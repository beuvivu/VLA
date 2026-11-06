"""Bước theo dõi dung lượng kho hằng tuần (`scripts/ops/repo_growth.py`, `repo-growth.yml`), 06-11-2026.

Bản kế hoạch dung lượng (`documentation/plans/2026-11-05-dung-luong-kho.md`) từng báo sai số hai lần:
- «74 MB/tuần» vì cộng blob nén từng cái, bỏ qua delta;
- «3 MB/ngày, gói 642 MB» vì đo trên bản clone NÔNG của phiên làm việc.
Trên bản đầy đủ, gói là 608 MB và kho tăng 4–9 MB/ngày.

Mỗi phép dưới đây ghim đúng một trong những luật đã chặn các lỗi ấy, trên kho git dựng sẵn có ngày
commit cố định:
- số đo là gói mỏng;
- mốc đi theo nhánh chính;
- bản nông bị từ chối;
- workflow lấy đủ lịch sử.
"""
from __future__ import annotations

import importlib.util
import os
import random
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "repo-growth.yml"
SCRIPT = ROOT / "scripts" / "ops" / "repo_growth.py"

_spec = importlib.util.spec_from_file_location("repo_growth", SCRIPT)
growth = importlib.util.module_from_spec(_spec)
sys.modules["repo_growth"] = growth  # dataclass cần module đã đăng ký
_spec.loader.exec_module(growth)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _git(repo: Path, *args: str, when: datetime | None = None) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "kiem-thu", "GIT_AUTHOR_EMAIL": "kiem-thu@example.invalid",
        "GIT_COMMITTER_NAME": "kiem-thu", "GIT_COMMITTER_EMAIL": "kiem-thu@example.invalid",
    }
    if when is not None:
        stamp = f"@{int(when.timestamp())} +0000"
        env |= {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo, env=env, check=True, capture_output=True, text=True,
    ).stdout


def _commit(repo: Path, day: float, files: dict[str, bytes], message: str = "c") -> str:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message, when=T0 + timedelta(days=day))
    return _git(repo, "rev-parse", "HEAD").strip()


def _noise(size: int, seed: int) -> bytes:
    """Byte ngẫu nhiên: zlib không nén được, nên kích thước nén ≈ kích thước thật."""
    return random.Random(seed).randbytes(size)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "kho"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    return path


def test_growth_is_the_thin_pack_not_the_sum_of_compressed_blobs(repo: Path) -> None:
    """Sửa 10 byte cuối của tệp 300 KB thì kho chỉ lưu thêm một delta nhỏ, không phải 300 KB.

    Trong gói của chính kho, phiên bản MỚI giữ nguyên vẹn (`%(objectsize:disk)` ≈ 300 KB). Cộng số ấy
    là cách bản rà soát 05-11 ra «74 MB/tuần».
    """
    big = _noise(300_000, seed=1)
    _commit(repo, 0, {"data/excel/bang.bin": big})
    _commit(repo, 8, {"data/excel/bang.bin": big[:-10] + b"0123456789"})
    _git(repo, "gc", "-q")
    newest = _git(repo, "rev-parse", "HEAD:data/excel/bang.bin")
    on_disk = int(subprocess.run(["git", "cat-file", "--batch-check=%(objectsize:disk)"], cwd=repo,
                                 input=newest, capture_output=True, text=True, check=True).stdout)
    measured = growth.measure(repo, "HEAD", days=7, now=T0 + timedelta(days=9))
    assert on_disk > 290_000                      # trong gói của kho, bản mới nằm nguyên vẹn
    assert 0 < measured.thin_pack_bytes < 20_000  # còn lượng kho phải lưu thêm chỉ là delta


def test_the_directory_table_adds_up_to_the_thin_pack(repo: Path) -> None:
    """Mỗi byte của gói mỏng thuộc đúng một dòng, kể cả byte của delta, không thêm byte nào khác.

    `index-pack --fix-thin` nối đối tượng gốc của delta vào cuối gói để dựng chỉ mục; tính cả chúng
    thì bảng cộng lại lớn hơn gói.
    """
    big = _noise(100_000, seed=10)
    _commit(repo, 0, {"docs/trang.bin": big, "data/stats/bang.bin": _noise(50_000, seed=11)})
    _commit(repo, 8, {"docs/trang.bin": big[:-5] + b"abcde",
                      "data/stats/moi.bin": _noise(30_000, seed=12)})
    measured = growth.measure(repo, "HEAD", days=7, now=T0 + timedelta(days=9))
    table = dict(measured.breakdown)
    assert sum(table.values()) == measured.thin_pack_bytes - growth.PACK_FRAME
    assert table["data/stats"] > 29_000           # tệp mới vào nguyên vẹn
    assert table["docs"] < 1_000                  # tệp sửa chỉ là delta
    assert set(table) == {"docs", "data/stats", "data", growth.COMMITS}
    files = dict(growth.measure(repo, "HEAD", days=7, now=T0 + timedelta(days=9), by_file=True).breakdown)
    assert sum(files.values()) == sum(table.values())
    assert files["data/stats/moi.bin"] > 29_000 and files["docs/trang.bin"] < 1_000


