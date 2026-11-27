from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("workflow_map", ROOT / "scripts/ops/workflow_map.py")
MAP = importlib.util.module_from_spec(SPEC)
sys.modules["workflow_map"] = MAP
SPEC.loader.exec_module(MAP)


def test_the_published_map_matches_the_workflows():
    text = MAP.DOC.read_text(encoding="utf-8")
    assert MAP.updated_document(text, MAP.load()) == text, "chạy: python3 scripts/ops/workflow_map.py --write"


def test_every_link_between_workflows_points_at_something_real():
    workflows = MAP.load()
    assert len(workflows) == len(list((ROOT / ".github/workflows").glob("*.yml"))) > 20
    assert MAP.broken_links(workflows) == []


def _write(folder: Path, file: str, body: str) -> None:
    (folder / file).write_text(body, encoding="utf-8")


def test_the_link_rules_catch_each_kind_of_break(tmp_path):
    _write(tmp_path, "source.yml", "name: Nguồn\non:\n  workflow_dispatch:\njobs: {}\n")
    _write(tmp_path, "follower.yml", "name: Theo\non:\n  workflow_run:\n    workflows: [Nguồn]\n    types: [completed]\njobs: {}\n")
    _write(tmp_path, "caller.yml", "name: Gọi\non: push\njobs:\n  a:\n    steps:\n"
                                   "      - run: curl -X POST $API/actions/workflows/source.yml/dispatches\n")
    assert MAP.broken_links(MAP.load(tmp_path)) == []

    _write(tmp_path, "typo.yml", "name: Sai\non:\n  workflow_run:\n    workflows: [Nguon]\njobs: {}\n")
    _write(tmp_path, "renamed.yml", "name: Đổi\non: push\njobs:\n  a:\n    steps:\n"
                                    "      - run: python -c \"dispatch('old-name.yml')\"\n")
    _write(tmp_path, "closed.yml", "name: Đóng\non: push\njobs: {}\n")
    _write(tmp_path, "needs-dispatch.yml", "name: Cần\non: push\njobs:\n  a:\n    steps:\n"
                                           "      - run: curl $API/actions/workflows/closed.yml/dispatches\n")
    _write(tmp_path, "ping.yml", "name: Ping\non:\n  workflow_run:\n    workflows: [Pong]\njobs:\n  a:\n    steps:\n"
                                 "      - run: curl $API/actions/workflows/pong.yml/dispatches\n")
    _write(tmp_path, "pong.yml", "name: Pong\non:\n  workflow_dispatch:\njobs: {}\n")
    problems = "\n".join(MAP.broken_links(MAP.load(tmp_path)))
    assert "typo.yml: workflow_run theo 'Nguon'" in problems
    assert "renamed.yml: gọi old-name.yml" in problems
    assert "closed.yml không khai workflow_dispatch" in problems
    assert "vòng kích hoạt" in problems and "ping.yml" in problems and "pong.yml" in problems


def test_every_external_timer_event_is_documented_for_the_owner():
    docs = "".join((ROOT / "documentation/operations" / name).read_text(encoding="utf-8")
                   for name in ("scheduling.md", "on-time-trigger.md"))
    types = {kind for w in MAP.load().values() for kind in w.dispatch_types}
    assert types, "không đọc được repository_dispatch nào — luật đang quét trên rỗng"
    assert sorted(kind for kind in types if re.search(rf"(?<![\w-]){re.escape(kind)}(?![\w-])", docs) is None) == []
