from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pages import update_readme
from web.templates import Render


def _sample_payload() -> dict:
    return {
        "anchor_date": "2026-08-31",
        "target_date": "2026-09-01",
        "disclaimer": "Dự đoán vui/mô phỏng để tham khảo.",
        "groups": [
            {
                "key": "special",
                "label": "Đặc Biệt",
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
    block = update_readme._render_fun_prediction_block(_sample_payload())
    original = (
        "# Test\n\n"
        "<!-- SNAPSHOT:BEGIN -->\nsnapshot\n<!-- SNAPSHOT:END -->\n\n"
        "<!-- FUN_PREDICTION:BEGIN -->\nold\n<!-- FUN_PREDICTION:END -->\n\n"
        "## End\n"
    )
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


def test_automation_block_replaces_legacy_schedule_and_is_idempotent() -> None:
    original = (
        "# Test\n\n"
        "## Lịch daily finalization\n\n"
        "- `18:38` — finalization chính.\n"
        "- `18:53` — recovery 1.\n\n"
        "## Dashboard\n\n"
        "dashboard text\n"
    )
    once = update_readme._replace_automation_block(original)
    twice = update_readme._replace_automation_block(once)
    assert once == twice
    assert "## Lịch daily finalization" not in once
    assert once.count("<!-- AUTOMATION:BEGIN -->") == 1
    assert once.count("<!-- AUTOMATION:END -->") == 1
    assert "18:00" in once
    assert "17:55, 18:05, 18:15, 18:25, 18:45" in once
    assert "18:30, 18:40, 18:50, 19:00, 19:10, 19:20, 19:30, 19:45, 20:00" in once
    assert "19:05, 19:25, 19:45, 20:05" in once
    assert "20:10–20:35" in once
    assert "07:15" in once


def test_automation_block_replaces_obsolete_source_policy_and_is_idempotent() -> None:
    original = (
        "# Test\n\n"
        "<!-- AUTOMATION:BEGIN -->\n"
        "Tải 7 nguồn song song, yêu cầu ≥2 nhóm nhà cung cấp độc lập.\n"
        "<!-- AUTOMATION:END -->\n\n"
        "## Bảng điều khiển\n"
    )
    once = update_readme._replace_automation_block(original)
    assert "nguồn chính; chỉ gọi dự phòng khi nguồn chính gặp sự cố" in once
    assert "yêu cầu ≥1 nhóm nhà cung cấp" in once
    assert "7 nguồn" not in once
    assert "≥2" not in once
    assert update_readme._replace_automation_block(once) == once


def test_daily_readme_template_and_automation_keep_the_current_source_policy() -> None:
    context = {
        field: 72 for _, fields in update_readme.GROUPS for field in fields
    }
    render = Render(template_dir=Path(__file__).resolve().parents[2] / "src" / "web" / "templates")
    rendered = render(
        "README.j2", date=date(2026, 10, 17), loto_result=["2"] * 10,
        max_count=1, min_count=1, mean=1, std=0, **context,
    )
    generated = update_readme._replace_automation_block(rendered)
    assert "17-10-2026" in generated
    assert "00072" in generated
    assert "Nguồn chính: `xoso.com.vn`" in generated
    assert "Dự phòng theo thứ tự ưu tiên: `mketqua.net`, rồi `www.minhngoc.net.vn`" in generated
    assert "ít nhất 1 nhóm nhà cung cấp" in generated
    assert "yêu cầu ≥1 nhóm nhà cung cấp" in generated
    assert "18:40 giờ Việt Nam" in generated
    assert "thế hòa" in generated
    assert "StalePage" in generated
    assert "7 nguồn" not in generated
    assert "ít nhất 2 nhóm" not in generated
    assert "≥2" not in generated
    assert update_readme._replace_automation_block(generated) == generated