def test_the_window_starts_on_the_main_line_not_on_an_old_side_branch(repo: Path) -> None:
    """Nhánh phụ commit ngày 4, gộp vào ngày 10: tệp của nó vào nhánh chính TRONG cửa sổ 5 → 12.

    Không theo `--first-parent`, `rev-list --before` dừng ở chính commit nhánh phụ (ngày 4 là commit
    mới nhất trước mốc), coi tệp ấy là cũ và bỏ khỏi số đo.
    """
    _commit(repo, 0, {"a.txt": b"goc"})
    _git(repo, "checkout", "-q", "-b", "phu")
    _commit(repo, 4, {"docs/trang.bin": _noise(200_000, seed=2)}, "nhanh phu")
    _git(repo, "checkout", "-q", "main")
    before_window = _commit(repo, 2, {"a.txt": b"chinh"}, "nhanh chinh")
    _git(repo, "merge", "-q", "--no-ff", "-m", "gop", "phu", when=T0 + timedelta(days=10))
    measured = growth.measure(repo, "main", days=7, now=T0 + timedelta(days=12))
    assert measured.base == before_window
    assert measured.thin_pack_bytes > 190_000


def test_a_shallow_clone_is_refused_instead_of_measured(repo: Path, tmp_path: Path) -> None:
    """Bản nông có kích thước gói khác và thiếu chuỗi nhánh chính: đo ra số sai mà trông hợp lý."""
    for day in range(10):
        _commit(repo, day, {"data/so.bin": _noise(5_000, seed=day)})
    shallow = tmp_path / "nong"
    subprocess.run(["git", "clone", "-q", "--depth", "2", f"file://{repo}", str(shallow)],
                   check=True, capture_output=True)
    with pytest.raises(growth.Unmeasurable):
        growth.measure(shallow, "HEAD", days=7, now=T0 + timedelta(days=10))
    summary = tmp_path / "tom-tat.md"
    assert growth.main(["--repo", str(shallow), "--summary", str(summary)]) == 2
    assert "Không đo được" in summary.read_text(encoding="utf-8")


def test_the_run_turns_red_only_when_the_week_grows_past_the_limit(repo: Path, tmp_path: Path) -> None:
    _commit(repo, 0, {"a.txt": b"goc"})
    _commit(repo, 5, {"data/stats/bang.bin": _noise(200_000, seed=3)})
    now = (T0 + timedelta(days=6)).isoformat()
    over, under = tmp_path / "do.md", tmp_path / "xanh.md"
    args = ["--repo", str(repo), "--days", "7", "--now", now]
    assert growth.main([*args, "--limit-mb", "0.1", "--summary", str(over)]) == 1
    assert growth.main([*args, "--limit-mb", "1", "--summary", str(under)]) == 0
    assert "**Đỏ:**" in over.read_text(encoding="utf-8")
    assert "Trong ngưỡng" in under.read_text(encoding="utf-8")


def test_a_week_without_new_commits_grows_by_nothing(repo: Path) -> None:
    """Cửa sổ rỗng là 0 byte. Một gói rỗng vẫn có 32 byte đầu/đuôi, và chúng không được tính là tăng."""
    _commit(repo, 0, {"a.txt": b"goc"})
    measured = growth.measure(repo, "HEAD", days=7, now=T0 + timedelta(days=30))
    assert measured.thin_pack_bytes == 0
    assert measured.days_to_soft_limit is None
    assert "kho không lớn thêm" in growth.report(measured, limit_mb=40)


def test_a_history_younger_than_the_window_counts_every_object(repo: Path) -> None:
    _commit(repo, 0, {"data/xsmb.bin": _noise(50_000, seed=4)})
    measured = growth.measure(repo, "HEAD", days=7, now=T0 + timedelta(days=1))
    assert measured.base is None
    assert measured.thin_pack_bytes > 49_000
    assert "đầu lịch sử" in growth.report(measured, limit_mb=40)


def test_new_files_are_grouped_by_the_directory_that_holds_them() -> None:
    """`docs/a.html` vào `docs`, không đứng riêng: lượt thử đầu xếp từng trang thành một dòng."""
    assert growth.directory_of("docs/a.html") == "docs"
    assert growth.directory_of("data/stats/advanced/x.csv") == "data/stats"
    assert growth.directory_of("data/xsmb.json") == "data"
    assert growth.directory_of("README.md") == "README.md"
    assert growth.directory_of("") == growth.COMMITS


def test_the_weekly_workflow_measures_on_a_full_clone_and_can_turn_red() -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = document.get(True, document.get("on"))
    assert on["schedule"] and "workflow_dispatch" in on
    assert document["permissions"] == {"contents": "read"}
    (job,) = document["jobs"].values()
    steps = job["steps"]
    checkout = next(step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@"))
    assert checkout.get("with", {}).get("fetch-depth") == 0
    runs = [step for step in steps if "scripts/ops/repo_growth.py" in step.get("run", "")]
    assert len(runs) == 1
    # Lượt vượt ngưỡng phải đỏ: không được nuốt mã thoát.
    assert not runs[0].get("continue-on-error") and not job.get("continue-on-error")
    assert "||" not in runs[0]["run"]
