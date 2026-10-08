"""Mọi mức khớp của mã trình duyệt phải cùng phân hạng với engine."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import build_vietlott_results as builder


def test_browser_comparison_matches_engine_for_every_possible_hit_count() -> None:
    node = shutil.which("node")
    assert node, "Cần Node để kiểm tra logic đối chiếu đã xuất bản"
    cases = []
    expected = []
    with builder._engine_importable():
        from vietlott_engine.core.games import get_game

        for product, total in (("mega645", 6), ("power655", 6), ("lotto535", 5)):
            for hits in range(total + 1):
                bonus_states = (False,) if product == "mega645" or (product == "power655" and hits == total) else (False, True)
                for bonus_hit in bonus_states:
                    actual = list(range(1, total + 1))
                    predicted = actual[:hits] + list(range(total + 1, 2 * total - hits + 1))
                    options = {}
                    if product == "power655":
                        options["actualBonus"] = 30
                        if bonus_hit:
                            predicted[-1] = 30
                    elif product == "lotto535":
                        options = {"actualBonus": 9, "predictedBonus": 9 if bonus_hit else 10}
                    cases.append([product, predicted, actual, options])
                    tier = get_game(product).classify(hits, bonus_hit)
                    expected.append((hits, total, bonus_hit, tier.name if tier else None))
    script = """
const fs = require('node:fs'), vm = require('node:vm');
const context = { window: {}, document: { querySelectorAll: () => [], addEventListener: () => {} } };
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(cases.map(args => context.window.vietlottComparison.comparePrediction(...args))));
"""
    path = Path(builder.__file__).parent / "assets/vietlott-comparison.js"
    run = subprocess.run([node, "-e", script, str(path)], input=json.dumps(cases),
                         text=True, capture_output=True, check=True)
    for case, result, (hits, total, bonus_hit, tier) in zip(cases, json.loads(run.stdout), expected, strict=True):
        assert (result["hits"], result["total"], result["bonusMatched"], result["tier"]) == (hits, total, bonus_hit, tier), case
        assert result["accuracy"] == pytest.approx(hits / total * 100), case
