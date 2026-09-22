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
    for token in ("--ui-ink:", "--ui-ink-soft:", "--ui-surface:", "--ui-bg:"):
        assert token in template, token


@pytest.mark.parametrize(
    "page",
    ["soi-path-de-active.html", "soi-path-loto-active.html"],
)
def test_path_page_text_contrasts_with_the_light_surface(page: Path) -> None:
    text = (DOCS / page).read_text(encoding="utf-8")
    match = re.search(r"--ui-ink:\s*(#[0-9a-fA-F]{6})", text)
    assert match, "trang soi cầu phải khai báo --ui-ink"
    # Các trang soi cầu hiện dùng surface sáng, nên chữ phải tương phản đủ với màu trắng.
    assert contrast_ratio(match.group(1), "#ffffff") >= WCAG_AA_NORMAL


def test_inverse_surfaces_do_not_use_a_theme_flipping_token() -> None:
    """``var(--ui-ink)`` lật thành màu sáng ở chế độ tối.

    Dùng nó làm NỀN cho dải tiêu đề chữ trắng cho ra 1,17:1 khi hệ ở chế độ tối.
    """
    source = (ROOT / "src/build_research_lab.py").read_text(encoding="utf-8")
    hero = re.search(r"\.rl-hero\{\{[^}]*\}\}", source)
    assert hero, "không tìm thấy .rl-hero"
    assert "background:var(--ui-ink)" not in hero.group(0).replace(" ", "")


def _tokens(block_selector: str) -> dict[str, str]:
    """Token màu ĐANG có hiệu lực trong một khối của biểu định kiểu dùng chung.

    Đọc giá trị thật chứ không nhận mã màu viết tay trong phép kiểm. Bản trước
    ghim ``"#4f46e5"`` và ``"#8b93f8"`` thành hằng: đổi ``--ui-brand`` sang một
    màu KHÔNG đạt chuẩn thì phép kiểm vẫn xanh, vì nó không hề đọc token. Nó
    kiểm hai con số do chính nó viết ra.
    """
    from ui_theme import TAILWIND_LITE_CSS

    # Đếm ngoặc phải bắt đầu TỪ dấu ``{`` mở, không phải từ bên trong khối.
    # Bản trước nhảy qua luôn dấu mở nên độ sâu khởi đầu đã là 1 mà biến đếm
    # vẫn là 0: nó không bao giờ đóng đúng chỗ, ăn sang các khối sau, và vì
    # dict lấy giá trị CUỐI cho khoá trùng, ``_tokens(":root{")`` trả về đúng
    # bảng màu chế độ TỐI. Đột biến phát hiện: đổi --ui-ink-soft sang một màu
    # trượt AA mà phép kiểm vẫn xanh.
    mo = TAILWIND_LITE_CSS.index(block_selector) + len(block_selector) - 1
    if TAILWIND_LITE_CSS[mo] != "{":
        raise AssertionError(f"{block_selector!r} phải kết thúc bằng dấu ngoặc mở")
    depth = 0
    for offset, char in enumerate(TAILWIND_LITE_CSS[mo:]):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                block = TAILWIND_LITE_CSS[mo + 1 : mo + offset]
                break
    else:
        raise AssertionError(f"khong dong ngoac cho {block_selector!r}")
    # Bóc chú thích TRƯỚC khi dò token. Chú thích trong khối này nhắc tên token
    # bằng đúng cú pháp khai báo (``... cùng lúc với --ui-brand: ở chế độ
    # tối``), nên phép dò bắt luôn chuỗi đó và chạy tới dấu ``;`` kế tiếp — vốn
    # nằm sau MỘT khai báo khác. Kết quả đo được: ``--ui-brand`` mang giá trị
    # là một đoạn văn, và ``--ui-on-brand`` biến mất khỏi bảng.
    sach = re.sub(r"/\*.*?\*/", " ", block, flags=re.S)
    # Giữ giá trị CUỐI cho khoá trùng: trong một khối CSS, khai báo sau thắng.
    return {
        name: value.strip()
        for name, value in re.findall(r"(--ui-[a-z0-9-]+)\s*:\s*([^;}]+)", sach)
    }


