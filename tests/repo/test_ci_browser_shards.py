"""Job Chromium của CI chạy song song ba nhóm mà KHÔNG bỏ sót phép kiểm nào của job một khối cũ.

Ngày 05-11-2026 job một khối mất 22–29 phút (trần 40), riêng Vietlott UI 12 phút 17 giây; nay chia
thành ba nhóm. Chia nhóm dễ làm rơi một bước hay một nửa trạng thái mà CI vẫn xanh, nên phép kiểm này
ghim: mọi kịch bản cũ còn chạy, hai nửa Vietlott phủ đủ 8 trạng thái và không trùng, và job gác giữ
đúng tên kiểm cũ.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
OLD_STEPS = (
    "tests/web/test_app_shell.py::test_touch_can_reach_every_navigation_link_on_a_phone",
    "scripts/browser/check_ui_browser.py",
    "scripts/browser/check_dashboard_browser.py",
    "scripts/browser/check_vietlott_navigation_browser.py",
    "scripts/browser/check_vietlott_ui_browser.py",
    "scripts/browser/check_stat_tables_browser.py",
    "scripts/browser/check_bridge_workspace_browser.py",
)


def _jobs() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]


def _shard_states():
    source = (ROOT / "scripts" / "browser" / "check_vietlott_ui_browser.py").read_text(encoding="utf-8")
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == "shard_states")
    namespace: dict = {}
    exec(compile(ast.Module([function], []), "shard_states", "exec"), namespace)  # noqa: S102
    return namespace["shard_states"]


def test_every_browser_check_of_the_old_job_still_runs() -> None:
    steps = _jobs()["browser"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    missing = [script for script in OLD_STEPS if script not in commands]
    assert not missing, f"Nhóm Chromium bỏ sót: {missing}"
    shards = {entry["id"] for entry in _jobs()["browser"]["strategy"]["matrix"]["shard"]}
    for step in steps:
        condition = step.get("if", "")
        if "matrix.shard.id ==" in condition:
            wanted = condition.split("==")[1].strip().strip("'")
            assert wanted in shards, f"bước chạy cho nhóm không tồn tại: {condition}"


def test_the_vietlott_halves_cover_every_state_exactly_once() -> None:
    entries = _jobs()["browser"]["strategy"]["matrix"]["shard"]
    specs = [entry["ui_shard"] for entry in entries if "ui_shard" in entry]
    shard_states = _shard_states()
    covered = [state for spec in specs for state in shard_states(spec)]
    assert sorted(covered) == sorted(shard_states(None)), "hai nửa phải phủ đủ, không trùng, 8 trạng thái"
    vietlott = next(step for step in _jobs()["browser"]["steps"]
                    if "check_vietlott_ui_browser.py" in step.get("run", ""))
    assert vietlott["env"]["UI_SHARD"] == "${{ matrix.shard.ui_shard }}"


def test_the_gate_keeps_the_old_check_name_and_needs_every_shard() -> None:
    gate = _jobs()["browser-gate"]
    assert gate["name"] == "Giao diện Chromium sáng/tối và mobile"
    assert gate["needs"] == ["route", "browser"]
    assert gate["if"].startswith("always() &&")
    assert 'test "${RESULT}" = "success"' in gate["steps"][0]["run"]
    assert gate["steps"][0]["env"]["RESULT"] == "${{ needs.browser.result }}"
    assert _jobs()["browser"]["strategy"]["fail-fast"] is False
