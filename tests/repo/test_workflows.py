from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from web.site_assets import check_site, refresh_site

ROOT = Path(__file__).resolve().parents[2]


def _text(name: str) -> str:
    return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")


def _vietnam_minutes(cron: str) -> int:
    minute, hour = cron.split()[:2]
    return ((int(hour) + 7) % 24) * 60 + int(minute)


def test_live_workflow_uses_utc_schedule_and_subminute_poll_loop() -> None:
    text = _text("live-results.yml")
    crons = re.findall(r'cron: "([^"]+)"', text)
    assert crons, "workflow live phải có ít nhất một mốc lịch"
    assert min(_vietnam_minutes(c) for c in crons) <= 14 * 60
    assert max(_vietnam_minutes(c) for c in crons) <= 18 * 60 + 15
    assert 'POLL_SECONDS: "15"' in text
    assert 'MAX_SECONDS: "3600"' in text
    assert "refs/heads/live" in text
    assert "complete_verified" in text
    assert "actions: write" in text
    assert "actions/workflows/update-data.yml/dispatches" in text
    assert "cancel-in-progress: false" in text


def test_daily_workflow_has_primary_and_recovery_finalization_times() -> None:
    text = _text("update-data.yml")
    crons = re.findall(r'cron: "([^"]+)"', text)
    assert len(crons) >= 9
    minutes = [_vietnam_minutes(c) for c in crons]
    assert min(minutes) >= 18 * 60 + 30, "mốc đầu phải sau giờ quay 18:30"
    assert max(minutes) >= 20 * 60, "cần mốc phục hồi muộn"
    assert not [c for c in crons if int(c.split()[0]) in (0, 30)]
    assert "--cutoff 18:35" in text
    assert '"--consensus-min-recent", "1"' in text
    assert "Ghi nhận kết quả chuẩn ngay lập tức" in text
    assert "--fail-on-stale" in text
    assert "--fail-on-missing" in text
    assert '--expected-date "$TARGET_DATE"' in text
    assert "push:" in text
    assert '"reason": "live_verified"' in _text("live-results.yml")


def test_watchdog_and_post_finalization_use_utc7_cutoff_and_recovery() -> None:
    watchdog = _text("watchdog.yml")
    for cron in ("55 10", "5 11", "15 11", "25 11", "45 11", "5 12", "25 12", "45 12", "5 13"):
        assert f'cron: "{cron} * * *"' in watchdog
    assert '"18:35"' in watchdog
    assert '"reason": "watchdog_recovery"' in watchdog
    assert "--cutoff 18:35" in _text("post-finalization.yml")


def test_dashboard_refresh_checks_vietnamese_contract() -> None:
    text = _text("dashboard-refresh.yml")
    for marker in ("lịch 7 cột", "Độ nâng so với nền", "Kiểm toán và liên kết chi tiết"):
        assert marker in text
    assert "Lift vs baseline" not in text


def test_daily_workflow_scopes_privileged_permissions_to_the_jobs_that_need_them() -> None:
    text = _text("update-data.yml")
    top, jobs = text.split("jobs:\n", 1)
    update, rest = jobs.split("  trigger-post-finalization:\n", 1)
    trigger, deploy = rest.split("  deploy-pages:\n", 1)

    assert "permissions:\n  contents: read" in top
    assert "    permissions:\n      contents: write" in update
    assert "    permissions:\n      actions: write\n      contents: read" in trigger
    assert (
        "    permissions:\n      contents: read\n      id-token: write\n      pages: write"
    ) in deploy


def test_pages_use_official_actions_deployment_flow() -> None:
    page = _text("pages.yml")
    daily = _text("update-data.yml")
    for text in (page, daily):
        assert "actions/configure-pages@v6" in text
        assert "actions/upload-pages-artifact@v5" in text
        assert "actions/deploy-pages@v5" in text


def test_production_refreshes_do_not_restore_package_caches() -> None:
    for name in ("ci.yml", "live-results.yml", "update-data.yml", "dashboard-refresh.yml"):
        text = _text(name)
        assert "cache:" not in text
        assert "--no-cache-dir" in text


def test_cache_purge_is_explicit_and_not_scheduled() -> None:
    text = _text("cache-purge.yml")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "actions: write" in text
    assert "scripts/ops/purge_github_caches.py --confirm" in text


