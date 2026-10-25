"""Đường cầu phải truy được ngày nguồn, vị trí và kết quả, kể cả số 0 đầu."""

import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import threading

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


@pytest.fixture(scope="module")
def path_layout_browser(tmp_path_factory):
    """Dựng cả bốn biến thể từ nguồn, gồm Đặc Biệt đang chạy có dữ liệu mẫu."""
    playwright = pytest.importorskip("playwright.sync_api")
    folder = tmp_path_factory.mktemp("path-layout")
    root = Path(__file__).resolve().parents[2]
    shutil.copytree(root / "docs/assets", folder / "assets")
    raw = []
    for n, day in enumerate(pd.date_range("2025-10-15", periods=110)):
        raw.append({"date": day.strftime("%Y-%m-%d"), **dict.fromkeys(dict(FIELD_WIDTHS), 0),
                    "special": int(f"{n % 10}{(n + 1) % 10}123")})
    paths = []
    for lag in range(1, 41):
        row = {"lag": lag, "i": 0, "j": 1, "p_mean": .4, "p_next": .0123,
               "current_streak": 3, "max_streak": 4,
               "next_day_pred": int(str(raw[len(raw) - lag]["special"]).zfill(5)[:2])}
        for target in range(len(raw) - 14, len(raw)):
            day = raw[target]["date"]
            number = int(str(raw[target - lag]["special"]).zfill(5)[:2])
            hit = number == raw[target]["special"] % 100
            row.update({f"{day}_num": number, f"{day}_hit": int(hit), f"{day}_is_de": int(hit)})
        paths.append(row)
    picks = pd.DataFrame([{"number": number, "prob": .0123, "support_paths_count": 4}
                          for number in (1, 12, 23, 34, 45, 56, 67, 78, 89, 90)])
    env = Environment(loader=FileSystemLoader(str(page.TEMPLATES)))
    for mode in ("loto", "de"):
        for kind in ("active", "stable"):
            page._render_page(env, out_path=folder / f"soi-path-{mode}-{kind}.html",
                              title="Đường cầu kiểm bố cục", mode=mode, kind=kind,
                              other_link=None, other_kind_label="", other_mode_label="",
                              index_link="index.html", anchor_date=raw[-1]["date"], display_days=14,
                              ui_df=pd.DataFrame(paths), picks_df=picks, raw_df=pd.DataFrame(raw))

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with playwright.sync_playwright() as pw:
            options = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.environ.get("APP_BROWSER_EXECUTABLE"):
                options["executable_path"] = os.environ["APP_BROWSER_EXECUTABLE"]
            try:
                browser = pw.chromium.launch(**options)
            except playwright.Error as error:
                if "Executable doesn't exist" in str(error):
                    pytest.skip("Cần playwright install chromium để đo hai cột đường cầu")
                raise
            try:
                yield browser, f"http://127.0.0.1:{server.server_port}"
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


def _path_geometry(browser_page):
    return browser_page.evaluate("""() => {
      const box = selector => {
        const element = document.querySelector(selector), rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return {top:rect.top,bottom:rect.bottom,height:rect.height,
          border:parseFloat(style.borderTopWidth),padding:parseFloat(style.paddingTop),
          contain:style.contain,maxHeight:style.maxHeight,clientHeight:element.clientHeight,
          scrollHeight:element.scrollHeight};
      };
      return {list:box('.path-list'),detail:box('.path-detail'),
        scroll:box('.path-list>.path-table-scroll'),note:box('.path-list>.path-note'),
        overflow:document.documentElement.scrollWidth-innerWidth};
    }""")


