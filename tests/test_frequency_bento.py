"""Demo data must be explicit, deterministic and isolated from real XSMB draws."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("query,enabled", [("", False), ("?demo=1", True)])
def test_demo_preserves_canonical_history_and_complete_draws(query: str, enabled: bool) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the browser data fixture")
    script = """
const fs = require('node:fs');
const vm = require('node:vm');
const canonical = [{d:'2026-09-14',s:'12345',n:['45']}];
const window = {__D_DRAWS__:canonical};
const context = {window,location:{search:process.argv[1]},URLSearchParams};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
console.log(JSON.stringify({same:window.__D_DRAWS__===canonical,
  demo:window.__D_DEMO_DRAWS__||null}));
"""
    run = subprocess.run(
        [node, "-e", script, query, str(ROOT / "src/templates/frequency_demo.js")],
        check=True, capture_output=True, text=True, timeout=10,
    )
    result = json.loads(run.stdout)
    assert result["same"] is True
    if not enabled:
        assert result["demo"] is None
        return
    rows = result["demo"]
    assert len(rows) == 45
    assert len({row["d"] for row in rows}) == len(rows)
    assert all(len(row["n"]) == 27 for row in rows)
    assert all(row["n"][0] == row["s"][-2:] for row in rows)
    # Both even and odd demo days retain every tier outside the priority star.
    tiers = {
        row["n"].count(f"{number:02d}")
        for row in rows for number in range(100)
        if f"{number:02d}" != row["s"][-2:]
    }
    assert {0, 1, 2, 3, 4, 5}.issubset(tiers)