def test_regional_workflow_refreshes_pages_through_the_shared_pipeline(tmp_path: Path) -> None:
    workflow = yaml.safe_load(_text("regional-results.yml"))
    steps = workflow["jobs"]["sync"]["steps"]
    step = next(step for step in steps if "src/pages/build_regional_results.py" in step.get("run", ""))
    assert "wrap_page" not in step["run"]
    assert "app_shell" not in step["run"]

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$PYTHON_CALLS"\n')
    fake_python.chmod(0o755)
    calls = tmp_path / "python-calls"
    env = dict(os.environ, PATH=f"{fake_bin}:{os.environ['PATH']}", PYTHON_CALLS=str(calls))
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert calls.read_text().splitlines() == [
        "src/pages/build_regional_results.py", "scripts/web/refresh_navigation.py"
    ]


@pytest.mark.parametrize("with_station_analysis", [True, False])
def test_regional_workflow_commits_html_and_its_refreshed_asset_bundle(
    tmp_path: Path, with_station_analysis: bool
) -> None:
    workflow = yaml.safe_load(_text("regional-results.yml"))
    steps = workflow["jobs"]["sync"]["steps"]
    step = next(step for step in steps if "git add data/regions/" in step.get("run", ""))
    remote = tmp_path / "remote.git"
    repo = tmp_path / "writer"
    subprocess.run(["git", "init", "--bare", "-q", "--initial-branch=main", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(repo)], check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True,
        ).stdout.strip()

    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.test")
    infrastructure = {"scripts/ops/push_generated_site.py", "src/web/site_assets.py"}
    for relative in infrastructure:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)

    contents = {
        "data/regions/xsmt.csv": "date,version\n2026-10-17,new\n",
        "data/regions/xsmt.json": '{"region":"xsmt","version":"new"}\n',
        "data/regions/xsmn.csv": "date,version\n2026-10-17,new\n",
        "data/regions/xsmn.json": '{"region":"xsmn","version":"new"}\n',
        "docs/index.html": ('<!doctype html><html><head><link rel="stylesheet" href="assets/ui.css">'
                            '<script src="assets/app-shell.js"></script></head>'
                            '<body><p>new</p></body></html>'),
        "docs/assets/app-shell.js": 'const revision = "new";\n',
        "docs/assets/ui.css": '/* new */ body { color: inherit; }\n',
        "docs/assets/icons/probe.svg": '<svg xmlns="http://www.w3.org/2000/svg"><desc>new</desc></svg>\n',
    }
    if with_station_analysis:
        contents.update({
            "data/stats/regional/summary_mn.json": '{"version":"new"}\n',
            "data/stats/regional/frequency_mn.csv": "number,version\n00,new\n",
            "data/evaluation/regional_benchmark/benchmark.json": '{"version":"new"}\n',
            "data/research/hypotheses/regional_cage_bias.json": '{"version":"new"}\n',
            "data/research/hypotheses/regional_cage_bias.csv": "id,version\n1,new\n",
        })
    for relative, value in contents.items():
        if relative.endswith("probe.svg"):
            continue
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value.replace("new", "old"), encoding="utf-8")
    refresh_site(repo / "docs")
    git("add", ".")
    git("commit", "-qm", "Hạ tầng và gói trang ban đầu")
    git("push", "-q", "origin", "main")
    before = git("rev-parse", "HEAD")
    assert git("status", "--porcelain") == ""

    for relative, value in contents.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8")
    refresh_site(repo / "docs")
    expected = set(contents) | {"docs/assets/release.json"}
    expected_bytes = {relative: (repo / relative).read_bytes() for relative in expected}
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("status", "--porcelain") == ""
    assert git("rev-parse", "HEAD") == git("rev-parse", "origin/main")
    assert set(git("diff", "--name-only", before, "origin/main").splitlines()) == expected
    assert set(git("ls-tree", "--name-only", "-r", "origin/main").splitlines()) == expected | infrastructure

    published = tmp_path / "published"
    subprocess.run(["git", "clone", "-q", str(remote), str(published)], check=True)
    for relative, value in expected_bytes.items():
        assert (published / relative).read_bytes() == value, relative
    assert check_site(published / "docs") == []


def test_daily_update_prefers_dispatch_over_schedule() -> None:
    text = _text("daily_update.yml")
    assert "repository_dispatch:" in text
    assert "types: [daily-collect]" in text
    crons = re.findall(r'cron: "([^"]+)"', text)
    assert len(crons) <= 8, "quá nhiều mốc chỉ tăng số lần chạy thừa"


