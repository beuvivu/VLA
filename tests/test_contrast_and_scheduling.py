"""Kiểm thử tương phản màu và lịch chạy tự động.

Ba nhóm, mỗi nhóm khóa lại một kết quả đã đo được:

* ``readable_ink`` bảo đảm mọi nền đều có màu chữ đạt WCAG AA. Cách cũ dùng
  ngưỡng độ sáng cố định và để lọt cả một dải nền tầm trung.
* Các trang nền tối phải ánh xạ bảng màu riêng lên token dùng chung, nếu không
  thành phần dùng chung lấy màu chế độ sáng và biến mất trên nền tối.
* Lịch chạy tránh phút :00/:30 và có đường kích hoạt từ ngoài.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from ui_theme import (
    WCAG_AA_LARGE,
    WCAG_AA_NORMAL,
    contrast_ratio,
    readable_ink,
)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
WORKFLOWS = ROOT / ".github/workflows"


# --- Chọn màu chữ theo tương phản -----------------------------------------


def test_contrast_ratio_matches_known_values() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)
    # Đối xứng: đổi chỗ hai màu không đổi tỉ lệ.
    assert contrast_ratio("#4f46e5", "#ffffff") == pytest.approx(
        contrast_ratio("#ffffff", "#4f46e5")
    )


def test_readable_ink_meets_aa_on_every_background() -> None:
    """Quét toàn dải màu: không được có nền nào không tìm ra màu chữ đạt chuẩn.

    Đây là điều mà ngưỡng độ sáng cố định không làm được. Với ngưỡng cũ, chữ
    trắng trên nền #8aacf5 chỉ đạt 2,26:1 và trên #ea580c đạt 3,56:1.
    """
    worst = 21.0
    worst_bg = ""
    for r in range(0, 256, 17):
        for g in range(0, 256, 17):
            for b in range(0, 256, 17):
                bg = f"#{r:02x}{g:02x}{b:02x}"
                value = contrast_ratio(readable_ink(bg), bg)
                if value < worst:
                    worst, worst_bg = value, bg
    assert worst >= WCAG_AA_NORMAL, f"nền {worst_bg} chỉ đạt {worst:.2f}:1"


def test_readable_ink_fixes_the_backgrounds_that_actually_failed() -> None:
    for bg in ("#8aacf5", "#ea580c", "#9d6df2", "#f66b18", "#e9471f"):
        assert contrast_ratio(readable_ink(bg), bg) >= WCAG_AA_NORMAL, bg


def test_readable_ink_prefers_the_softer_dark_ink_when_both_pass() -> None:
    """Đen tuyền chỉ dùng khi #0f172a không đủ; nó gắt mắt hơn."""
    assert readable_ink("#ffffff") == "#0f172a"


# --- Trang nền tối ánh xạ token dùng chung --------------------------------


def test_dark_pages_map_their_palette_onto_the_shared_tokens() -> None:
    """Thiếu ánh xạ này, khối trạng thái rỗng lấy màu chữ của chế độ sáng.

    Đo được trên trang thật trước khi sửa: #0f172a trên card #0f172a, tức
    1,00:1 — chữ vô hình hoàn toàn.
    """
    template = (ROOT / "src/templates/path_ui_page.html.j2").read_text(encoding="utf-8")
    for token in ("--vla-ink:", "--vla-ink-soft:", "--vla-surface:", "--vla-bg:"):
        assert token in template, token


@pytest.mark.parametrize(
    "page",
    ["soi-path-de-active.html", "soi-path-loto-active.html"],
)
def test_dark_page_empty_and_body_text_are_light(page: Path) -> None:
    text = (DOCS / page).read_text(encoding="utf-8")
    match = re.search(r"--vla-ink:\s*(#[0-9a-fA-F]{6})", text)
    assert match, "trang tối phải khai báo lại --vla-ink"
    # Trên nền card #0f172a, màu chữ phải sáng để đạt chuẩn.
    assert contrast_ratio(match.group(1), "#0f172a") >= WCAG_AA_NORMAL


def test_inverse_surfaces_do_not_use_a_theme_flipping_token() -> None:
    """``var(--vla-ink)`` lật thành màu sáng ở chế độ tối.

    Dùng nó làm NỀN cho dải tiêu đề chữ trắng cho ra 1,17:1 khi hệ ở chế độ tối.
    """
    source = (ROOT / "src/build_research_lab.py").read_text(encoding="utf-8")
    hero = re.search(r"\.rl-hero\{\{[^}]*\}\}", source)
    assert hero, "không tìm thấy .rl-hero"
    assert "background:var(--vla-ink)" not in hero.group(0).replace(" ", "")


def test_text_on_brand_background_flips_with_the_theme() -> None:
    """Nền thương hiệu sáng lên ở chế độ tối; chữ trắng chỉ còn 2,75:1."""
    from ui_theme import TAILWIND_LITE_CSS

    assert "--vla-on-brand" in TAILWIND_LITE_CSS
    assert contrast_ratio("#ffffff", "#4f46e5") >= WCAG_AA_NORMAL
    assert contrast_ratio("#0f172a", "#8b93f8") >= WCAG_AA_NORMAL


