"""Trang Vietlott không đè trang XSMB khi triển khai Pages (18-11-2026).

Pages là MỘT site, mọi lần triển khai tải lên nguyên `docs/`. Ngày 18-11-2026 workflow trang Vietlott
triển khai ảnh chụp git lúc 18:38:33 (giờ VN), đè trang kết quả XSMB mà `publish-results` đã triển khai
lúc 18:35:52 nhưng chưa commit; trang chủ hiện kết quả hôm qua tới 18:41:09. Phép kiểm ghim cả LUẬT
(`scripts/ops/pages_deploy_window.py`) lẫn chỗ workflow dùng nó, và chạy thật hai khối `run:` mới.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "pages_deploy_window.py"
WORKFLOW = ROOT / ".github" / "workflows" / "vietlott-results.yml"

_spec = importlib.util.spec_from_file_location("pages_deploy_window", SCRIPT)
window = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(window)

UTC = timezone.utc
CANONICAL = datetime(2026, 11, 18, 11, 34, 29, tzinfo=UTC)  # commit «data: finalize XSMB 2026-11-18»


def _ledger(*days: str) -> str:
    return "date,special\n" + "".join(f"{day},12345\n" for day in days)


def _forecasts(*pairs: tuple[str, str]) -> list[str]:
    return [f"predict_next_{mode}_all_{day}.csv" for mode, day in pairs]


BOTH_18 = _forecasts(("loto", "2026-11-18"), ("de", "2026-11-18"))
BOTH_19 = BOTH_18 + _forecasts(("loto", "2026-11-19"), ("de", "2026-11-19"))


def test_the_night_of_18_11_is_replayed_as_a_yield() -> None:
    """Đúng tình huống đã xảy ra: kỳ 18-11 đã chốt, chưa có dự báo 19-11, Vietlott triển khai 4 phút sau."""
    decision = window.decide(_ledger("2026-11-17", "2026-11-18"), BOTH_18, CANONICAL,
                             datetime(2026, 11, 18, 11, 38, 22, tzinfo=UTC))
    assert decision.deploy is False
    assert "đang chốt kỳ 2026-11-18" in decision.reason and "nhường" in decision.reason


def test_once_the_full_pipeline_wrote_the_next_forecasts_vietlott_deploys_again() -> None:
    decision = window.decide(_ledger("2026-11-18"), BOTH_19, CANONICAL,
                             datetime(2026, 11, 18, 11, 41, tzinfo=UTC))
    assert decision.deploy is True and "không đang chốt kỳ" in decision.reason


def test_one_mode_alone_does_not_close_the_window() -> None:
    names = BOTH_18 + _forecasts(("loto", "2026-11-19"))
    decision = window.decide(_ledger("2026-11-18"), names, CANONICAL, CANONICAL + timedelta(minutes=3))
    assert decision.deploy is False


def test_the_next_draw_may_come_after_a_break_in_the_calendar() -> None:
    """Dự báo mang ngày QUAY kế tiếp, không phải ngày lịch kế tiếp (nghỉ Tết)."""
    names = _forecasts(("loto", "2027-02-10"), ("de", "2027-02-10"))
    decision = window.decide(_ledger("2027-02-05"), names, None, datetime(2027, 2, 6, tzinfo=UTC))
    assert decision.deploy is True


def test_older_forecasts_and_foreign_files_do_not_count() -> None:
    names = BOTH_18 + ["predict_next_loto_2026-11-19.csv", "predict_next_de_all_2026-11-19.csv.bak", "notes.md"]
    decision = window.decide(_ledger("2026-11-18"), names, CANONICAL, CANONICAL + timedelta(minutes=2))
    assert decision.deploy is False


@pytest.mark.parametrize("minutes,deploy", [(0, False), (59, False), (60, False), (61, True), (240, True)])
def test_a_stuck_xsmb_pipeline_does_not_freeze_the_vietlott_page_forever(minutes: int, deploy: bool) -> None:
    decision = window.decide(_ledger("2026-11-18"), BOTH_18, CANONICAL, CANONICAL + timedelta(minutes=minutes))
    assert decision.deploy is deploy
    if deploy:
        assert "có thể đã kẹt" in decision.reason


def test_an_unknown_finalization_time_yields_and_a_missing_ledger_deploys() -> None:
    late = CANONICAL + timedelta(hours=5)
    assert window.decide(_ledger("2026-11-18"), BOTH_18, None, late).deploy is False
    assert window.decide("", BOTH_18, None, late).deploy is True
    assert window.decide("date,special\n", [], None, late).deploy is True


def test_api_times_are_parsed_and_garbage_is_unknown() -> None:
    assert window.parse_time("2026-11-18T11:34:29Z") == CANONICAL
    assert window.parse_time("2026-11-18T18:34:29+07:00") == CANONICAL
    assert window.parse_time("2026-11-18T11:34:29") == CANONICAL  # không múi giờ thì coi là UTC
    for garbage in ("", "   ", "null", "không phải giờ"):
        assert window.parse_time(garbage) is None


# --- Đọc từ một ref git thật -----------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def _repo(path: Path, ledger: str, forecasts: list[str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    (path / "data" / "forecast" / "predict").mkdir(parents=True)
    (path / "data" / "xsmb.csv").write_text(ledger, encoding="utf-8")
    for name in forecasts:
        (path / "data" / "forecast" / "predict" / name).write_text("number,prob\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "khởi tạo")
    return path


def _outputs(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)


def test_main_reads_the_ledger_and_forecasts_of_the_given_ref(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path / "kho", _ledger("2026-11-17", "2026-11-18"), BOTH_18)
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    just_now = (datetime.now(UTC) - timedelta(minutes=3)).isoformat()
    assert window.main(["--repo", str(repo), "--ref", "HEAD", "--canonical-at", just_now]) == 0
    assert _outputs(out)["deploy"] == "false"
    # Pipeline XSMB ghi dự báo kỳ sau: commit mới, cùng lệnh, giờ được triển khai.
    for name in _forecasts(("loto", "2026-11-19"), ("de", "2026-11-19")):
        (repo / "data" / "forecast" / "predict" / name).write_text("number,prob\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: finalize analytics 2026-11-18")
    out.unlink()
    window.main(["--repo", str(repo), "--ref", "HEAD", "--canonical-at", just_now])
    assert _outputs(out)["deploy"] == "true"
    # Ref cũ vẫn đọc đúng ảnh chụp cũ: hàm đọc theo ref, không theo cây làm việc.
    out.unlink()
    window.main(["--repo", str(repo), "--ref", "HEAD~1", "--canonical-at", just_now])
    assert _outputs(out)["deploy"] == "false"


# --- Chỗ workflow dùng luật ------------------------------------------------------------------


def _steps() -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["build"]["steps"]


def _step(name: str) -> dict:
    return next(step for step in _steps() if step.get("name") == name)


def _index(name: str) -> int:
    return next(i for i, step in enumerate(_steps()) if step.get("name") == name)


SYNC = "Lấy docs/ của nhánh mặc định mới nhất"
YIELD = "Nhường lần triển khai khi XSMB đang chốt kỳ"


def test_the_package_is_taken_from_the_newest_branch_after_this_run_pushed() -> None:
    order = [_index("Ghi trang"), _index(SYNC), _index(YIELD), _index("Chốt phiên bản và kiểm tra tài nguyên"),
             _index("Đóng gói GitHub Pages"), _index("Đánh dấu đã đóng gói")]
    assert order == sorted(order)
    sync = _step(SYNC)["run"]
    assert 'git fetch --no-tags --depth=1 origin "${GITHUB_REF_NAME}"' in sync
    assert "git restore --source=FETCH_HEAD --staged --worktree -- docs" in sync
    run = _step(YIELD)["run"]
    assert _step(YIELD)["id"] == "window"
    assert "scripts/ops/pages_deploy_window.py --ref FETCH_HEAD" in run
    assert "path=data/xsmb.csv" in run and window.LEDGER == "data/xsmb.csv"


@pytest.mark.parametrize("deploy,packaged", [("true", True), ("false", False), ("", False)])
def test_packaging_and_the_deploy_job_follow_the_window_decision(deploy: str, packaged: bool) -> None:
    github = SimpleNamespace(ref_name="main", event=SimpleNamespace(repository=SimpleNamespace(default_branch="main")))
    steps = SimpleNamespace(window=SimpleNamespace(outputs=SimpleNamespace(deploy=deploy)))
    for name in ("Chốt phiên bản và kiểm tra tài nguyên", "Đóng gói GitHub Pages", "Đánh dấu đã đóng gói"):
        expression = _step(name)["if"].replace("&&", " and ").replace("||", " or ")
        assert eval(expression, {"__builtins__": {}}, {"github": github, "steps": steps}) is packaged
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert document["jobs"]["deploy"]["if"] == "needs.build.outputs.published == 'true'"


# --- Chạy thật hai khối run: ------------------------------------------------------------------


def _bash(block: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Đúng lệnh shell GitHub dùng cho ``run:`` (bash --noprofile --norc -eo pipefail)."""
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block], cwd=cwd,
                          env={**os.environ, **env}, capture_output=True, text=True, check=False)


