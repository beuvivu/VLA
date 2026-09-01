from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import update_readme


def _sample_payload() -> dict:
    return {
        "anchor_date": "2026-08-31",
        "target_date": "2026-09-01",
        "disclaimer": "Dự đoán vui/mô phỏng để tham khảo.",
        "groups": [
            {
                "key": "special",
                "label": "Đặc biệt",
                "values": [{"value": "30972", "suffix": "72", "model_prob_percent": 1.01}],
            },
            {
                "key": "prize1",
                "label": "Giải nhất",
                "values": [{"value": "60647", "suffix": "47", "model_prob_percent": 23.94}],
            },
        ],
        "top_loto": [
            {"rank": 1, "number": "77", "prob_percent": 24.97},
            {"rank": 2, "number": "83", "prob_percent": 24.94},
        ],
        "top_de": [
            {"rank": 1, "number": "83", "prob_percent": 1.216},
            {"rank": 2, "number": "38", "prob_percent": 1.180},
        ],
    }


def test_render_fun_prediction_block_contains_key_sections() -> None:
    block = update_readme._render_fun_prediction_block(_sample_payload())
    assert "<!-- FUN_PREDICTION:BEGIN -->" in block
    assert "Dự đoán vui ngày 01-09-2026" in block
    assert "30972" in block
    assert "**77**" in block
    assert "**83**" in block
    assert "24.97%" in block
    assert "1.216%" in block
    assert "<!-- FUN_PREDICTION:END -->" in block


def test_replace_fun_block_is_idempotent() -> None:
    payload = _sample_payload()
    block = update_readme._render_fun_prediction_block(payload)
    original = "# Test\n\n## Latest data snapshot\n\n<!-- FUN_PREDICTION:BEGIN -->\nold\n<!-- FUN_PREDICTION:END -->\n\n## End\n"
    once = update_readme._replace_fun_prediction_block(original, block)
    twice = update_readme._replace_fun_prediction_block(once, block)
    assert once == twice
    assert once.count("<!-- FUN_PREDICTION:BEGIN -->") == 1
    assert once.count("<!-- FUN_PREDICTION:END -->") == 1


def test_load_fun_payload(tmp_path: Path) -> None:
    path = tmp_path / "fun.json"
    path.write_text(json.dumps(_sample_payload(), ensure_ascii=False), encoding="utf-8")
    payload = update_readme._load_fun_prediction(path)
    assert payload["target_date"] == "2026-09-01"