MEASURED_DELAYS = [
    ("09-10", 263, 307, 257), ("09-11", 261, 307, 250), ("09-12", 256, 274, 211),
    ("09-13", 268, 337, 277), ("09-14", 277, 398, 384), ("09-15", 276, 325, 302),
    ("09-16", 271, 321, 294), ("09-17", 274, 322, 297), ("09-18", 265, 304, 259),
    ("09-19", 259, 288, 230), ("09-20", 276, 308, 262), ("09-21", 277, 398, 389),
    ("09-22", 276, 322, 290), ("09-23", 267, 325, 301), ("09-24", 271, 330, 297),
    ("09-25", 279, 330, 320), ("09-26", 279, 305, 272), ("09-27", 300, 345, 328),
    ("09-28", 304, 466, 491), ("09-29", 325, 398, 376), ("09-30", 314, 379, 390),
    ("10-01", 332, 432, 410), ("10-02", 317, 387, 372), ("10-03", 299, 320, 305),
    ("10-04", 333, 371, 333), ("10-05", 319, 514, None),
]
UTC_MIDNIGHT_VN = 17 * 60


def _utc_minutes(name: str) -> list[int]:
    crons = re.findall(r'cron: "([^"]+)"', _text(name))
    return [int(c.split()[1]) * 60 + int(c.split()[0]) for c in crons]


REDUNDANT_SLOTS = 3


def _slots_landing_in(slots: list[int], low: int, high: int, delay: int) -> int:
    return sum(low <= slot + delay <= high for slot in slots)


@pytest.mark.parametrize(
    "name, window, cap",
    [
        ("daily_update.yml", 11 * 60 + 15, "daily"),
        ("live-results.yml", 11 * 60 + 8, "live"),
    ],
)
def test_some_slot_lands_in_the_waiting_window_on_every_measured_day(name, window, cap) -> None:
    slots = _utc_minutes(name)
    wait = _wait_cap_minutes(cap)
    low, high = window - wait, 11 * 60 + 35
    missed = []
    for day, early, mid, _ in MEASURED_DELAYS:
        for delay in range(min(early, mid), max(early, mid) + 1):
            if _slots_landing_in(slots, low, high, delay) < REDUNDANT_SLOTS:
                missed.append((day, delay))
                break
    assert not missed, f"ngày có ít hơn {REDUNDANT_SLOTS} mốc rơi vào khung chờ: {missed}"
    assert _slots_landing_in(slots, low, window, 0), "GitHub đúng giờ thì không mốc nào chờ được"


def _wait_cap_minutes(which: str) -> int:
    if which == "daily":
        return int(re.search(r'MAX_WAIT_MINUTES:\s*"(\d+)"', _text("daily_update.yml")).group(1))
    found = re.search(r"max_wait_seconds=\$\(\(\s*(\d+)\s*\*\s*60\s*\)\)", _text("live-results.yml"))
    return int(found.group(1))


def test_the_last_backstop_fires_before_midnight_even_at_the_worst_measured_delay() -> None:
    last = _utc_minutes("daily_update.yml")[-1]
    worst = max(late for *_, late in MEASURED_DELAYS if late is not None)
    assert last + worst < UTC_MIDNIGHT_VN


def test_early_arrivals_exit_instead_of_idling_the_runner() -> None:
    text = _text("daily_update.yml")
    found = re.search(r'MAX_WAIT_MINUTES:\s*"(\d+)"', text)
    assert found is not None, "thiếu trần chờ MAX_WAIT_MINUTES cho job đến quá sớm"

    cap = int(found.group(1))
    timeout = int(re.search(r"timeout-minutes:\s*(\d+)", text).group(1))
    poll_window = 75

    assert timeout >= cap + poll_window, (
        f"timeout {timeout} phút không đủ cho trần chờ {cap} cộng khung thăm dò "
        f"{poll_window}; job sẽ bị giết giữa chừng"
    )


def test_gate_skips_when_todays_draw_is_already_stored() -> None:
    text = _text("daily_update.yml")
    assert "data/xsmb.csv" in text
    assert "run=false" in text
    assert "steps.gate.outputs.run == 'true'" in text


def test_last_backstop_guard_matches_the_actual_last_cron() -> None:
    text = _text("daily_update.yml")
    crons = re.findall(r'cron: "([^"]+)"', text)
    guard = re.search(r'LAST_CRON:\s*"([^"]+)"', text)
    assert guard, "thiếu hằng số LAST_CRON"
    assert guard.group(1) == crons[-1], (
        f"LAST_CRON={guard.group(1)!r} không khớp mốc cuối {crons[-1]!r}"
    )


