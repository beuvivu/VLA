"""Đo kho git lớn thêm bao nhiêu trong một tuần; đỏ khi vượt ngưỡng (06-11-2026).

Phương án 1 của `documentation/plans/2026-11-05-dung-luong-kho.md`, chủ dự án duyệt 06-11-2026.
Workflow `repo-growth.yml` chạy kịch bản này mỗi thứ Hai và ghi bảng vào trang tóm tắt của lượt chạy.

Số đo là GÓI MỎNG: `git pack-objects --thin --revs` lấy mọi đối tượng mới kể từ mốc. Đó đúng là lượng
git phải lưu thêm, vì đã tính delta với phiên bản cũ. Bảng thư mục chia CHÍNH gói ấy: chỉ mục của gói
cho biết mỗi đối tượng chiếm bao nhiêu byte, nên các dòng cộng lại đúng bằng gói. Đừng thay bằng
`%(objectsize:disk)` của từng blob. Gói của máy chủ thường giữ bản MỚI nhất nguyên vẹn và lưu bản cũ
thành delta, nên phép cộng ấy gần gấp đôi số đúng, và ngày 05-11 nó báo 74 MB/tuần.

Mốc là commit cuối cùng trên chuỗi cha thứ nhất (`--first-parent`) trước `--days` ngày, tức trạng thái
của nhánh chính lúc ấy. Đi không theo chuỗi ấy thì `rev-list --before` có thể dừng ở commit nhánh phụ
cũ hơn nhiều, nếu nhánh đó được gộp vào sau mốc.

Bản clone NÔNG bị từ chối (thoát 2). Ngày 05-11-2026 ta đo trên bản nông, và mọi số đều sai:
- mốc 7 ngày rơi vào một commit nhánh phụ ngày 24-10;
- kích thước «gói» là của bản nông (642 MiB, bản đầy đủ chỉ 580 MiB);
- tốc độ báo 3 MB/ngày, đo lại trên bản đầy đủ là 4–9 MB/ngày.

Chạy: `python3 scripts/ops/repo_growth.py [--ref HEAD] [--days 7] [--limit-mb 40] [--summary TỆP]`;
`--by-file --top 15` chia phần tăng theo từng tệp.
Không có `--summary` thì kịch bản ghi vào `$GITHUB_STEP_SUMMARY` nếu biến ấy có, không thì ra stdout.
Mã thoát: 0 trong ngưỡng, 1 vượt ngưỡng, 2 không đo được.
"""
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
#: GitHub khuyên giữ kho dưới 1 GB.
SOFT_LIMIT_BYTES = 1_000_000_000
MB = 1_000_000
#: Đầu gói (12 byte) và mã băm cuối gói (20 byte): có trong gói mà không thuộc đối tượng nào.
PACK_FRAME = 12 + 20
#: Commit và cây gốc không có đường dẫn trong `rev-list --objects`.
COMMITS = "(commit và cây gốc)"


class Unmeasurable(RuntimeError):
    """Lịch sử không đủ để đo (bản clone nông)."""


@dataclass(frozen=True)
class Growth:
    tip: str
    base: str | None          # None: cả lịch sử nằm trong cửa sổ
    base_time: str | None
    since: datetime
    days: float
    thin_pack_bytes: int
    pack_bytes: int
    #: Byte của gói mỏng theo nhóm (thư mục, hoặc tệp khi `by_file`), lớn nhất trước; cộng lại bằng
    #: `thin_pack_bytes − PACK_FRAME`.
    breakdown: list[tuple[str, int]]
    by_file: bool = False

    @property
    def per_week(self) -> float:
        return self.thin_pack_bytes * 7 / self.days

    @property
    def days_to_soft_limit(self) -> float | None:
        """Số ngày tới 1 GB ở tốc độ này; None khi kho không lớn thêm."""
        per_day = self.thin_pack_bytes / self.days
        if per_day <= 0:
            return None
        return max(SOFT_LIMIT_BYTES - self.pack_bytes, 0) / per_day


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, input=stdin, capture_output=True, text=True, check=True,
    ).stdout


def base_commit(repo: Path, ref: str, since: datetime) -> str | None:
    """Commit cuối của nhánh chính trước mốc, hoặc None khi cả lịch sử nằm sau mốc."""
    found = _git(repo, "rev-list", "-1", "--first-parent", f"--before={since.isoformat()}",
                 ref).strip()
    return found or None


def directory_of(path: str, depth: int = 2) -> str:
    """Nhóm của một đường dẫn: `depth` cấp đầu của THƯ MỤC chứa nó.

    `docs/a.html` vào `docs`, `data/stats/advanced/x.csv` vào `data/stats`. Tệp ở gốc kho đứng
    riêng bằng tên của nó.
    """
    if not path:
        return COMMITS
    parts = path.split("/")
    return "/".join(parts[:-1][:depth]) or parts[0]


def _object_sizes(repo: Path, pack: Path) -> dict[str, int]:
    """Số byte mỗi đối tượng chiếm trong gói mỏng, đọc từ chỉ mục của chính gói.

    Gói mỏng không tự dựng chỉ mục được: delta của nó trỏ vào đối tượng ở ngoài gói. `index-pack
    --fix-thin` nối các đối tượng gốc ấy vào CUỐI gói, nên mọi đối tượng của gói mỏng giữ nguyên vị
    trí. Kích thước một đối tượng là khoảng tới đối tượng kế tiếp trong gói đã nối; đối tượng nối thêm
    (vị trí ≥ cuối gói mỏng) bị bỏ. Gói mới ghi vào thư mục tạm; kho đang đo chỉ được đọc qua
    alternates.
    """
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
    """Kích thước gói mỏng của mọi đối tượng có trong `ref` mà không có trong `base`, và phần của
    từng thư mục (hoặc từng tệp, khi `by_file`) trong gói ấy, lớn nhất trước."""
    tip = _git(repo, "rev-parse", ref).strip()
    if base == tip:
        return 0, []
    revs = [tip, *([f"^{base}"] if base else [])]
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp) / "mong.pack"
        # Gói có thể dài hàng chục MB: ghi thẳng ra đĩa, không giữ trong bộ nhớ.
        with pack.open("wb") as out:
            subprocess.run(["git", "pack-objects", "--stdout", "--thin", "--revs", "-q"], cwd=repo,
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
    """Dung lượng đối tượng trong kho cục bộ (gói và đối tượng rời), tính bằng byte."""
    fields = dict(
        line.split(": ", 1) for line in _git(repo, "count-objects", "-v").splitlines() if ": " in line
    )
    return (int(fields.get("size-pack", 0)) + int(fields.get("size", 0))) * 1024


def measure(repo: Path, ref: str = "HEAD", days: float = 7, now: datetime | None = None,
            by_file: bool = False) -> Growth:
    """Đo gói mỏng của `days` ngày gần nhất trên `ref`; từ chối bản clone nông."""
    if _git(repo, "rev-parse", "--is-shallow-repository").strip() == "true":
        raise Unmeasurable(
            "Bản clone nông: mốc và kích thước gói sẽ sai. Lấy đủ lịch sử (checkout `fetch-depth: 0`)."
        )
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)  # git đọc giờ không múi theo máy chạy: chốt UTC
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
    """Bảng Markdown cho trang tóm tắt của lượt chạy."""
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
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
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
