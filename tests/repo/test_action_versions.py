from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def action_versions(workflows: dict[str, dict]) -> dict[str, dict[str, set[str]]]:
    seen: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for name, workflow in workflows.items():
        for job in (workflow.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                uses = str(step.get("uses") or "")
                if "@" in uses and not uses.startswith(("./", "docker://")):
                    action, version = uses.rsplit("@", 1)
                    seen[action][version].add(name)
    return seen


def drift(workflows: dict[str, dict]) -> dict[str, dict[str, list[str]]]:
    return {action: {version: sorted(names) for version, names in sorted(versions.items())}
            for action, versions in action_versions(workflows).items() if len(versions) > 1}


def test_every_action_runs_one_version_in_every_workflow():
    workflows = {path.name: yaml.safe_load(path.read_text(encoding="utf-8")) for path in WORKFLOWS}
    assert len(action_versions(workflows)) >= 5, "tập action rỗng: phép kiểm không còn đọc được workflow"
    assert drift(workflows) == {}


def test_the_drift_rule_itself_catches_two_versions():
    def workflow(*uses):
        return {"jobs": {"j": {"steps": [{"uses": u} for u in uses]}}}

    sample = {
        "a.yml": workflow("actions/upload-artifact@v7", "actions/checkout@v7", "./local-action"),
        "b.yml": workflow("actions/upload-artifact@v6", "actions/checkout@v7"),
    }
    assert drift(sample) == {"actions/upload-artifact": {"v6": ["b.yml"], "v7": ["a.yml"]}}
    assert drift({"a.yml": sample["a.yml"]}) == {}