# --- Không còn liên kết chết ----------------------------------------------


def test_no_internal_link_is_broken() -> None:
    pages = {p.name for p in DOCS.glob("*.html")}
    broken: list[str] = []
    for page in sorted(DOCS.glob("*.html")):
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        ids = {el.get("id") for el in soup.find_all(attrs={"id": True})}
        for anchor in soup.find_all("a"):
            href = (anchor.get("href") or "").strip()
            if not href or href.startswith(("http://", "https://", "mailto:")):
                continue
            target, _, fragment = href.partition("#")
            if target and target not in pages and not (DOCS / target).exists():
                broken.append(f"{page.name} -> {href}")
            elif not target and fragment and fragment not in ids:
                broken.append(f"{page.name} -> #{fragment}")
    assert not broken, f"liên kết chết: {broken[:10]}"


# --- Lịch chạy tự động ----------------------------------------------------


def _crons(name: str) -> list[str]:
    return re.findall(r'cron:\s*"([^"]+)"', (WORKFLOWS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["live-results.yml", "update-data.yml"])
def test_schedules_avoid_the_most_congested_minutes(name: str) -> None:
    """Hàng đợi lịch của GitHub dồn nặng nhất ở phút :00 và :30.

    Trên kho này độ trễ đo được là 2,5–4,5 giờ: mốc 11:00 UTC của workflow live
    thực tế nổ lúc 20:39–22:26 giờ Việt Nam trong năm ngày liên tiếp, khi kỳ
    quay đã xong từ lâu.
    """
    minutes = [int(c.split()[0]) for c in _crons(name)]
    assert minutes, name
    assert not [m for m in minutes if m in (0, 30)], f"{name}: còn mốc ở phút {minutes}"


@pytest.mark.parametrize("name", ["live-results.yml", "update-data.yml"])
def test_workflows_accept_an_external_on_time_trigger(name: str) -> None:
    """Lịch của GitHub là "cố gắng tốt nhất"; đường đúng giờ phải gọi từ ngoài."""
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    assert "repository_dispatch:" in text, name


def test_live_workflow_waits_for_the_draw_window_when_it_starts_early() -> None:
    text = (WORKFLOWS / "live-results.yml").read_text(encoding="utf-8")
    assert "window_start_min" in text
    assert "max_wait_seconds" in text


def test_live_workflow_gives_up_early_instead_of_holding_a_runner() -> None:
    """Mốc rơi quá sớm phải thoát để mốc sau xử lý, không giữ runner hàng giờ."""
    text = (WORKFLOWS / "live-results.yml").read_text(encoding="utf-8")
    assert "quá sớm" in text
    assert re.search(r"max_wait_seconds=\$\(\(\s*90\s*\*\s*60\s*\)\)", text)


def test_live_window_starts_before_the_first_prize() -> None:
    """Khung phải mở trước 18:15 giờ VN, nếu không sẽ lỡ những giải đầu."""
    text = (WORKFLOWS / "live-results.yml").read_text(encoding="utf-8")
    match = re.search(r"window_start_min=\$\(\(18 \* 60 \+ (\d+)\)\)", text)
    assert match and int(match.group(1)) <= 15


# --- Hiện số tuần tự ------------------------------------------------------


def test_live_page_reveals_numbers_one_at_a_time() -> None:
    text = (DOCS / "live.html").read_text(encoding="utf-8")
    for hook in ("revealQueue", "drainQueue", "queueReveal", "REVEAL_STAGGER_MS"):
        assert hook in text, hook


def test_live_page_respects_reduced_motion() -> None:
    text = (DOCS / "live.html").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in text
    assert "reduceMotion" in text


def test_live_page_never_builds_markup_from_strings() -> None:
    """Trang đọc dữ liệu từ nguồn ngoài; dựng HTML bằng chuỗi là đường tiêm mã."""
    text = (DOCS / "live.html").read_text(encoding="utf-8")
    assert "innerHTML" not in text
    assert "insertAdjacentHTML" not in text


# --- Ô nhiệt trong trang đã dựng ----------------------------------------------

#: Nội dung thuộc tính ``style`` của một ô nhiệt: ``background:rgb(r,g,b);color:#rrggbb``.
#:
#: Đọc GIÁ TRỊ thuộc tính chứ không khớp cả dấu nháy bao quanh. Bản đầu khớp
#: ``style="background:...`` và nó xanh — nhưng chỉ vì đang đọc một
#: docs/statistics.html cũ còn sót trong kho; trình dựng thật phát ra nháy đơn,
#: nên dựng lại một cái là test tìm thấy 0 ô và tưởng trang hỏng.
_HEAT_STYLE = re.compile(r"background:rgb\((\d+),\s*(\d+),\s*(\d+)\);color:(#[0-9a-fA-F]{6})")


def _heat_cells(slug: str = "statistics") -> list[tuple[str, str]]:
    """Các cặp (nền, chữ) của ô nhiệt trong một trang đã dựng.

    Args:
        slug: Tên trang, không kèm ``.html``.

    Returns:
        Danh sách cặp màu ``#rrggbb``.
    """
    soup = BeautifulSoup((DOCS / f"{slug}.html").read_text(encoding="utf-8"), "html.parser")
    pairs = []
    for el in soup.select("[style]"):
        found = _HEAT_STYLE.search(str(el.get("style", "")))
        if found:
            red, green, blue, ink = found.groups()
            pairs.append((f"#{int(red):02x}{int(green):02x}{int(blue):02x}", ink.lower()))
    return pairs


def test_every_heat_cell_in_the_built_page_reaches_aa() -> None:
    """Kiểm trên MÀU ĐÃ PHÁT RA, không phải trên hàm chọn màu.

    ``readable_ink`` đạt AA trên toàn dải nhiệt — đã có test riêng. Nhưng test
    đó không nói gì về việc trang có thật sự dùng kết quả của nó hay không:
    một chỗ gọi quên, một màu viết cứng, một nền đổi mà chữ giữ nguyên, đều
    lọt qua. Ở đây đọc thẳng cặp nền–chữ trong tệp HTML đã dựng.

    Ghi lại vì sao KHÔNG đo bằng điểm ảnh: bốn cách đo trên ảnh chụp đều cho
    ra số khác nhau và đều sai — dò ``backgroundColor`` bỏ sót nền gradient;
    chụp ``full_page`` làm trang dựng lại nên toạ độ lệch; lấy màu phổ biến
    nhất trong ô thì gặp màu pha do khử răng cưa; tắt chữ rồi lấy màu phổ biến
    nhất thì gặp nền của ô bên cạnh. Cặp màu trong markup thì không mơ hồ.
    """
    cells = _heat_cells()
    # Không dùng skip: ô nhiệt biến mất khỏi trang cũng là một hồi quy, mà
    # skip thì im lặng đúng như khi mọi thứ vẫn tốt.
    assert len(cells) > 500, f"chỉ thấy {len(cells)} ô nhiệt, trang dựng hỏng?"

    failures = []
    for background, ink in cells:
        ratio = contrast_ratio(ink, background)
        if ratio < WCAG_AA_NORMAL:
            failures.append(
                f"nền {background} chữ {ink} = {ratio:.2f}, "
                f"readable_ink nói {readable_ink(background)}"
            )
    assert not failures, (
        f"{len(failures)}/{len(cells)} ô nhiệt dưới chuẩn AA:\n  "
        + "\n  ".join(sorted(set(failures))[:8])
    )


def test_heat_cells_do_not_hand_their_ink_to_a_child() -> None:
    """Màu chữ tính cho ô phải là màu chữ người đọc thấy.

    Ô nhiệt đặt màu nội tuyến rồi để con thừa kế. Một thẻ con tự đặt màu sẽ
    ghi đè màu đó, mà cặp nền–chữ trong markup vẫn trông đúng — test trên
    xuống không bắt được.

    Cắt chuỗi tới ``</td>`` là sai: ô nhiệt ở đây là ``div``, nên phép cắt
    chạy sang tận ô kế tiếp rồi báo lỗi cho chính màu nội tuyến của ô đó.
    Phải duyệt cây thật.
    """
    soup = BeautifulSoup((DOCS / "statistics.html").read_text(encoding="utf-8"), "html.parser")
    cells = [el for el in soup.select("[style]")
             if _HEAT_STYLE.search(str(el.get("style", "")))]
    assert len(cells) > 500, f"chỉ thấy {len(cells)} ô nhiệt, trang dựng hỏng?"

    offenders = [
        f"{kid.name} trong {cell.name}: {kid.get('style')}"
        for cell in cells
        for kid in cell.find_all(True)
        if "color" in str(kid.get("style", ""))
    ]
    assert not offenders, (
        "thẻ con tự đặt màu làm vô hiệu màu đã tính cho nền: " + "; ".join(offenders[:5])
    )


# --- Trang không được là ngõ cụt ----------------------------------------------


def test_statistics_page_can_reach_the_rest_of_the_site() -> None:
    """statistics.html từng chỉ có ĐÚNG MỘT liên kết nội bộ.

    Mọi mục điều hướng khác trên trang đều là neo ``#...`` trong chính nó, nên
    ai mở thẳng trang này thì không có đường sang 14 trang thống kê, cũng không
    về được trang chính. Bảng điều khiển hằng ngày trỏ tới đây, nên đó là ngõ
    cụt ngay trên lối vào chính.
    """
    page = (DOCS / "statistics.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(page, "html.parser")
    targets = {
        a["href"].split("#", 1)[0]
        for a in soup.find_all("a", href=True)
        if a["href"].endswith(".html") or ".html#" in a["href"]
    }
    targets.discard("")

    assert "index.html" in targets, "phải có đường về trang chính"
    assert len(targets) >= 5, f"chỉ tới được {len(targets)} trang: {sorted(targets)}"

    # Mọi đích phải tồn tại thật — liên kết gãy còn tệ hơn không có liên kết.
    missing = sorted(t for t in targets if not (DOCS / t).exists())
    assert not missing, f"liên kết trỏ tới trang không tồn tại: {missing}"
