from __future__ import annotations

import pandas as pd

from build_statistics_dashboard import _evidence_payload, _matrix, _table


def test_modern_matrix_is_self_contained_and_complete() -> None:
    html = _matrix(
        pd.DataFrame({"number_str": ["00", "99"], "freq": [1, 3]}),
        title="Test matrix",
        subtitle="Self-contained",
        value_col="freq",
    )
    assert html.count("matrix-cell") == 100
    assert "<img" not in html
    assert "00" in html
    assert "99" in html


def test_table_ignores_missing_requested_columns() -> None:
    html = _table(
        pd.DataFrame({"number_str": ["01"], "freq": [2]}),
        title="Test table",
        columns=["number_str", "missing_col", "freq"],
        highlight_col="freq",
        zfill_cols={"number_str"},
    )
    assert "missing_col" not in html
    assert "01" in html
    assert "Tần suất" in html


def test_clickable_matrix_and_payload_include_position_evidence() -> None:
    html = _matrix(
        pd.DataFrame({"number_str": ["00"], "freq": [4]}),
        title="Clickable",
        subtitle="Evidence",
        value_col="freq",
        evidence_mode="loto",
    )
    assert "showNumberEvidence" in html
    assert "data-number='00'" in html
    assert "data-mode='loto'" in html

    payload = _evidence_payload(
        cau_loto=pd.DataFrame({"number_str": ["00"], "cau_score": ["42.5"], "prob_percent": ["12.3"]}),
        cau_de=pd.DataFrame(),
        explain_loto=pd.DataFrame(
            {
                "number_str": ["00"],
                "ai_cau_score": ["42.5"],
                "ai_prob_percent": ["12.3"],
                "path_lines_count": ["1"],
                "top_position_1": ["L1: Giải Đặc Biệt · số 1(0) + Giải nhất · số 2(0) → 00"],
            }
        ),
        explain_de=pd.DataFrame(),
        positions_loto=pd.DataFrame(
            {
                "number_str": ["00"],
                "rule_kind": ["active"],
                "lag_days": ["1"],
                "base_date": ["2026-08-11"],
                "pos_i_label": ["Giải Đặc Biệt · số 1"],
                "digit_i": ["0"],
                "pos_j_label": ["Giải nhất · số 2"],
                "digit_j": ["0"],
                "path_line": ["L1: Giải Đặc Biệt · số 1(0) + Giải nhất · số 2(0) → 00"],
                "p_mean": ["0.25"],
                "hits": ["10"],
                "trials": ["40"],
                "current_streak": ["3"],
                "max_streak": ["5"],
                "rule_score": ["55"],
                "reason": ["Cầu đang chạy"],
            }
        ),
        positions_de=pd.DataFrame(),
    )
    assert payload["loto"]["00"]["summary"]["ai_cau_score"] == "42.5"
    assert payload["loto"]["00"]["positions"][0]["pos_i_label"] == "Giải Đặc Biệt · số 1"


# --- Banner, thẻ AI/ML và chân trang ---------------------------------------

import re
from pathlib import Path

BUILDER = (Path(__file__).resolve().parents[1] / "src" / "build_statistics_dashboard.py"
           ).read_text(encoding="utf-8")
#: Mã đã bỏ chú thích. Các phép kiểm bên dưới hỏi "chuỗi X còn/không còn trong
#: tệp" — mà chú thích của chính bản sửa lại NHẮC TỚI chuỗi cũ để giải thích vì
#: sao nó bị bỏ. Không cắt chú thích thì phép kiểm khớp vào lời giải thích và
#: xanh vĩnh viễn.
import build_statistics_dashboard as bsd

#: Biểu định kiểu đã trích khỏi f-string: quy tắc CSS ở đây mang cú pháp CSS
#: THẬT (một lớp ngoặc), nên phép kiểm không còn phụ thuộc chỗ đặt khối.
DASHBOARD_CSS = bsd._DASHBOARD_CSS