def test_the_sync_block_mirrors_the_branch_docs_including_deletions(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    seed = _repo(tmp_path / "seed", _ledger("2026-11-18"), [])
    (seed / "docs").mkdir()
    (seed / "docs" / "index.html").write_text("kỳ 17-11", encoding="utf-8")
    (seed / "docs" / "cu.html").write_text("trang đã gỡ", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "trang cũ")
    _git(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))
    runner = tmp_path / "runner"
    _git(tmp_path, "clone", "-q", "--depth=1", f"file://{origin}", str(runner))
    # XSMB đẩy trang mới SAU khi job Vietlott đã lấy mã.
    (seed / "docs" / "index.html").write_text("kỳ 18-11", encoding="utf-8")
    (seed / "docs" / "cu.html").unlink()
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "chore: finalize analytics 2026-11-18")
    _git(seed, "push", "-q", str(origin), "main")
    result = _bash(_step(SYNC)["run"], runner, {"GITHUB_REF_NAME": "main"})
    assert result.returncode == 0, result.stderr
    assert (runner / "docs" / "index.html").read_text(encoding="utf-8") == "kỳ 18-11"
    assert not (runner / "docs" / "cu.html").exists()


def _window_repo(tmp_path: Path, forecasts: list[str]) -> Path:
    repo = _repo(tmp_path / "kho", _ledger("2026-11-18"), forecasts)
    (repo / "scripts" / "ops").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "ops" / SCRIPT.name)
    head = _git(repo, "rev-parse", "HEAD").strip()
    (repo / ".git" / "FETCH_HEAD").write_text(f"{head}\t\tbranch 'main' of origin\n", encoding="utf-8")
    return repo


