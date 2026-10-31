from __future__ import annotations

from pathlib import Path

from pages.build_landing_page import _fmt2, build_landing_page
from web.web_security import json_for_html_script

ROOT = Path(__file__).resolve().parents[2]


def test_landing_page_contains_navigation_and_sections(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    outputs = build_landing_page(repo_root=repo_root, docs_dir=tmp_path)

    assert (tmp_path / "index.html") in outputs
    assert (tmp_path / "landing.html") in outputs

    html = (tmp_path / "landing.html").read_text(encoding="utf-8")

    for section_id in [
        "tong-quan",
        "ket-qua",
        "chuc-don-vi",
        "ai-ml",
        "tan-suat-loto",
        "tan-suat-de",
        "gan-nhip",
        "cap-lon",
        "dau-duoi-tong",
        "db-tuan-thang",
        "duong-cau",
        "backtest",
    ]:
        assert f'id="{section_id}"' in html or f"id='{section_id}'" in html
        assert f"#{section_id}" in html

    # Khung hai cấp thay dock nổi, giữ các neo chuyển phần.
    assert 'class="app-rail"' in html
    assert 'class="dock"' not in html
    assert "Các phần trong trang" in html
    assert "Kết quả hàng ngày" in html
    assert "Chục × đơn vị" in html
    assert "data-number" in html
    assert "landing-data" in html
    assert "statistics.html" in html


def test_landing_page_is_self_contained(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    build_landing_page(repo_root=repo_root, docs_dir=tmp_path)
    html = (tmp_path / "landing.html").read_text(encoding="utf-8")

    assert "https://cdn" not in html
    assert "http://cdn" not in html
    assert "<script type=\"application/json\" id=\"landing-data\">" in html


def test_landing_page_escapes_embedded_data_and_avoids_untrusted_inner_html(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    build_landing_page(repo_root=repo_root, docs_dir=tmp_path)
    rendered = (tmp_path / "landing.html").read_text(encoding="utf-8")

    payload = json_for_html_script({"value": "</script><img src=x onerror=alert(1)>&"})
    assert "</script>" not in payload
    assert "<img" not in payload
    assert "\\u003c" in payload and "\\u0026" in payload
    assert _fmt2("' onmouseover='alert(1)") == ""
    assert "li.innerHTML =" not in rendered
    assert "Content-Security-Policy" in rendered
    assert 'name="referrer" content="no-referrer"' in rendered


def test_the_landing_page_delegates_clicks_instead_of_binding_every_cell() -> None:
    """Một trình nghe uỷ quyền, không phải một trình nghe mỗi ô.

    Đo trên trang đã dựng: ``[data-number]`` khớp 1309 phần tử — 1000 ô ma
    trận, 100 ô ma trận nhỏ, 88 liên kết số, 44 hàng cột, 27 số giải, 27 số
    dự đoán vui, 20 hàng xác suất. Bản cũ gọi ``addEventListener`` cho từng
    cái, giữ lại 1309 closure cùng 1309 bản ghi trình nghe. Đếm trong trình
    duyệt: 1339 trình nghe trước, 31 sau.

    Phép kiểm soi MÃ NGUỒN chứ không đếm trong trình duyệt: đếm trình nghe
    cần Chromium và một lượt dựng, quá nặng cho bộ kiểm thường. Thứ ghim ở
    đây là KHUÔN — không được quay lại lối gắn từng phần tử.
    """
    nguon = (ROOT / "src" / "pages" / "build_landing_page.py").read_text(encoding="utf-8")
    assert "document.querySelectorAll('[data-number]').forEach" not in nguon, (
        "quay lại lối gắn trình nghe cho từng phần tử mang data-number"
    )
    assert "goc.closest('[data-number]')" in nguon, (
        "phải uỷ quyền bằng closest thay vì gắn từng phần tử"
    )


def test_every_number_element_on_the_landing_page_can_still_be_opened() -> None:
    """Uỷ quyền chỉ đúng khi MỌI phần tử mang số vẫn mở được bảng căn cứ.

    Bản đầu của phép thử soi ``#number-detail`` — một id KHÔNG tồn tại — nên
    nó báo "nội dung không đổi" cho cả bốn loại phần tử và suýt bị đọc thành
    hồi quy. ``showNumber`` ghi vào ``#inspect-*``; soi đúng chỗ thì cả bốn
    loại đều đặt đúng con số.

    Ở đây ghim điều kiện để uỷ quyền chạy được: mọi phần tử bấm được đều mang
    ``data-number``, và trang có đủ các ô ``#inspect-*`` mà ``showNumber`` ghi
    vào. Thiếu một trong hai thì uỷ quyền im lặng không làm gì.
    """
    trang = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    for o in ("inspect-num", "inspect-mode", "inspect-title", "inspect-score",
              "inspect-prob", "inspect-reason", "inspect-evidence",
              "inspect-summary", "inspect-lines"):
        assert f'id="{o}"' in trang, f"thiếu ô {o} mà showNumber ghi vào"
    assert trang.count("data-number=") > 100, (
        "trang phải còn các phần tử mang data-number để uỷ quyền có việc"
    )


def test_the_conditional_tables_print_the_baseline_and_fdr_beside_the_raw_rate() -> None:
    import pandas as pd

    from pages.build_landing_page import CONDITIONAL_COLUMNS, _render_table

    df = pd.DataFrame([{"prev_special_2d": "42", "next_loto": "96", "count": 21, "base_count": 40,
                        "conditional_rate": 0.525, "baseline_rate": 0.24, "posterior_rate": 0.24004,
                        "lift": 1.0, "p_value": 9.4e-5, "q_value_fdr": 0.94}])
    for prev in ("prev_special_2d", "prev_loto"):
        assert CONDITIONAL_COLUMNS[prev][:2] == [prev, "next_loto"]
    html = _render_table(title="t", subtitle="s", df=df, columns=CONDITIONAL_COLUMNS["prev_special_2d"])
    for label in ("Tỷ lệ có điều kiện", "Mức nền", "Ước lượng sau co về nền", "q (FDR)"):
        assert f">{label}</th>" in html
    assert ">52.5%</td>" in html and ">24.0%</td>" in html and ">0.94</td>" in html


def test_tied_rows_keep_their_file_order_on_every_machine() -> None:
    # Hai dòng cầu cùng điểm từng đổi chỗ giữa runner CI và máy khác: quicksort của numpy xếp
    # dòng hoà theo lệnh vector của CPU.
    import pandas as pd

    from pages.build_landing_page import _sort_top

    df = pd.DataFrame({"id": range(300), "rule_score": [1.0, 2.0, 3.0] * 100})
    out = _sort_top(df, "rule_score", limit=300)
    for score, group in out.groupby("rule_score", sort=False):
        assert group["id"].is_monotonic_increasing, score