def _without_comments(code: str) -> str:
    """Bỏ chú thích trước khi quét, đúng như ``BUILDER_CODE`` vẫn làm.

    Phép kiểm ở đây đòi những chuỗi KHÔNG được xuất hiện ("as_of",
    "Dữ liệu đến"). Một chú thích nhắc tới chúng là hợp lệ — chính khối JS này
    có một chú thích giải thích vì sao mốc dựng thật được giữ lại — nên quét cả
    chú thích sẽ báo lỗi cho một đoạn mã đúng.
    """
    return "\n".join(
        line for line in code.splitlines() if not line.lstrip().startswith("//")
    )


DASHBOARD_SCRIPT_MAIN = _without_comments(bsd._DASHBOARD_SCRIPT_MAIN)

BUILDER_CODE = re.sub(r"/\*.*?\*/", "", re.sub(r"^\s*#.*$", "", BUILDER, flags=re.M), flags=re.S)
BUILDER_CODE = "\n".join(
    line for line in BUILDER_CODE.splitlines() if not line.lstrip().startswith("//")
)


def test_the_banner_uses_the_same_content_column_as_the_page_body() -> None:
    """Hero và thân trang phải tính từ CÙNG hai biến, không phải hai bộ số.

    Trước đây `main` dùng cột có `max-width` còn `.hero` canh lề bằng `margin`,
    nên độ lệch đổi dấu theo bề rộng — đo được: hero thò ra 168px mỗi bên ở
    1920px, nhưng thụt vào 72px mỗi bên ở 1440px. Trang không hề cuộn ngang ở
    bất kỳ mức nào, nên đây không phải lỗi tràn khung; nó là hai hệ toạ độ
    không nói chuyện với nhau.
    """
    # Đòi quy tắc CSS, không đòi cách nó được MÃ HOÁ. Bản trước regex nguồn
    # builder tìm ".hero {{...}}" với dấu ngoặc viết đôi — đúng chỉ khi khối CSS
    # còn nằm trong f-string của `main`. Sau khi CSS được trích ra hằng số
    # `_DASHBOARD_CSS`, dấu ngoặc trở lại đơn và phép kiểm đỏ oan dù quy tắc vẫn
    # nằm nguyên trong trang dựng ra.
    assert "--page-max:" in DASHBOARD_CSS and "--page-gutter:" in DASHBOARD_CSS
    hero = re.search(r"\.hero \{(.*?)\}", DASHBOARD_CSS, flags=re.S)
    main = re.search(r"\n\s*main \{(.*?)\}", DASHBOARD_CSS, flags=re.S)
    assert hero is not None and main is not None
    for block, name in ((hero.group(1), "hero"), (main.group(1), "main")):
        assert "var(--page-max)" in block, f"{name} phải dùng biến chung"
        assert "var(--page-gutter)" in block, f"{name} phải dùng biến chung"
    # Con số cứng quay lại là bệnh cũ tái phát.
    assert "1440px" not in hero.group(1), hero.group(1)
    assert "clamp(16px, 5vw, 72px)" not in hero.group(1), hero.group(1)
    assert "margin: 18px auto 0" in hero.group(1), hero.group(1)


def test_the_banner_heading_is_the_short_title_with_no_blurb_under_it() -> None:
    assert "<h1>Bảng Điều Khiển Thống Kê Xổ Số</h1>" in BUILDER_CODE
    assert "dễ nhìn, hiện đại và tự chứa dữ liệu" not in BUILDER_CODE
    assert "Giao diện này ưu tiên khả năng so sánh" not in BUILDER_CODE
    hero_markup = BUILDER_CODE[BUILDER_CODE.index('<header class="hero">'):]
    hero_markup = hero_markup[: hero_markup.index("</header>")]
    assert "<p>" not in hero_markup, hero_markup


def test_every_metric_card_holds_a_value_not_a_section_name() -> None:
    """Ô lớn của thẻ số liệu là chỗ cho MỘT GIÁ TRỊ.

    Thẻ AI/ML từng đặt vào đó một cái tên mục ("Cầu - Kèo & Xếp Hạng"). Nó
    không phải giá trị nào cả, nên xuống hai dòng và phá nhịp cả hàng trong
    khi ba thẻ kia chỉ một dòng. Bỏ nền thẻ đi không chữa được chuyện ấy — nó
    chỉ làm thẻ trông như bị lỗi dựng hình.
    """
    block = BUILDER_CODE[BUILDER_CODE.index("    metrics = ["):]
    block = block[: block.index("\n    ]")]
    assert "Cầu - Kèo & Xếp Hạng" not in block, block
    assert "cầu-kèo + xếp hạng" not in block, block
    assert "target_date or" in block, block
    assert "Tín hiệu AI/ML cho kỳ" in block, block


