"""Commit bot Vietlott phải mang đúng manifest của các trang nó vừa dựng."""

import os
from pathlib import Path
import shutil
import subprocess

import yaml

from web.site_assets import check_site, refresh_site

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ("src/web/site_assets.py", "scripts/ops/push_generated_site.py", "scripts/web/stamp_only_change.py")


def test_vietlott_bot_commits_a_complete_release_snapshot(tmp_path: Path) -> None:
    """Chạy nguyên shell ghi trang và helper thật trên remote git cục bộ."""
    def git(repo, *args):
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    git(tmp_path, "init", "--bare", "-q", "--initial-branch=main", str(remote))
    git(tmp_path, "clone", "-q", str(remote), str(work))
    git(work, "config", "user.name", "Fixture")
    git(work, "config", "user.email", "fixture@example.test")
    docs, assets = work / "docs", work / "docs/assets"
    assets.mkdir(parents=True)
    for name in ("vietlott-picks.js", "vietlott-comparison.js", "app-evidence.js"):
        (assets / name).write_text("/* bản đầu */", encoding="utf-8")
    page = docs / "vietlott.html"
    page.write_text("<!doctype html><p>Trước kỳ mới</p>", encoding="utf-8")
    (docs / "index.html").write_text(
        '<!doctype html><p>Trang chủ</p><script src="assets/app-evidence.js"></script>', encoding="utf-8",
    )
    for name in SCRIPTS:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    refresh_site(docs)
    git(work, "add", ".")
    git(work, "commit", "-qm", "Ảnh chụp ban đầu")
    git(work, "push", "-q", "origin", "main")
    page.write_text("<!doctype html><p>Kết quả kỳ mới</p>", encoding="utf-8")
    # Sửa tài nguyên chung buộc finalizer thay cả URL trên trang chủ.
    (assets / "app-evidence.js").write_text("/* tài nguyên mới */", encoding="utf-8")
    workflow = yaml.safe_load((ROOT / ".github/workflows/vietlott-results.yml").read_text())
    step = next(step for step in workflow["jobs"]["build"]["steps"] if step.get("name") == "Ghi trang")
    subprocess.run(
        ["bash", "-e", "-c", step["run"]], cwd=work, check=True,
        env={**os.environ, "GITHUB_REF_NAME": "main"}, capture_output=True, text=True,
    )
    # Clone remote sau khi đẩy: không được vô tình đo cây chưa commit/stage.
    published = tmp_path / "published"
    git(tmp_path, "clone", "-q", str(remote), str(published))
    assert check_site(published / "docs") == []
    assert (published / "docs/assets/app-evidence.js").read_text() == "/* tài nguyên mới */"
    assert "Kết quả kỳ mới" in (published / "docs/vietlott.html").read_text()
    assert git(work, "status", "--porcelain").stdout == ""


def _run_write_step(work: Path) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/vietlott-results.yml").read_text())
    step = next(step for step in workflow["jobs"]["build"]["steps"] if step.get("name") == "Ghi trang")
    subprocess.run(
        ["bash", "-e", "-c", step["run"]], cwd=work, check=True,
        env={**os.environ, "GITHUB_REF_NAME": "main"}, capture_output=True, text=True,
    )


def _stamped(at: str, body: str = "Kỳ #1582") -> str:
    return (f'<!doctype html><p>{body}</p><p class="vl-muted">Bản dữ liệu được dựng lúc {at} 01/11/2026 '
            "(giờ Việt Nam). Đây là bản chụp tại lần dựng trang.</p>")


def _fixture(tmp_path: Path, page_text: str):
    def git(repo, *args):
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    git(tmp_path, "init", "--bare", "-q", "--initial-branch=main", str(remote))
    git(tmp_path, "clone", "-q", str(remote), str(work))
    git(work, "config", "user.name", "Fixture")
    git(work, "config", "user.email", "fixture@example.test")
    docs = work / "docs"
    (docs / "assets").mkdir(parents=True)
    (docs / "assets" / "vietlott-picks.js").write_text("/* bản đầu */", encoding="utf-8")
    (docs / "vietlott.html").write_text(page_text, encoding="utf-8")
    for name in SCRIPTS:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    refresh_site(docs)
    git(work, "add", ".")
    git(work, "commit", "-qm", "Ảnh chụp ban đầu")
    git(work, "push", "-q", "origin", "main")
    return git, remote, work, docs


def test_a_rebuild_that_only_moves_the_build_time_is_not_committed(tmp_path: Path) -> None:
    """78% lượt dựng tháng 10-2026 chỉ đổi giờ dựng: không commit, giữ đúng bản HEAD để triển khai."""
    git, remote, work, docs = _fixture(tmp_path, _stamped("06:17"))
    head = git(work, "rev-parse", "HEAD").stdout
    committed = (docs / "vietlott.html").read_text(encoding="utf-8")
    (docs / "vietlott.html").write_text(_stamped("06:30"), encoding="utf-8")
    _run_write_step(work)
    assert git(remote, "rev-parse", "main").stdout == head
    assert (docs / "vietlott.html").read_text(encoding="utf-8") == committed
    assert git(work, "status", "--porcelain").stdout == ""
    assert check_site(docs) == []


def test_a_rebuild_that_changes_content_next_to_the_build_time_is_committed(tmp_path: Path) -> None:
    git, remote, work, docs = _fixture(tmp_path, _stamped("06:17"))
    head = git(work, "rev-parse", "HEAD").stdout
    (docs / "vietlott.html").write_text(_stamped("06:30", body="Kỳ #1583"), encoding="utf-8")
    _run_write_step(work)
    assert git(remote, "rev-parse", "main").stdout != head
    published = tmp_path / "published"
    git(tmp_path, "clone", "-q", str(remote), str(published))
    assert "Kỳ #1583" in (published / "docs/vietlott.html").read_text(encoding="utf-8")
    assert check_site(published / "docs") == []
