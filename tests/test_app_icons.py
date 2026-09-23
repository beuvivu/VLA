"""Biểu tượng phải là một BỘ, không phải một nhúm ký tự nhặt từ nhiều nơi.

Bản trước dùng 27 ký tự Unicode rời rạc — ``◉ ▤ ▦ ⟋ ⚗ 🎯 🔁 ① ② Σ`` — lấy từ
nhiều khối Unicode khác nhau. Chúng lệch nhau về nét, cỡ và đường chân chữ,
lại do PHÔNG HỆ THỐNG vẽ nên mỗi máy một khác. Không có cách nào làm chúng
nhất quán, vì chúng chưa bao giờ là một bộ.

Số đo ghim ở đây lấy từ trang tham chiếu qua runner Actions, đo trên trình
duyệt thật. Đổi chúng là đổi hợp đồng thị giác, nên phải đổi có chủ ý.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "src"))

from app_icons import CO_HOP, DUONG_VE, LUOI, NET, icon_svg  # noqa: E402
from ui_theme import SITE_NAV  # noqa: E402

PAGES = sorted(DOCS.glob("*.html"))

#: Số đo của trang tham chiếu. Hợp đồng, không phải sở thích.
HOP_THAM_CHIEU = 18
LUOI_THAM_CHIEU = "0 0 20 20"
NET_THAM_CHIEU = "1"


def test_the_measured_icon_geometry_is_pinned() -> None:
    """Ba con số này đến từ phép đo, không từ ước lượng."""
    assert CO_HOP == HOP_THAM_CHIEU
    assert LUOI == LUOI_THAM_CHIEU
    assert NET == NET_THAM_CHIEU


def test_every_menu_item_has_a_drawn_icon() -> None:
    """Không mục nào được rơi về hình tròn dự phòng.

    ``icon_svg`` trả hình tròn rỗng cho khoá lạ, vì một ô trống nhìn y như
    lỗi tải. Nhưng hình tròn ấy là dấu hiệu THIẾU, nên không mục thật nào
    được dùng nó.
    """
    muc = [(nhan, khoa) for _, nhom in SITE_NAV for _, nhan, khoa in nhom]
    assert len(muc) >= 32, "SITE_NAV co lại — phép kiểm sẽ quét tập nhỏ hơn"
    thieu = [f"{nhan} -> {khoa}" for nhan, khoa in muc if khoa not in DUONG_VE]
    assert thieu == []


def test_no_menu_item_still_uses_a_typographic_glyph() -> None:
    """Khoá biểu tượng phải là TÊN, không phải ký tự vẽ sẵn.

    Một ký tự Unicode lọt lại sẽ được `icon_svg` coi là khoá lạ và vẽ ra
    hình tròn — tức nó hỏng lặng lẽ, không đỏ ở đâu cả.
    """
    hop_le = re.compile(r"^[a-z0-9-]+$")
    xau = [
        f"{nhan}: {khoa!r}"
        for _, nhom in SITE_NAV
        for _, nhan, khoa in nhom
        if not hop_le.match(khoa)
    ]
    assert xau == []


def test_every_icon_is_stroke_only_on_the_measured_grid() -> None:
    """Nét, không tô. Trang tham chiếu dùng ``fill:none`` và nét 1px."""
    for khoa in DUONG_VE:
        svg = icon_svg(khoa)
        assert f'viewBox="{LUOI_THAM_CHIEU}"' in svg, khoa
        assert f'width="{HOP_THAM_CHIEU}" height="{HOP_THAM_CHIEU}"' in svg, khoa
        assert 'fill="none"' in svg, khoa
        assert f'stroke-width="{NET_THAM_CHIEU}"' in svg, khoa
        assert 'stroke="currentColor"' in svg, khoa
        # Màu đi theo `currentColor` nên biểu tượng đổi màu cùng chữ. Một mã
        # màu ghim cứng sẽ đứng im khi đổi chế độ màu.
        assert "#" not in svg, f"{khoa} ghim mã màu cứng"


def test_icons_stay_inside_the_grid() -> None:
    """Đường vẽ tràn khỏi lưới 20x20 sẽ bị cắt cụt khi thu về 18px.

    Đo HỘP BAO đã dựng, không đếm số trong chuỗi đường vẽ. Bản đầu của phép
    kiểm này quét mọi con số bằng biểu thức chính quy và đỏ trên mã ĐÚNG:
    lệnh chữ thường của SVG (``a``, ``l``, ``v``, ``h``, ``c``) mang ĐỘ DỜI
    tương đối, nên ``-12.8`` trong một hình tròn hợp lệ là bình thường. Một
    phép kiểm đỏ trên mã đúng thì tệ hơn không có phép kiểm.

    Chỉ trình duyệt mới trả lời được câu hỏi thật: sau khi dựng, hình nằm ở
    đâu trong khung nhìn.
    """
    trinh_duyet = pytest.importorskip("playwright.sync_api")
    chrome = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    if not chrome.exists():
        pytest.skip("không có Chromium để đo hộp bao")

    ve = "".join(
        f'<svg id="ic-{khoa}" viewBox="{LUOI}" fill="none" stroke="#000"'
        f' stroke-width="{NET}">'
        + "".join(f'<path d="{d}"/>' for d in duong)
        + "</svg>"
        for khoa, duong in DUONG_VE.items()
    )
    with trinh_duyet.sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=str(chrome), args=["--no-sandbox"])
        trang = b.new_page()
        trang.set_content(f"<!doctype html><body>{ve}</body>")
        hop = trang.evaluate(
            """() => {
              const ra = {};
              for (const s of document.querySelectorAll("svg")) {
                const b = s.getBBox();
                ra[s.id.slice(3)] = [b.x, b.y, b.x + b.width, b.y + b.height];
              }
              return ra;
            }"""
        )
        b.close()

    assert len(hop) == len(DUONG_VE), "không dựng đủ biểu tượng để đo"
    # Chừa 0.5 cho nửa bề dày nét ở mép.
    tran = [
        f"{khoa}: {[round(v, 2) for v in o]}"
        for khoa, o in hop.items()
        if o[0] < -0.5 or o[1] < -0.5 or o[2] > 20.5 or o[3] > 20.5
    ]
    assert tran == []


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_published_page_draws_the_icon_set(page: Path) -> None:
    """Cả bảy nhóm và ba mươi hai mục đều phải có biểu tượng trên mọi trang."""
    text = page.read_text(encoding="utf-8")
    so_muc = sum(len(nhom) for _, nhom in SITE_NAV)
    mong_doi = len(SITE_NAV) + so_muc
    dem = text.count('class="app-ic"')
    assert dem == mong_doi, f"{page.name}: {dem} biểu tượng, cần {mong_doi}"