def test_the_metric_row_keeps_one_single_surface_treatment() -> None:
    """Bốn thẻ cùng một hàng thì phải cùng một bề mặt.

    Một thẻ thiếu nền giữa ba thẻ có nền đọc như lỗi dựng hình, không phải
    như một lựa chọn thiết kế.
    """
    assert "metric-card-plain" not in BUILDER_CODE, "biến thể phẳng đã bỏ"
    assert "plain=True" not in BUILDER_CODE
    assert "plain: bool" not in BUILDER_CODE, "tham số chết còn sót lại"


def test_a_long_metric_value_shrinks_instead_of_wrapping() -> None:
    """Xuống dòng làm lệch nhịp hàng; co chữ thì không."""
    rule = re.search(r"\.metric-card strong \{(.*?)\}", DASHBOARD_CSS, flags=re.S)
    assert rule is not None
    assert "clamp(" in rule.group(1), rule.group(1)
    assert "font-size: 23px" not in rule.group(1), rule.group(1)


def test_the_footer_keeps_only_the_two_timestamps() -> None:
    footer = BUILDER_CODE[BUILDER_CODE.index('<p class="footer-note">'):]
    footer = footer[: footer.index("</p>")]
    assert "Tạo lúc:" in footer and "Dữ liệu đến:" in footer
    assert "Manifest" not in footer, footer
    assert "CDN" not in footer, footer


def test_the_footer_clock_never_rewrites_the_data_date() -> None:
    """Đồng hồ chỉ được chạm vào "Tạo lúc".

    Cho "Dữ liệu đến" chạy theo đồng hồ máy sẽ là một lời khẳng định SAI về độ
    mới của dữ liệu — mỗi lần mở trang, ngày ấy lại nhảy lên hôm nay dù kho
    không hề có thêm kỳ nào. Đó đúng là loại sai lầm mà cả bộ kiểm toán của
    kho này sinh ra để chặn.
    """
    # Đọc thẳng khối JS của đồng hồ chân trang. Bản trước cắt nguồn builder từ
    # dòng getElementById("footerBuilt") tới "</script>"; sau khi JS được trích
    # ra hằng số, thẻ đóng không còn trong cùng chuỗi nên phép cắt tràn sang
    # khối JS thứ hai (_DASHBOARD_SCRIPT_EVIDENCE, có 9 lần getElementById) và
    # phép đếm "chỉ MỘT phần tử bị ghi đè" đỏ oan.
    script = DASHBOARD_SCRIPT_MAIN
    assert "footerBuilt" in script
    # Chỉ MỘT phần tử được ghi đè, và nó là phần tử "Tạo lúc".
    assert len(re.findall(r"getElementById\(", script)) == 1, script
    assert "as_of" not in script and "Dữ liệu đến" not in script, script
    # Mốc dựng thật phải còn đọc được, không bị xoá.
    assert "node.dataset.built" in script, script


def test_the_footer_clock_shows_local_time_not_utc() -> None:
    """`toISOString()` quy về UTC, nên máy ở Việt Nam hiện lùi 7 tiếng.

    Đã đo trong Chromium: cùng một thời điểm, trang hiện
    ``2026-09-15T09:37:11+07:00`` còn ``toISOString()`` cho
    ``2026-09-15T02:37:12Z``. Ở ``America/Los_Angeles`` nó còn sai cả NGÀY
    (15/09 thay vì 14/09).
    """
    script = BUILDER_CODE[BUILDER_CODE.index('var node = document.getElementById("footerBuilt")'):]
    script = script[: script.index("</script>")]
    assert "toISOString" not in script, script
    assert "getTimezoneOffset()" in script, script
    for call in ("getFullYear()", "getMonth()", "getDate()", "getHours()"):
        assert call in script, call
