from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = "documentation/plans/2026-11-05-dung-luong-kho.md"
SOFT_LIMIT_BYTES = 1_000_000_000
MB = 1_000_000
PACK_FRAME = 12 + 20
COMMITS = "(commit và cây gốc)"


class Unmeasurable(RuntimeError):
    pass


@dataclass(frozen=True)
class Growth:
    tip: str
    base: str | None
    base_time: str | None
    since: datetime
    days: float
    thin_pack_bytes: int
    pack_bytes: int
    breakdown: list[tuple[str, int]]
    by_file: bool = False

    @property
    def per_week(self) -> float:
        return self.thin_pack_bytes * 7 / self.days

    @property
    def days_to_soft_limit(self) -> float | None:
        per_day = self.thin_pack_bytes / self.days
        if per_day <= 0:
            return None
        return max(SOFT_LIMIT_BYTES - self.pack_bytes, 0) / per_day


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, input=stdin, capture_output=True, text=True, check=True,
    ).stdout


def base_commit(repo: Path, ref: str, since: datetime) -> str | None:
    found = _git(repo, "rev-list", "-1", "--first-parent", f"--before={since.isoformat()}",
                 ref).strip()
    return found or None


def directory_of(path: str, depth: int = 2) -> str:
    if not path:
        return COMMITS
    parts = path.split("/")
    return "/".join(parts[:-1][:depth]) or parts[0]


def _object_sizes(repo: Path, pack: Path) -> dict[str, int]:
    end = pack.stat().st_size - 20
    own = Path(_git(repo, "rev-parse", "--absolute-git-dir").strip()) / "objects"
    with tempfile.TemporaryDirectory() as tmp:
        objects = Path(tmp) / "objects"
        (objects / "pack").mkdir(parents=True)
        env = {**os.environ, "GIT_OBJECT_DIRECTORY": str(objects),
               "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(own)}
        with pack.open("rb") as stdin:
            subprocess.run(["git", "index-pack", "--stdin", "--fix-thin"], cwd=repo, env=env,
                           stdin=stdin, capture_output=True, check=True)
        (index,) = (objects / "pack").glob("*.idx")
        fixed_end = index.with_suffix(".pack").stat().st_size - 20
        with index.open("rb") as stdin:
            listing = subprocess.run(["git", "show-index"], cwd=repo, stdin=stdin,
                                     capture_output=True, text=True, check=True).stdout
    offsets = sorted((int(offset), sha) for offset, sha, *_ in map(str.split, listing.splitlines()))
    following = [offset for offset, _ in offsets[1:]] + [fixed_end]
    return {sha: after - offset
            for (offset, sha), after in zip(offsets, following, strict=True) if offset < end}


def thin_pack(repo: Path, ref: str, base: str | None,
              by_file: bool = False) -> tuple[int, list[tuple[str, int]]]:
    tip = _git(repo, "rev-parse", ref).strip()
    if base == tip:
        return 0, []
    revs = [tip, *([f"^{base}"] if base else [])]
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp) / "mong.pack"
        with pack.open("wb") as out:
            subprocess.run(["git", "pack-objects", "--stdout", "--thin", "--revs", "--no-reuse-delta", "-q"], cwd=repo,
                           input="\n".join(revs).encode() + b"\n", stdout=out, check=True)
        size = pack.stat().st_size
        sizes = _object_sizes(repo, pack)
    paths = {}
    for line in _git(repo, "rev-list", "--objects", *revs).splitlines():
        sha, _, path = line.partition(" ")
        paths[sha] = path
    totals: dict[str, int] = defaultdict(int)
    for sha, bytes_in_pack in sizes.items():
        path = paths.get(sha, "")
        totals[(path or COMMITS) if by_file else directory_of(path)] += bytes_in_pack
    return size, sorted(totals.items(), key=lambda item: (-item[1], item[0]))


def pack_bytes(repo: Path) -> int:
    fields = dict(
        line.split(": ", 1) for line in _git(repo, "count-objects", "-v").splitlines() if ": " in line
    )
    return (int(fields.get("size-pack", 0)) + int(fields.get("size", 0))) * 1024