def test_text_on_brand_background_flips_with_the_theme() -> None:
    """Chữ trên nền thương hiệu phải đạt AA ở CẢ hai chế độ.

    Nền thương hiệu sáng lên ở chế độ tối, nên một màu chữ cố định không phục
    vụ được cả hai: chữ trắng trên nền thương hiệu tối chỉ còn 2,75:1.
    """
    for ten, selector in (
        ("sáng", ":root{"),
        ("tối theo hệ", ':root:not([data-ui-theme="light"]){'),
        ("tối chọn tay", ':root[data-ui-theme="dark"]{'),
    ):
        token = _tokens(selector)
        thuong_hieu = token["--ui-brand"]
        tren_thuong_hieu = token["--ui-on-brand"]
        ratio = contrast_ratio(tren_thuong_hieu, thuong_hieu)
        assert ratio >= WCAG_AA_NORMAL, (
            f"chế độ {ten}: {tren_thuong_hieu} trên {thuong_hieu} = {ratio:.2f}:1"
        )


def test_both_dark_blocks_declare_the_same_tokens() -> None:
    """Tối-theo-hệ và tối-chọn-tay phải cho CÙNG một bảng màu.

    Biểu định kiểu khai chế độ tối hai lần: một lần trong
    ``@media (prefers-color-scheme:dark)`` cho người không chọn gì, một lần
    trong ``:root[data-ui-theme="dark"]`` cho người bấm chọn. Không có phép
    kiểm này thì hai khối trôi khỏi nhau: sửa một khối, quên khối kia, và hai
    người đọc cùng một trang thấy hai màu khác nhau. Đột biến đã chứng minh lỗ
    này — đổi ``--ui-on-brand`` chỉ trong khối ``@media`` mà bộ kiểm vẫn xanh.
    """
    theo_he = _tokens(':root:not([data-ui-theme="light"]){')
    chon_tay = _tokens(':root[data-ui-theme="dark"]{')
    assert theo_he == chon_tay, (
        "hai khối chế độ tối lệch nhau: "
        + ", ".join(
            f"{k}: media={theo_he.get(k)!r} vs attr={chon_tay.get(k)!r}"
            for k in sorted(set(theo_he) | set(chon_tay))
            if theo_he.get(k) != chon_tay.get(k)
        )
    )


def test_every_text_token_reaches_aa_on_every_surface_it_sits_on() -> None:
    """Mọi token màu CHỮ phải đạt AA trên mọi bề mặt của cùng chế độ.

    Không có phép kiểm này thì một màu nhấn đẹp mà mờ lọt thẳng ra trang: đã
    đo, ``#717580`` — màu chữ mờ của trang tham chiếu — chỉ đạt 3,96:1 trên
    ``#eaedff``.
    """
    CHU = ("--ui-ink", "--ui-ink-2", "--ui-ink-soft", "--ui-brand", "--ui-brand-ink",
           "--ui-ok", "--ui-warn", "--ui-bad")
    BE_MAT = ("--ui-bg", "--ui-bg-2", "--ui-surface", "--ui-surface-2")
    loi: list[str] = []
    for che_do, selector in (
        ("sáng", ":root{"),
        ("tối theo hệ", ':root:not([data-ui-theme="light"]){'),
        ("tối chọn tay", ':root[data-ui-theme="dark"]{'),
    ):
        token = _tokens(selector)
        for ten_chu in CHU:
            for ten_nen in BE_MAT:
                chu, nen = token[ten_chu], token[ten_nen]
                if not (chu.startswith("#") and nen.startswith("#")):
                    continue
                ratio = contrast_ratio(chu, nen)
                if ratio < WCAG_AA_NORMAL:
                    loi.append(f"{che_do}: {ten_chu} {chu} trên {ten_nen} {nen} = {ratio:.2f}:1")
    assert not loi, "token chữ trượt AA:\n  " + "\n  ".join(loi)


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
            # `?demo=1` trỏ về CHÍNH trang đang đứng, chỉ đổi tham số truy vấn.
            # Cắt phần truy vấn ra trước khi tra tên tệp, nếu không phép kiểm
            # đi tìm một tệp tên "?demo=1" và báo chết một liên kết vẫn sống.
            target = target.partition("?")[0]
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


