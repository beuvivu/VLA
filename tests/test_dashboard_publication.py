"""Chạy bước xuất bản dashboard với Git thật và nhánh chính tiến lên."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BUILDER = Path("src") / "build_markdown_dashboard_v3.py"
pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="cần bash và git",
)


class DashboardRepo:
    """Hai runner cục bộ cùng xuất bản một bảng là hàm của dữ liệu."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        for name, body in (
            ("python", f'exec "{sys.executable}" "$@"\n'),
            ("sleep", "exit 0\n"),
        ):
            executable = bin_dir / name
            executable.write_text("#!/bin/sh\n" + body, encoding="utf-8")
            executable.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
        self.remote = tmp / "remote.git"
        self.git(tmp, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.other = tmp / "other"
        self.git(tmp, "clone", str(self.remote), str(self.other))
        (self.other / "src").mkdir()
        (self.other / BUILDER).write_text(
            "from pathlib import Path\n"
            "text = Path('marker').read_text() + '\\n'\n"
            "text += 'Màu | Khoảng giá trị | Ý nghĩa\\nlịch 7 cột\\n'\n"
            "text += 'Độ nâng so với nền\\nKiểm toán và liên kết chi tiết\\n'\n"
            "text += 'Đầu\\\\Đuôi\\n' * 12\n"
            "text += '| Ý nghĩa | Thanh so sánh |\\n' * 20\n"
            "Path('DASHBOARD.md').write_text(text + 'x' * 71000)\n",
            encoding="utf-8",
        )
        (self.other / "marker").write_text("m1", encoding="utf-8")
        (self.other / "DASHBOARD.md").write_text("old", encoding="utf-8")
        self.push_from(self.other, "seed")
        self.runner = tmp / "runner"
        self.git(tmp, "clone", str(self.remote), str(self.runner))
        subprocess.run(
            [sys.executable, str(BUILDER)],
            cwd=self.runner, check=True,
        )

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    def push_from(self, clone: Path, message: str) -> None:
        self.git(clone, "add", ".")
        self.git(clone, "commit", "-m", message)
        self.git(clone, "push", "origin", "main")

    def run(self) -> subprocess.CompletedProcess[str]:
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/dashboard-refresh.yml").read_text(encoding="utf-8")
        )
        step = next(s for s in workflow["jobs"]["refresh"]["steps"]
                    if s.get("name") == "Ghi nhận bảng điều khiển đã làm mới")
        script = self.tmp / "publish.sh"
        script.write_text(step["run"], encoding="utf-8")
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
            cwd=self.runner, env=self.env, capture_output=True, text=True, timeout=30,
            check=False,
        )


def test_dashboard_is_rebuilt_after_main_advances(tmp_path: Path) -> None:
    """Retry phải dùng dữ liệu mới, kể cả hai runner cùng đổi dashboard."""
    repo = DashboardRepo(tmp_path)
    (repo.other / "marker").write_text("m2", encoding="utf-8")
    (repo.other / "DASHBOARD.md").write_text("another dashboard", encoding="utf-8")
    repo.push_from(repo.other, "new data")

    result = repo.run()

    assert result.returncode == 0, result.stdout + result.stderr
    published = repo.git(tmp_path, "--git-dir", str(repo.remote), "show", "main:DASHBOARD.md")
    assert published.startswith("m2\n")
    assert repo.git(tmp_path, "--git-dir", str(repo.remote), "show", "main:marker") == "m2"


def test_dashboard_stops_after_bounded_rejected_pushes(tmp_path: Path) -> None:
    """Lỗi quyền/remote dai dẳng phải đỏ, không báo đã xuất bản."""
    repo = DashboardRepo(tmp_path)
    attempts = tmp_path / "attempts"
    hook = repo.remote / "hooks/pre-receive"
    hook.write_text(f"#!/bin/sh\necho push >> '{attempts}'\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    result = repo.run()

    assert result.returncode != 0
    assert attempts.read_text(encoding="utf-8").splitlines() == ["push"] * 4
    assert repo.git(tmp_path, "--git-dir", str(repo.remote), "show", "main:DASHBOARD.md") == "old"


def test_dashboard_retry_does_not_duplicate_an_already_published_build(tmp_path: Path) -> None:
    """Một runner khác đã dựng đúng bảng thì kết thúc xanh, không thêm commit."""
    repo = DashboardRepo(tmp_path)
    (repo.other / "marker").write_text("m2", encoding="utf-8")
    subprocess.run([sys.executable, str(BUILDER)], cwd=repo.other, check=True)
    repo.push_from(repo.other, "already refreshed")
    before = repo.git(repo.other, "rev-parse", "HEAD")

    result = repo.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert repo.git(tmp_path, "--git-dir", str(repo.remote), "rev-parse", "main") == before


def test_dashboard_retry_validates_the_rebuilt_page(tmp_path: Path) -> None:
    """Bản sinh lại không đạt hợp đồng bố cục phải dừng trước khi push."""
    repo = DashboardRepo(tmp_path)
    (repo.other / BUILDER).write_text(
        "from pathlib import Path\nPath('DASHBOARD.md').write_text('broken')\n",
        encoding="utf-8",
    )
    repo.push_from(repo.other, "broken builder")
    before = repo.git(repo.other, "rev-parse", "HEAD")

    result = repo.run()

    assert result.returncode != 0
    assert "AssertionError" in result.stderr
    assert repo.git(tmp_path, "--git-dir", str(repo.remote), "rev-parse", "main") == before