def measure(repo: Path, ref: str = "HEAD", days: float = 7, now: datetime | None = None,
            by_file: bool = False) -> Growth:
    if _git(repo, "rev-parse", "--is-shallow-repository").strip() == "true":
        raise Unmeasurable(
            "Bản clone nông: mốc và kích thước gói sẽ sai. Lấy đủ lịch sử (checkout `fetch-depth: 0`)."
        )
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    since = now - timedelta(days=days)
    base = base_commit(repo, ref, since)
    size, breakdown = thin_pack(repo, ref, base, by_file)
    return Growth(
        tip=_git(repo, "rev-parse", ref).strip(),
        base=base,
        base_time=_git(repo, "log", "-1", "--format=%cI", base).strip() if base else None,
        since=since,
        days=days,
        thin_pack_bytes=size,
        pack_bytes=pack_bytes(repo),
        breakdown=breakdown,
        by_file=by_file,
    )


def _mb(value: float) -> str:
    return f"{value / MB:.1f}".replace(".", ",")


def report(growth: Growth, limit_mb: float, top: int = 10) -> str:
    over = growth.per_week > limit_mb * MB
    days_left = growth.days_to_soft_limit
    if growth.pack_bytes >= SOFT_LIMIT_BYTES:
        horizon = "đã vượt 1 GB"
    elif days_left is None:
        horizon = "kho không lớn thêm"
    else:
        horizon = f"≈ {days_left:.0f} ngày"
    since = growth.since.strftime("%d-%m-%Y %H:%M UTC")
    base = f"`{growth.base[:9]}` ({growth.base_time})" if growth.base else "đầu lịch sử"
    lines = [
        "## Dung lượng kho git",
        "",
        "| Số đo | Giá trị |",
        "|---|---|",
        f"| Gói git của bản clone đầy đủ | {_mb(growth.pack_bytes)} MB |",
        f"| Tăng từ {since} (gói mỏng, mốc {base}) | {_mb(growth.thin_pack_bytes)} MB |",
        f"| Quy ra một tuần | {_mb(growth.per_week)} MB |",
        f"| Ngưỡng | {_mb(limit_mb * MB)} MB/tuần |",
        f"| Ở tốc độ này, gói chạm 1 GB sau | {horizon} |",
        "",
        (f"**Đỏ:** kho tăng {_mb(growth.per_week)} MB/tuần, vượt ngưỡng {_mb(limit_mb * MB)} MB/tuần. "
         f"Xem các phương án trong `{PLAN}`." if over else
         f"Trong ngưỡng: kho tăng {_mb(growth.per_week)} MB/tuần."),
    ]
    if growth.breakdown:
        unit = "tệp" if growth.by_file else "thư mục"
        lines += [
            "",
            f"### Phần tăng theo {unit}",
            "",
            "Byte của chính gói mỏng, đã tính delta: các dòng cộng lại bằng phần tăng ở trên.",
            "",
            f"| {unit.capitalize()} | MB | Tỉ phần |",
            "|---|---|---|",
            *(f"| `{name}` | {_mb(size)} | {100 * size / growth.thin_pack_bytes:.0f}% |"
              for name, size in growth.breakdown[:top]),
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--days", type=float, default=7)
    parser.add_argument("--limit-mb", type=float, default=40, help="ngưỡng đỏ, MB mỗi tuần")
    parser.add_argument("--summary", type=Path,
                        help="tệp Markdown nhận bảng (mặc định $GITHUB_STEP_SUMMARY)")
    parser.add_argument("--now", type=datetime.fromisoformat, help="mốc hiện tại, ISO 8601 (để kiểm thử)")
    parser.add_argument("--by-file", action="store_true", help="chia phần tăng theo tệp, không theo thư mục")
    parser.add_argument("--top", type=int, default=10, help="số dòng của bảng phần tăng")
    args = parser.parse_args(argv)
    try:
        growth = measure(args.repo, args.ref, args.days, args.now, args.by_file)
    except Unmeasurable as exc:
        text = f"## Dung lượng kho git\n\nKhông đo được: {exc}\n"
        status = 2
    else:
        text = report(growth, args.limit_mb, args.top)
        status = 1 if growth.per_week > args.limit_mb * MB else 0
    summary = args.summary
    if summary is None and os.environ.get("GITHUB_STEP_SUMMARY"):
        summary = Path(os.environ["GITHUB_STEP_SUMMARY"])
    if summary:
        with summary.open("a", encoding="utf-8") as handle:
            handle.write(text)
    sys.stdout.write(text)
    return status


if __name__ == "__main__":
    sys.exit(main())
