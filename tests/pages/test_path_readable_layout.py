"""Đường cầu phải truy được ngày nguồn, vị trí và kết quả, kể cả số 0 đầu."""

import json

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
import pandas as pd
import pytest

from core.path_models import FIELD_WIDTHS
from pages import build_docs as page


def _frames():
    raw = []
    for day, special in [("2026-01-01", 7123), ("2026-01-02", 63555), ("2026-01-03", 10107)]:
        raw.append({"date": day, **dict.fromkeys(dict(FIELD_WIDTHS), 0), "special": special})
    paths = pd.DataFrame([{"lag": 2, "i": 0, "j": 1, "p_mean": .4, "p_next": .0123,
                           "current_streak": 0, "max_streak": 3, "next_day_pred": 63,
                           "2026-01-03_num": 7, "2026-01-03_hit": 1, "2026-01-03_is_de": 1}])
    return pd.DataFrame(raw), paths


def _render(tmp_path, *, empty=False, frames=None):
    raw, paths = frames if frames is not None else _frames()
    target = tmp_path / "soi-path-de-active.html"
    page._render_page(Environment(loader=FileSystemLoader(str(page.TEMPLATES))),
                      out_path=target, title="Cầu Đặc Biệt đang chạy", mode="de", kind="active",
                      other_link="soi-path-de-stable.html", other_kind_label="Ổn định",
                      other_mode_label="Đặc Biệt", index_link="index.html", anchor_date="2026-01-03",
                      display_days=1, ui_df=paths.iloc[:0] if empty else paths,
                      picks_df=pd.DataFrame() if empty else pd.DataFrame([{
                          "number": 63, "prob": .0123, "support_paths_count": 71}]), raw_df=raw,
                      empty_reason={"threshold": 3, "is_de": True, "baseline_pct": 1,
                                    "chance_pct": .0001, "sibling_rows": 200,
                                    "sibling_link": "soi-path-de-stable.html", "sibling_label": "Ổn định"})
    return BeautifulSoup(target.read_text(), "html.parser")


def test_detail_joins_exact_source_day_and_preserves_forecast_and_zeroes(tmp_path):
    soup = _render(tmp_path)
    payload = json.loads(soup.select_one("#path-data").string)
    row = payload["rows"][0]
    assert row["next_num"] == "63"
    assert row["p_next"] == .0123
    cell = row["cells"][0]
    assert (cell["source_date"], cell["target_date"], cell["num"]) == ("2026-01-01", "2026-01-03", "07")
    assert cell["source_a"]["value"] == "07123"
    assert cell["source_a"]["digit"] == "0" and cell["source_b"]["digit"] == "7"
    assert cell["actual_special"] == "10107" and cell["state"] == "hit-de"
    forecast = row["forecast"]
    assert forecast["source_date"] == "2026-01-02" and forecast["target_date"] == "2026-01-04"
    assert forecast["num"] == "63" and forecast["state"] == "future"
    assert soup.select_one("#path-detail") is not None
    assert soup.select_one("button.quick-pick[data-path-number='63']") is not None
    assert "71 đường cầu" in soup.get_text(" ", strip=True)
    assert "đang hiển thị" in soup.get_text(" ", strip=True)
    assert not soup.select("[title]")


def test_empty_active_page_is_useful_without_fabricating_paths(tmp_path):
    soup = _render(tmp_path, empty=True)
    payload = json.loads(soup.select_one("#path-data").string)
    assert payload["rows"] == []
    assert "chưa có đường cầu nối đủ 3 kỳ liên tiếp" in soup.select_one(".ui-empty").get_text(" ", strip=True).lower()
    assert soup.select_one(".ui-empty a[href='soi-path-de-stable.html']") is not None
    assert soup.select_one("#path-number-filter") is None


def test_missing_source_day_is_explicit_instead_of_using_nearest_draw(tmp_path):
    raw, paths = _frames()
    paths.loc[0, "lag"] = 3
    paths.loc[0, "next_day_pred"] = 7
    payload = page._path_payload(paths, raw, anchor_date="2026-01-03", mode="de", kind="active")
    cell = payload["rows"][0]["cells"][0]
    assert cell["source_date"] == "2025-12-31" and cell["source_a"] is None
    assert cell["num"] == "07"
    assert cell["state"] == "unknown"


def test_missing_actual_or_number_stays_unknown_not_a_loss():
    raw, paths = _frames()
    missing_actual = raw[raw["date"] != "2026-01-03"]
    cell = page._path_payload(paths, missing_actual, anchor_date="2026-01-03", mode="de", kind="active")["rows"][0]["cells"][0]
    assert cell["state"] == "unknown" and cell["count"] is None and cell["actual_special"] is None
    paths.loc[0, "2026-01-03_num"] = float("nan")
    cell = page._path_payload(paths, raw, anchor_date="2026-01-03", mode="de", kind="active")["rows"][0]["cells"][0]
    assert cell["state"] == "unknown" and cell["num"] is None and cell["count"] is None


def test_render_missing_history_flags_does_not_crash_before_unknown_state(tmp_path):
    raw, paths = _frames()
    for column in ["2026-01-03_num", "2026-01-03_hit", "2026-01-03_is_de"]:
        paths.loc[0, column] = float("nan")
    soup = _render(tmp_path, frames=(raw, paths))
    cell = json.loads(soup.select_one("#path-data").string)["rows"][0]["cells"][0]
    assert cell["state"] == "unknown" and cell["num"] is None and cell["count"] is None


def test_missing_raw_field_is_not_replaced_by_zero_and_future_is_not_read():
    raw, paths = _frames()
    raw.loc[0, "special"] = float("nan")
    extra = raw.iloc[1].copy()
    extra["date"] = "2026-01-04"
    raw = pd.concat([raw, pd.DataFrame([extra])], ignore_index=True)
    row = page._path_payload(paths, raw, anchor_date="2026-01-03", mode="de", kind="active")["rows"][0]
    assert row["cells"][0]["source_a"] is None and row["cells"][0]["state"] == "unknown"
    assert row["forecast"]["state"] == "future"
    assert row["forecast"]["actual_special"] is None and row["forecast"]["actual_numbers"] == []


def test_wrong_source_to_candidate_alignment_is_rejected():
    raw, paths = _frames()
    paths.loc[0, "2026-01-03_num"] = 63
    with pytest.raises(ValueError, match="không khớp nguồn 2026-01-01"):
        page._path_payload(paths, raw, anchor_date="2026-01-03", mode="de", kind="active")


def test_special_hit_is_still_special_when_optional_export_flag_is_missing():
    raw, paths = _frames()
    paths = paths.drop(columns=["2026-01-03_is_de"])
    cell = page._path_payload(paths, raw, anchor_date="2026-01-03", mode="de", kind="active")["rows"][0]["cells"][0]
    assert cell["state"] == "hit-de"


def test_source_template_owns_clear_steps_and_token_colors():
    template = (page.TEMPLATES / "path_ui_page.html.j2").read_text()
    assert 'class="path-steps" data-app-workspace-guide' in template
    css = (page.TEMPLATES / "path_explorer.css").read_text()
    for token in ("--ui-n1-bg", "--ui-n2-bg", "--ui-special-bg", "--ui-empty-bg"):
        assert token in css