def test_missing_data_at_the_last_backstop_fails_the_job() -> None:
    text = _text("daily_update.yml")
    assert "::error::" in text
    assert re.search(r'FIRED_CRON.*=.*LAST_CRON|"\$FIRED_CRON"\s*=\s*"\$LAST_CRON"', text)
    assert "exit 1" in text


def test_daily_update_sets_the_timezone_at_job_level() -> None:
    text = _text("daily_update.yml")
    assert "TZ: Asia/Ho_Chi_Minh" in text


def test_daily_update_bounds_the_runner() -> None:
    text = _text("daily_update.yml")
    assert re.search(r"timeout-minutes:\s*\d+", text)


def test_every_dock_page_builder_runs_in_the_release_chain() -> None:
    chain = (
        Path(__file__).resolve().parents[2] / "scripts" / "release" / "release_check.sh"
    ).read_text(encoding="utf-8")

    builders = [
        "build_docs.py",
        "build_docs_ml.py",
        "build_dashboard.py",
        "build_statistics_dashboard.py",
        "build_landing_page.py",
        "build_fun_prediction.py",
        "build_traditional_results.py",
    ]
    lines = {line.strip() for line in chain.splitlines()}
    for name in builders:
        assert f"python src/pages/{name}" in lines, f"{name} không nằm trong chuỗi phát hành"

    assert chain.index("python src/pages/build_docs.py") < chain.index(
        "python src/pages/build_landing_page.py"
    ), "build_docs phải chạy trước build_landing_page, nếu không index.html bị ghi đè sai"


def test_builders_let_callers_redirect_their_output() -> None:
    root = Path(__file__).resolve().parents[2]
    required = {
        "build_dashboard.py": "--docs-dir",
        "build_stat_pages.py": "--docs-dir",
        "build_markdown_dashboard_v3.py": "--output",
        "build_domain_experiment_report.py": "--output",
    }
    for name, flag in required.items():
        source = (root / "src" / "pages" / name).read_text(encoding="utf-8")
        assert f'"{flag}"' in source, f"{name} thiếu {flag}"

    landing = (root / "src" / "pages" / "build_landing_page.py").read_text(encoding="utf-8")
    assert "docs_dir: Path | None = None" in landing, (
        "build_landing_page phải nhận docs_dir để tách nơi ghi khỏi nơi đọc"
    )


def test_no_test_builds_into_the_repository_docs_tree() -> None:
    root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    test_files = sorted((root / "tests").rglob("test_*.py"))
    assert len(test_files) > 100, len(test_files)
    for path in test_files:
        text = path.read_text(encoding="utf-8")
        for builder, flag in (
            ("src/pages/build_dashboard.py", "--docs-dir"),
            ("src/pages/build_markdown_dashboard_v3.py", "--output"),
            ("src/pages/build_domain_experiment_report.py", "--output"),
        ):
            for line_no, line in enumerate(text.splitlines(), 1):
                if builder not in line:
                    continue
                window = "\n".join(text.splitlines()[line_no - 1 : line_no + 6])
                if flag not in window:
                    offenders.append(f"{path.name}:{line_no} gọi {builder} không kèm {flag}")
    assert not offenders, "test ghi thẳng vào kho: " + "; ".join(offenders)


import ast
import sys

SRC = ROOT / "src"

_IMPORT_TO_DISTRIBUTION = {
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "dateutil": "python-dateutil",
    "PIL": "pillow",
    "cv2": "opencv-python",
}


_LOCAL_PROJECTS = {"vietlott": {"vietlott_engine", "vlm"}}


def _resolve_local(module: str, *search: Path) -> Path | None:
    for directory in search:
        for candidate in (directory / f"{module}.py", directory / module / "__init__.py"):
            if candidate.is_file():
                return candidate
    return None


def _local_modules(dotted: str, *search: Path) -> list[Path] | None:
    parts = dotted.split(".")
    for directory in search:
        if _resolve_local(parts[0], directory) is None:
            continue
        files: list[Path] = []
        base = directory
        for part in parts:
            candidate = _resolve_local(part, base)
            if candidate is None:
                break
            files.append(candidate)
            base = base / part
        return files
    return None


