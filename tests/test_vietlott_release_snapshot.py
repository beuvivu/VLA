"""Commit bot Vietlott phải mang đúng manifest của các trang nó vừa dựng."""

import os
from pathlib import Path
import shutil
import subprocess

import yaml

from site_assets import check_site, refresh_site

ROOT = Path(__file__).resolve().parents[1]


def test_vietlott_bot_commits_a_complete_release_snapshot(tmp_path: Path) -> None:
    """Chạy nguyên shell ghi trang; chỉ thay hai lệnh giao tiếp remote bằng no-op."""
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run([git, "config", "user.name", "Fixture"], cwd=tmp_path, check=True)
    subprocess.run([git, "config", "user.email", "fixture@example.test"], cwd=tmp_path, check=True)
    docs = tmp_path / "docs"
    assets = docs / "assets"
    assets.mkdir(parents=True)
    for name in ("vietlott-picks.js", "vietlott-comparison.js", "app-evidence.js"):
        (assets / name).write_text("/* bản đầu */", encoding="utf-8")
    page = docs / "vietlott.html"
    page.write_text("<!doctype html><p>Trước kỳ mới</p>", encoding="utf-8")
    other_page = docs / "index.html"
    other_page.write_text('<!doctype html><p>Trang chủ</p><script src="assets/app-evidence.js"></script>', encoding="utf-8")
    refresh_site(docs)
    subprocess.run([git, "add", "docs"], cwd=tmp_path, check=True)
    subprocess.run([git, "commit", "-qm", "Ảnh chụp ban đầu"], cwd=tmp_path, check=True)
    page.write_text("<!doctype html><p>Kết quả kỳ mới</p>", encoding="utf-8")
    # Tài nguyên dùng chung thay đổi cũng phải nằm trong cùng ảnh chụp đã ghi.
    (assets / "app-evidence.js").write_text("/* tài nguyên mới */", encoding="utf-8")
    (tmp_path / "src").mkdir()
    shutil.copyfile(ROOT / "src/site_assets.py", tmp_path / "src/site_assets.py")
    commands = tmp_path / "commands"
    commands.mkdir()
    wrapper = commands / "git"
    wrapper.write_text(
        '#!/bin/sh\nif [ "$1" = pull ] || [ "$1" = push ]; then exit 0; fi\n'
        f'exec "{git}" "$@"\n', encoding="utf-8",
    )
    wrapper.chmod(0o755)
    workflow = yaml.safe_load((ROOT / ".github/workflows/vietlott-results.yml").read_text())
    steps = workflow["jobs"]["build"]["steps"]
    commit_step = next(step for step in steps if step.get("name") == "Ghi trang")
    subprocess.run(
        ["bash", "-e", "-c", commit_step["run"]], cwd=tmp_path, check=True,
        env={**os.environ, "PATH": f"{commands}:{os.environ['PATH']}", "GITHUB_REF_NAME": "main"},
        capture_output=True, text=True,
    )
    # Đọc nội dung ĐÃ COMMIT, tránh vô tình đo manifest chưa được stage.
    committed = tmp_path / "committed"
    committed.mkdir()
    names = subprocess.check_output([git, "ls-tree", "-r", "--name-only", "HEAD", "docs"], cwd=tmp_path, text=True).splitlines()
    for name in names:
        target = committed / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output([git, "show", f"HEAD:{name}"], cwd=tmp_path))
    assert check_site(committed / "docs") == []
    assert (committed / "docs/assets/app-evidence.js").is_file()
    assert subprocess.check_output([git, "status", "--porcelain", "--", "docs"], cwd=tmp_path, text=True) == ""