def _fake_gh(tmp_path: Path, body: str) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    gh.chmod(0o755)
    return f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


@pytest.mark.parametrize("gh_body,forecasts,deploy", [
    # API trả giờ chốt vừa xong, chưa có dự báo kỳ sau: nhường.
    ('date -u -d "-4 min" +%Y-%m-%dT%H:%M:%SZ', BOTH_18, "false"),
    # API hỏng: bước KHÔNG được đỏ, và vẫn nhường.
    ("echo 'HTTP 502' >&2; exit 1", BOTH_18, "false"),
    # Chốt kỳ đã quá trần: triển khai lại.
    ('date -u -d "-3 hours" +%Y-%m-%dT%H:%M:%SZ', BOTH_18, "true"),
    # Pipeline XSMB đã xong: triển khai.
    ('date -u -d "-4 min" +%Y-%m-%dT%H:%M:%SZ', BOTH_19, "true"),
])
def test_the_window_block_runs_as_written(tmp_path: Path, gh_body: str, forecasts: list[str], deploy: str) -> None:
    repo = _window_repo(tmp_path, forecasts)
    out = tmp_path / "github_output"
    result = _bash(_step(YIELD)["run"], repo, {
        "PATH": _fake_gh(tmp_path, gh_body), "GITHUB_OUTPUT": str(out), "GITHUB_REPOSITORY": "chu/kho",
        "GITHUB_REF_NAME": "main", "GH_TOKEN": "khong-dung",
    })
    assert result.returncode == 0, result.stderr
    assert _outputs(out)["deploy"] == deploy
    assert ("Nhường: " if deploy == "false" else "Triển khai: ") in result.stdout
