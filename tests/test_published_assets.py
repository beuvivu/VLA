"""Tài nguyên mà trang trỏ tới phải TỒN TẠI, và tài nguyên thừa phải nói ra.

Hai lớp lỗi khác nhau, nên hai phép kiểm khác nhau:

* Trang trỏ tới tệp không có -> trình duyệt nhận 404 và mất hẳn phần giao
  diện ấy. Lỗi thấy được ngay.
* Tệp không trang nào dùng -> không ai thấy gì, nó chỉ nằm đó và lớn dần.
  Lỗi không thấy được, nên cần phép kiểm mới phát hiện.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

#: Đuôi tệp mà trang nạp về để hiển thị. Không tính `.html` vì liên kết giữa
#: các trang đã có phép kiểm điều hướng riêng canh.
DUOI_TAI_NGUYEN = (".css", ".js", ".woff2", ".woff", ".png", ".svg", ".webp", ".ico")

#: Đường dẫn nội bộ trong thuộc tính `href` hoặc `src`. Bỏ qua URL tuyệt đối,
#: `data:`, `mailto:` và neo trong trang.
_THAM_CHIEU = re.compile(r'(?:href|src)="((?!https?:|data:|mailto:|#)[^"]+)"')

#: Tệp được các KỊCH BẢN BẢO TRÌ phát ra, không phải trình dựng thường.
#:
#: Chúng không xuất hiện trên trang nào, nhưng KHÔNG chết: có mã phát ra
#: chúng, chỉ là mã ấy chạy tay chứ không nằm trong quy trình. Đo được:
#:
#:     matrix-virt.js        scripts/optimize_index_dom.py
#:     apply-data-styles.js  scripts/patch_csp_no_inline.py
#:     ui-dock.js            src/web_security.py::security_script_tags
#:     live-board.js         không mã nào phát ra
#:
#: `security_script_tags` hiện KHÔNG ai gọi, và `live-board.js` không mã nào
#: phát ra. Cả hai là ứng viên gỡ, nhưng gỡ chúng là gỡ cả một đường mã nên
#: tách sang lần sau; ghi ở đây để chúng không lặng lẽ trôi đi.
NGOAI_LE = {
    "assets/matrix-virt.js",
    "assets/apply-data-styles.js",
    "assets/ui-dock.js",
    "assets/live-board.js",
}


def _duong_dan_trang_tro_toi() -> dict[str, set[str]]:
    """Mọi đường dẫn nội bộ mà các trang xuất bản trỏ tới.

    Returns:
        Ánh xạ đường dẫn -> tập tên trang trỏ tới nó.
    """
    ra: dict[str, set[str]] = {}
    for trang in sorted(DOCS.glob("*.html")):
        noi_dung = trang.read_text(encoding="utf-8")
        for khop in _THAM_CHIEU.finditer(noi_dung):
            dich = khop.group(1).split("?")[0].split("#")[0]
            if dich and not dich.endswith("/"):
                ra.setdefault(dich, set()).add(trang.name)
    return ra


def test_the_published_tree_has_pages_to_scan() -> None:
    """Chốt chặn: hai phép kiểm dưới quét `docs/`, tập rỗng thì chúng vô dụng."""
    assert len(list(DOCS.glob("*.html"))) >= 29


def test_no_published_page_points_at_a_file_that_is_not_there() -> None:
    """Một `src` trỏ hụt là 404, và phần giao diện ấy biến mất không báo gì."""
    tro_toi = _duong_dan_trang_tro_toi()
    assert tro_toi, "không trang nào trỏ tới tài nguyên nào — quét hỏng"
    thieu = {
        f"{trang} -> {dich}"
        for dich, trangs in tro_toi.items()
        if not (DOCS / dich).exists()
        for trang in sorted(trangs)
    }
    assert thieu == set()


def test_every_published_asset_is_reachable_from_some_page() -> None:
    """Tệp không ai dùng thì không ai thấy nó thừa.

    `ui-part1.css`, `ui-part2.css` và `ui-part3.css` từng nằm đây 12 KB mà
    KHÔNG trang nào trong 29 trang trỏ tới, không `@import` nào gọi, không
    phép kiểm nào nhắc, và `extract_critical_css.py` chỉ đọc `ui.css`. Thứ
    duy nhất nhắc tên chúng là một chuỗi selector trong `css-async.js` —
    selector ấy khớp *nếu* có trang nạp chúng, mà không trang nào nạp.
    """
    tro_toi = set(_duong_dan_trang_tro_toi())
    co_that = {
        tep.relative_to(DOCS).as_posix()
        for tep in DOCS.rglob("*")
        if tep.is_file() and tep.suffix in DUOI_TAI_NGUYEN
    }
    assert co_that, "không tìm thấy tài nguyên nào — quét hỏng"
    thua = co_that - tro_toi - NGOAI_LE
    assert thua == set(), (
        "tài nguyên không trang nào dùng; gỡ đi, hoặc thêm vào NGOAI_LE kèm "
        "lý do đo được"
    )