def _third_party_closure(path: Path, seen: set[Path] | None = None) -> set[str]:
    seen = set() if seen is None else seen
    if path in seen:
        return set()
    seen.add(path)

    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            targets = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
        else:
            continue
        for dotted in targets:
            root = dotted.split(".")[0]
            if root in sys.stdlib_module_names:
                continue
            local = _local_modules(dotted, path.parent, SRC)
            if local is None:
                found.add(_IMPORT_TO_DISTRIBUTION.get(root, root).lower())
                continue
            for module in local:
                found |= _third_party_closure(module, seen)
    return found


def _requirement_names(name: str, seen: set[str] | None = None) -> set[str]:
    seen = set() if seen is None else seen
    if name in seen:
        return set()
    seen.add(name)
    path = ROOT / name
    if not path.is_file():
        return set()
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        if line.startswith("-r "):
            names |= _requirement_names(line[3:].strip(), seen)
            continue
        names.add(re.split(r"[<>=!~\[]", line)[0].strip().lower())
    return names


def _installed_by(run_text: str) -> set[str]:
    installed: set[str] = set()
    for match in re.finditer(r"pip install([^\n]*)", run_text):
        args = match.group(1)
        for req in re.findall(r"-r\s+(\S+)", args):
            installed |= _requirement_names(req)
        for token in args.split():
            token = token.strip("\"'")
            if token.startswith("-") or "/" in token:
                continue
            if token in {"pip", "wheel", "setuptools"}:
                continue
            if token.rstrip("/") in _LOCAL_PROJECTS:
                installed |= _LOCAL_PROJECTS[token.rstrip("/")]
                continue
            installed.add(re.split(r"[<>=!~\[]", token)[0].strip().lower())
    return installed


def _jobs_running_python() -> list[tuple[str, str, set[Path], set[str]]]:
    import yaml

    out: list[tuple[str, str, set[Path], set[str]]] = []
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        document = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for job_name, job in (document.get("jobs") or {}).items():
            run_text = "\n".join(
                step["run"]
                for step in (job or {}).get("steps", [])
                if isinstance(step, dict) and isinstance(step.get("run"), str)
            )
            scripts = {
                ROOT / rel
                for rel in set(re.findall(r"(src/[\w/]+\.py)", run_text))
                if (ROOT / rel).is_file()
            }
            if scripts:
                out.append((workflow.name, job_name, scripts, _installed_by(run_text)))
    return out


def test_the_closure_follows_a_dotted_module_into_its_package(tmp_path: Path) -> None:
    package = tmp_path / "goi"
    package.mkdir()
    (package / "__init__.py").write_text('"""Gói."""\n', encoding="utf-8")
    (package / "nguon.py").write_text("import bs4\n", encoding="utf-8")
    (package / "khung.py").write_text("import yaml\n", encoding="utf-8")
    script = tmp_path / "chay.py"
    script.write_text("from goi.nguon import X\nfrom goi import khung\nimport numpy.linalg\n", encoding="utf-8")
    assert _third_party_closure(script) == {"beautifulsoup4", "pyyaml", "numpy"}


def test_the_audit_actually_finds_the_jobs_that_run_python() -> None:
    seen = {(workflow, job) for workflow, job, _, _ in _jobs_running_python()}
    for expected in (
        ("post-finalization.yml", "reconcile"),
        ("daily_update.yml", "collect"),
        ("watchdog.yml", "audit-and-recover"),
    ):
        assert expected in seen, (expected, sorted(seen))


def test_the_install_parser_reads_quoted_requirement_specs() -> None:
    assert _installed_by('python -m pip install "numpy==2.2.6" \'scipy>=1.10,<2.0\' pandas') == {
        "numpy",
        "scipy",
        "pandas",
    }


def test_local_projects_really_provide_the_packages_they_are_credited_with() -> None:
    for directory, packages in _LOCAL_PROJECTS.items():
        assert (ROOT / directory / "pyproject.toml").is_file(), directory
        for package in packages:
            assert (ROOT / directory / "src" / package / "__init__.py").is_file(), (directory, package)
    assert _installed_by("python -m pip install --no-cache-dir -e vietlott") == {"vietlott_engine", "vlm"}


def test_every_workflow_installs_what_its_python_scripts_import() -> None:
    offenders: list[str] = []
    for workflow, job_name, scripts, installed in _jobs_running_python():
        needed: set[str] = set()
        for script in scripts:
            needed |= _third_party_closure(script)
        missing = sorted(needed - installed)
        if missing:
            offenders.append(f"{workflow}:{job_name} thiếu {missing}")
    assert not offenders, "workflow chạy Python mà không cài đủ: " + "; ".join(offenders)