def test_ci_runs_on_pushes_to_working_branches() -> None:
    """Nhánh làm việc phải tự có tín hiệu, không chờ một PR nào mở.

    Danh sách cũ chỉ có main/master, nên đẩy lên ``claude/**`` không khớp
    ``push`` và chỉ còn trông vào ``pull_request``. Đo được trong một phiên:
    sáu lần đẩy liên tiếp lên nhánh ĐANG CÓ PR MỞ không sinh lần chạy nào suốt
    hơn 45 phút. Nhánh im lặng không đỏ — chỉ là không có gì chạy — nên nhìn
    hệt như đang chờ, và phải kích hoạt tay mới biết mã có xanh không.
    """
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    branches = re.search(r"push:.*?branches:\s*\[([^\]]+)\]", text, re.S)
    assert branches, "ci.yml phải chạy trên push"
    listed = {b.strip().strip('"\'') for b in branches.group(1).split(",")}
    assert "claude/**" in listed, f"nhánh làm việc không được phủ: {sorted(listed)}"
    assert "main" in listed, f"nhánh chính không được phủ: {sorted(listed)}"


def test_ci_does_not_run_the_same_commit_twice() -> None:
    """Thêm ``push`` khiến một lần đẩy khớp CẢ HAI sự kiện.

    ``concurrency`` KHÔNG gộp được hai lần chạy đó: ``github.ref`` là
    ``refs/heads/...`` với ``push`` nhưng ``refs/pull/N/merge`` với
    ``pull_request``, tức hai nhóm khác nhau. Quan sát trực tiếp trên PR #58:
    hai lần chạy song song trên đúng một commit, dù khối ``concurrency`` vẫn ở
    nguyên đó.

    Nên phải chặn ở điều kiện job: nhánh trong kho đã có ``push`` phủ, chỉ fork
    mới cần ``pull_request`` vì nhánh fork không sinh ``push`` trên kho này.
    """
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    block = text[text.index("jobs:") :]
    block = block[: block.index("steps:")]
    assert "github.event_name != 'pull_request'" in block, (
        "job phải bỏ qua pull_request của nhánh trong kho"
    )
    assert "head.repo.full_name != github.repository" in block, (
        "vẫn phải chạy cho PR đến từ fork"
    )


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


# --- Nền không được nháy màu khi trang tải xong ---------------------------


def _ui_bg(css: str) -> str:
    match = re.search(r"--ui-bg:\s*(#[0-9a-fA-F]{3,8})", css)
    assert match, "không tìm thấy --ui-bg"
    return match.group(1).lower()


def test_the_three_copies_of_the_page_background_agree() -> None:
    """Màu nền khai ở BA chỗ; lệch nhau là một cú nháy màu khi trang tải.

    ``critical.css`` vẽ khung đầu tiên, ``ui.css`` vẽ khi đã tải xong, và
    ``_FALLBACK_CRITICAL`` đỡ khi module sinh ra không nạp được. Đo được trước
    khi sửa: bản dự phòng vẫn mang ``#F2F4FF`` của bảng màu cũ trong khi hai
    bản kia đã đổi — người đọc thấy nền cũ lóe lên rồi mới đổi sang nền mới.
    """
    import css_links
    from ui_theme import TAILWIND_LITE_CSS

    token = _ui_bg(TAILWIND_LITE_CSS)
    assert _ui_bg(css_links.CRITICAL_CSS) == token, "critical.css lệch khỏi ui.css"
    assert _ui_bg(css_links._FALLBACK_CRITICAL) == token, "bản dự phòng lệch khỏi ui.css"


def test_the_first_frame_paints_the_background_from_tokens_not_a_copy() -> None:
    """Quy tắc ``body`` của CSS tới hạn không được ghim mã màu.

    Màu nền từng có BỐN bản sao: ``ui_theme``, module sinh ra, bản dự phòng
    trong ``css_links``, và một chuỗi ghim cứng trong
    ``scripts/extract_critical_css.py``. Bản thứ tư không ai canh, nên sau khi
    đổi bảng màu thì khung vẽ ĐẦU TIÊN vẫn là nền cũ. Phép kiểm trên chỉ soi
    ``--ui-bg`` nên nó không thấy — nó không đọc thuộc tính ``background``.
    """
    import css_links

    for ten, css in (
        ("critical sinh ra", css_links.CRITICAL_CSS),
        ("bản dự phòng", css_links._FALLBACK_CRITICAL),
    ):
        match = re.search(r"body\{([^}]*)\}", css)
        assert match, f"{ten}: không có quy tắc body"
        khoi = match.group(1)
        background = re.search(r"background\s*:\s*([^;]+)", khoi)
        assert background, f"{ten}: body không khai background"
        assert not re.search(r"#[0-9a-fA-F]{3,8}", background.group(1)), (
            f"{ten}: nền ghim mã màu {background.group(1)!r} thay vì đọc token"
        )
