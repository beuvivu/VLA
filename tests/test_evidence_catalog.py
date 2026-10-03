"""Nguồn & bằng chứng của con số: danh mục, cách gắn vào trang, bằng chứng ML.

Phần hành vi trên trình duyệt nằm ở ``tests/frontend/evidence.test.mjs`` và
``scripts/check_ui_browser.py``; ở đây là hợp đồng phía dựng trang.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

import evidence_catalog
from evidence_catalog import covered_pages, ml_row_evidence, registry, registry_json, tag_rows, values_block
from page_output import _attach_evidence
from test_shipped_pages_are_clean import LEAK_TOKENS
from ui_theme import SITE_NAV, SITE_SEARCH_EXTRAS

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "docs").glob("*.html"))
_DATA = re.compile(r'<script type="application/json" id="app-evidence-data" data-app-evidence>(.*?)</script>', re.S)


def _published_registry(page: Path) -> dict:
    found = _DATA.findall(page.read_text(encoding="utf-8"))
    assert len(found) == 1, f"{page.name}: cần đúng một khối bằng chứng, có {len(found)}"
    return json.loads(found[0])


def test_the_catalog_covers_every_page_a_reader_can_reach() -> None:
    nav = {href.split("#")[0] for _, items in SITE_NAV for href, _, _ in items}
    extras = {href for href, _, _ in SITE_SEARCH_EXTRAS}
    published = {page.name for page in PAGES}
    assert published, "docs/ rỗng: phép kiểm không được quét tập rỗng"
    assert (nav | extras | published) - covered_pages() == set()


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_published_page_carries_sources_and_steps(page: Path) -> None:
    data = _published_registry(page)
    assert data["schema"] == evidence_catalog.SCHEMA_VERSION
    assert data["page"]["sources"], page.name
    assert data["page"]["reasoningTrace"]["steps"], page.name
    for entry in data["sections"]:
        assert (entry.get("match") or entry.get("heading")) and entry["sources"], entry
        assert entry["reasoningTrace"]["steps"], entry
    html = page.read_text(encoding="utf-8")
    assert html.count('<script src="assets/app-evidence.js" defer data-app-evidence></script>') == 1


def test_the_published_script_is_the_source_script() -> None:
    assert (ROOT / "docs/assets/app-evidence.js").read_bytes() == (ROOT / "src/assets/app-evidence.js").read_bytes()


@pytest.mark.parametrize("name", sorted(covered_pages()))
def test_no_catalog_entry_spells_out_where_the_data_lives(name: str) -> None:
    """Chặn ngay ở danh mục, trước cả khi trang được dựng.

    Nguồn ở đây là bộ dữ liệu và phép tính mô tả bằng lời; liên kết chỉ được
    trỏ tới trang nội bộ đã xuất bản.
    """
    text = json.dumps(registry(name), ensure_ascii=False)
    for token in LEAK_TOKENS:
        assert token not in text, f"{name} lộ {token!r}"
    published = {page.name for page in PAGES}
    data = registry(name)
    for entry in [data["page"], *data["sections"]]:
        for source in entry["sources"]:
            if "url" in source:
                assert source["url"] in published, source


def test_attaching_twice_gives_the_same_page_even_after_attribute_reordering(tmp_path: Path) -> None:
    page = tmp_path / "tan-suat-loto.html"
    html = "<html><head><title>x</title></head><body><main><p>27</p></main></body></html>"
    once = _attach_evidence(page, html)
    assert _attach_evidence(page, once) == once
    # Lượt chuẩn hoá HTML có thể sắp lại thuộc tính; bản cũ vẫn phải bị bóc.
    reordered = once.replace(
        '<script src="assets/app-evidence.js" defer data-app-evidence></script>',
        '<script data-app-evidence="" defer="" src="assets/app-evidence.js"></script>',
    )
    assert reordered != once
    assert _attach_evidence(page, reordered) == once
    assert (tmp_path / "assets/app-evidence.js").exists()


def test_the_registry_cannot_close_its_own_script_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    hostile = {"title": "</script><img src=x>", "snippet": "a & b"}
    monkeypatch.setattr(evidence_catalog, "_LOTO", hostile)
    text = registry_json("tan-suat-loto.html")
    assert "<" not in text and ">" not in text and "&" not in text
    assert hostile in json.loads(text)["page"]["sources"]


def _ml_frame(trust: float) -> pd.DataFrame:
    return pd.DataFrame({
        "number": [63, 5],
        "prob": [0.35 * 0.24213276 + 0.65 * 0.23797, 0.27],
        "raw_model_prob": [0.24213276, 0.31],
        "model_trust": [trust, trust],
        "quality_pass": [False, True],
    })


def test_ml_evidence_writes_out_the_shrinkage_with_real_numbers() -> None:
    rows = ml_row_evidence(_ml_frame(0.35), "loto")
    assert [ident for ident, _ in rows] == ["ml-loto-63", "ml-loto-05"]
    entry = rows[0][1]
    steps = " ".join(entry["reasoningTrace"]["steps"])
    # Tỉ lệ nền suy ngược đúng từ p = trust·thô + (1 − trust)·nền.
    assert "0,350 × 24,213% + 0,650 × 23,797% = 23,943%" in steps
    assert "quality_pass = False" in steps
    assert entry["reasoningTrace"]["confidenceScore"] == pytest.approx(0.35)
    assert entry["title"] == "Số 63 · ML LOTO"


def test_ml_evidence_without_skill_says_the_probability_is_the_baseline() -> None:
    frame = _ml_frame(0.0).assign(prob=[0.2383, 0.2383])
    steps = ml_row_evidence(frame, "loto")[0][1]["reasoningTrace"]["steps"]
    assert any("model_trust = 0" in step and "23,830%" in step for step in steps)
    de = ml_row_evidence(_ml_frame(0.35).assign(prob=[0.0108, 0.0101]), "de")[0][1]["reasoningTrace"]["steps"]
    assert any("chuẩn hoá" in step for step in de)
    assert not any(re.search(r"× \d+,\d+%", step) for step in de), "Đặc Biệt chuẩn hoá sau khi trộn: không được bịa nền"


def test_row_tags_go_to_body_rows_in_order() -> None:
    table = "<table><thead><tr><th>#</th></tr></thead><tbody><tr><td>1</td></tr>\n<tr class='x'><td>2</td></tr></tbody></table>"
    tagged = tag_rows(table, ["a", "b"])
    assert '<thead><tr><th>' in tagged
    assert re.findall(r'data-evidence-row="(\w)"', tagged) == ["a", "b"]
    assert 'data-evidence-cols' not in tagged
    assert tagged.count('data-evidence-cols="1,2"') == 0
    assert tag_rows(table, ["a", "b"], cols=(1, 2)).count('data-evidence-cols="1,2"') == 2
    block = values_block([("a", {"title": "</script>"})])
    assert block.startswith('<script type="application/json" data-app-evidence-values>')
    assert "</script>" not in block[len('<script type="application/json" data-app-evidence-values>'):-len("</script>")]


def test_published_ml_pages_tag_every_row_with_its_evidence() -> None:
    for mode in ("loto", "de"):
        html = (ROOT / f"docs/ml_top10_{mode}.html").read_text(encoding="utf-8")
        rows = re.findall(r'data-evidence-row="(ml-' + mode + r'-\d\d)" data-evidence-cols="1,2,3"', html)
        assert len(rows) == 10, (mode, rows)
        values = json.loads(re.search(r"data-app-evidence-values>(.*?)</script>", html, re.S).group(1))
        assert set(rows) == set(values)
        # Nguồn ML của mỗi chế độ trỏ về đúng trang top của chế độ ấy.
        page = f"ml_top10_{mode}.html"
        assert {v["sources"][0]["url"] for v in values.values()} == {page}
        ml = [src for src in _published_registry(ROOT / "docs" / page)["page"]["sources"] if src["title"] == "Mô hình ML thành phần"]
        assert [src["url"] for src in ml] == [page]


def test_ml_evidence_flags_files_made_under_the_old_trust_policy() -> None:
    """Tệp tạo trước luật mới không được trình bày như luật hiện hành."""
    from ml_train import TRUST_POLICY_VERSION

    legacy = " ".join(ml_row_evidence(_ml_frame(0.35), "loto")[0][1]["reasoningTrace"]["steps"])
    assert "luật trust CŨ" in legacy
    current = _ml_frame(0.0).assign(prob=[0.2383, 0.2383], trust_policy_version=TRUST_POLICY_VERSION)
    steps = " ".join(ml_row_evidence(current, "loto")[0][1]["reasoningTrace"]["steps"])
    assert "luật trust CŨ" not in steps
    stale = current.assign(trust_policy_version=TRUST_POLICY_VERSION - 1)
    assert "luật trust CŨ" in " ".join(ml_row_evidence(stale, "loto")[0][1]["reasoningTrace"]["steps"])


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_catalog_section_points_at_a_block_the_page_really_has(page: Path) -> None:
    """Khối khai trong danh mục phải có thật, nếu không con số rơi về bằng chứng của cả trang."""
    html = page.read_text(encoding="utf-8")
    for entry in _published_registry(page)["sections"]:
        if "heading" in entry:
            heads = [re.sub(r"<[^>]+>", "", h) for h in re.findall(r"<h[23][^>]*>(.*?)</h[23]>", html, re.S)]
            assert any(h.strip().startswith(entry["heading"]) for h in heads), (page.name, entry["heading"])
            continue
        ids = re.findall(r"#([\w-]+)", entry["match"])
        assert ids, entry["match"]
        assert any(f'id="{ident}"' in html for ident in ids), (page.name, entry["match"])


def test_live_forecasts_cite_the_published_forecast_not_the_live_draw() -> None:
    sections = {s["match"]: s for s in registry("live.html")["sections"]}
    titles = [src["title"] for src in sections["#live-predictions"]["sources"]]
    assert "Dự báo đã công bố trước kỳ quay" in titles
    assert "Bảng kết quả đang quay" not in titles
    assert "Bảng kết quả đang quay" in [src["title"] for src in registry("live.html")["page"]["sources"]]
    # Trang tải dự báo theo ngày quay lúc chạy: không được ghi ngày lúc dựng.
    snippets = " ".join(src["snippet"] for src in sections["#live-predictions"]["sources"])
    assert not re.search(r"cho kỳ \d\d-\d\d-\d{4}", snippets), snippets


def test_mixed_forecast_blocks_cite_both_model_pages() -> None:
    """Khối gộp LOTO lẫn Đặc Biệt trích mô hình ML của cả hai, trang riêng chỉ một."""
    def ml_links(entry: dict) -> set[str]:
        return {s["url"] for s in entry["sources"] if s["title"] == "Mô hình ML thành phần"}

    both = {"ml_top10_loto.html", "ml_top10_de.html"}
    home = {s.get("match"): s for s in registry("index.html")["sections"]}
    assert ml_links(home["#ai-ml"]) == both
    assert ml_links(registry("dashboard.html")["page"]) == both
    assert ml_links(registry("ml_top10_loto.html")["page"]) == {"ml_top10_loto.html"}
    assert ml_links(registry("ml_top10_de.html")["page"]) == {"ml_top10_de.html"}


def test_dashboard_diagnostics_have_their_own_derivations() -> None:
    sections = {s.get("heading"): s for s in registry("dashboard.html")["sections"]}
    assert {"Trọng số", "Hiệu chỉnh"} <= set(sections)
    steps = " ".join(sections["Trọng số"]["reasoningTrace"]["steps"])
    assert "MẶC ĐỊNH" in steps and "ngoài mẫu" in steps
    assert "vector xác suất 100 số" not in steps.lower()


def test_confidence_page_risk_numbers_get_the_simulation_derivation() -> None:
    """Số ở khối rủi ro đến từ mô phỏng và phép hoà vốn, không từ luật ba tầng."""
    sections = {s.get("heading"): s for s in registry("do-tin-cay.html")["sections"]}
    risk = " ".join(sections["Rủi ro / lợi nhuận"]["reasoningTrace"]["steps"])
    assert "10 000 kỳ" in risk and "100/27" in risk
    assert "High" not in risk and "Medium" not in risk
    assert {"Vòng phản hồi", "Giả thuyết đang kiểm tiến cứu"} <= set(sections)