def _assert_equal_path_panels(browser_page):
    geometry = _path_geometry(browser_page)
    left, right = geometry["list"], geometry["detail"]
    assert abs(left["top"] - right["top"]) <= 1, geometry
    assert abs(left["bottom"] - right["bottom"]) <= 1, geometry
    assert left["border"] == right["border"] == 1, geometry
    assert left["padding"] == right["padding"] == 16, geometry
    assert abs(geometry["note"]["bottom"] - (left["bottom"] - 17)) <= 1, geometry
    assert geometry["scroll"]["bottom"] <= geometry["note"]["top"] - 15, geometry
    assert geometry["overflow"] <= 1, geometry
    return geometry


@pytest.mark.parametrize("mode,kind", [("loto", "active"), ("loto", "stable"),
                                      ("de", "active"), ("de", "stable")])
def test_path_panels_share_visible_borders_and_follow_detail_after_filtering(path_layout_browser, mode, kind):
    """Đo khung thật sau mỗi thao tác; bảng dài không được áp chiều cao lên căn cứ."""
    browser, base = path_layout_browser
    context = browser.new_context(viewport={"width": 1600, "height": 1000}, reduced_motion="reduce")
    browser_page = context.new_page()
    try:
        browser_page.goto(f"{base}/soi-path-{mode}-{kind}.html", wait_until="networkidle")
        original_data = browser_page.locator("#path-data").text_content()
        initial = _assert_equal_path_panels(browser_page)
        assert initial["scroll"]["maxHeight"] == "none", initial
        assert initial["scroll"]["clientHeight"] > 608, initial
        assert initial["scroll"]["scrollHeight"] > initial["scroll"]["clientHeight"], initial
        for width in (1280, 1151):
            browser_page.set_viewport_size({"width": width, "height": 1000})
            _assert_equal_path_panels(browser_page)
        browser_page.set_viewport_size({"width": 1600, "height": 1000})
        browser_page.locator('[data-path-index="1"]').focus()
        browser_page.locator('[data-path-index="1"]').press("Enter")
        _assert_equal_path_panels(browser_page)
        assert browser_page.locator("#path-detail-title").evaluate("e => e === document.activeElement")

        heights = []
        for days, cards in (("5", 6), ("10", 11), ("all", 15)):
            browser_page.locator("#path-days-filter").select_option(days)
            assert browser_page.locator(".path-evidence").count() == cards
            heights.append(_assert_equal_path_panels(browser_page)["detail"]["height"])
        assert heights[0] < heights[1] < heights[2], heights

        browser_page.locator("#path-number-filter").fill("01")
        _assert_equal_path_panels(browser_page)
        assert browser_page.locator('[data-path-row]:not([hidden])').count() == 4
        assert "number=01" in browser_page.url
        browser_page.locator("#path-number-filter").fill("99")
        empty = _assert_equal_path_panels(browser_page)
        assert browser_page.locator('[data-path-row]:not([hidden])').count() == 0
        assert empty["detail"]["height"] < heights[0], empty
        browser_page.locator("#path-reset").click()
        _assert_equal_path_panels(browser_page)
        assert browser_page.locator('[data-path-row]:not([hidden])').count() == 40
        assert browser_page.locator("#path-data").text_content() == original_data

        for width in (1150, 820, 390):
            browser_page.set_viewport_size({"width": width, "height": 1000})
            stacked = _path_geometry(browser_page)
            assert stacked["detail"]["bottom"] <= stacked["list"]["top"], stacked
            assert stacked["scroll"]["contain"] == "none", stacked
            assert stacked["scroll"]["clientHeight"] > 200, stacked
            assert stacked["overflow"] <= 1, stacked
            scroll = browser_page.locator(".path-list>.path-table-scroll")
            scroll.evaluate("e => { e.scrollTop = e.scrollHeight; }")
            assert scroll.evaluate("e => e.querySelector('tbody tr:last-child').getBoundingClientRect().bottom <= e.getBoundingClientRect().bottom + 1")
            browser_page.locator('[data-path-index="39"]').click()
            assert browser_page.locator("#path-detail-title").evaluate("e => e === document.activeElement")
            assert browser_page.locator("#path-detail-title").bounding_box()["y"] >= 0
    finally:
        context.close()
