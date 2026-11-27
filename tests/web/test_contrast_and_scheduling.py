from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup

from web.ui_theme import (
    WCAG_AA_NORMAL,
    contrast_ratio,
    readable_ink,
)

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
WORKFLOWS = ROOT / ".github/workflows"


def test_contrast_ratio_matches_known_values() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)
    assert contrast_ratio("#4f46e5", "#ffffff") == pytest.approx(
        contrast_ratio("#ffffff", "#4f46e5")
    )


def test_readable_ink_meets_aa_on_every_background() -> None:
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
    assert readable_ink("#ffffff") == "#0f172a"


def test_dark_pages_map_their_palette_onto_the_shared_tokens() -> None:
    template = (ROOT / "src/web/templates/path_ui_page.html.j2").read_text(encoding="utf-8")
    for token in ("--text:var(--ui-ink)", "--muted:var(--ui-ink-soft)", "--card:var(--ui-surface)", "--bg:var(--ui-bg)"):
        assert token in template, token


@pytest.mark.parametrize(
    "page",
    ["soi-path-de-active.html", "soi-path-loto-active.html"],
)
def test_path_page_text_contrasts_with_each_theme(page: Path) -> None:
    from theme_palette_helpers import theme_tokens
    text = (DOCS / page).read_text(encoding="utf-8")
    assert 'assets/ui.css' in text
    template = (ROOT / "src/web/templates/path_ui_page.html.j2").read_text(encoding="utf-8")
    assert '--text:var(--ui-ink)' in template and '--card:var(--ui-surface)' in template
    for dark in (False, True):
        tokens = theme_tokens(dark)
        for ink in ('--ui-ink', '--ui-ink-soft'):
            assert contrast_ratio(tokens[ink], tokens['--ui-surface']) >= WCAG_AA_NORMAL


def test_inverse_surfaces_do_not_use_a_theme_flipping_token() -> None:
    source = (ROOT / "src/pages/build_research_lab.py").read_text(encoding="utf-8")
    hero = re.search(r"\.rl-hero\{\{[^}]*\}\}", source)
    assert hero, "không tìm thấy .rl-hero"
    assert "background:var(--ui-ink)" not in hero.group(0).replace(" ", "")


def _tokens(block_selector: str) -> dict[str, str]:
    from web.ui_theme import TAILWIND_LITE_CSS

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
    sach = re.sub(r"/\*.*?\*/", " ", block, flags=re.S)
    return {
        name: value.strip()
        for name, value in re.findall(r"(--ui-[a-z0-9-]+)\s*:\s*([^;}]+)", sach)
    }


def test_text_on_brand_background_flips_with_the_theme() -> None:
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
            target = target.partition("?")[0]
            if target and target not in pages and not (DOCS / target).exists():
                broken.append(f"{page.name} -> {href}")
            elif not target and fragment and fragment not in ids:
                broken.append(f"{page.name} -> #{fragment}")
    assert not broken, f"liên kết chết: {broken[:10]}"


def _crons(name: str) -> list[str]:
    return re.findall(r'cron:\s*"([^"]+)"', (WORKFLOWS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["live-results.yml", "update-data.yml"])
def test_schedules_avoid_the_most_congested_minutes(name: str) -> None:
    minutes = [int(c.split()[0]) for c in _crons(name)]
    assert minutes, name
    assert not [m for m in minutes if m in (0, 30)], f"{name}: còn mốc ở phút {minutes}"


@pytest.mark.parametrize("name", ["live-results.yml", "update-data.yml"])
def test_workflows_accept_an_external_on_time_trigger(name: str) -> None:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    assert "repository_dispatch:" in text, name


def test_ci_runs_on_pushes_to_working_branches() -> None:
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    branches = re.search(r"push:.*?branches:\s*\[([^\]]+)\]", text, re.S)
    assert branches, "ci.yml phải chạy trên push"
    listed = {b.strip().strip('"\'') for b in branches.group(1).split(",")}
    assert "claude/**" in listed, f"nhánh làm việc không được phủ: {sorted(listed)}"
    assert "main" in listed, f"nhánh chính không được phủ: {sorted(listed)}"


def test_ci_does_not_run_the_same_commit_twice() -> None:
    workflow = yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
    route = workflow["jobs"]["route"]
    assert route["outputs"]["run_checks"] == "${{ steps.route.outputs.run_checks }}"
    for name in ("browser", "test"):
        job = workflow["jobs"][name]
        assert job["needs"] == "route"
        assert job["if"] == "needs.route.outputs.run_checks == 'true'"


def test_live_workflow_waits_for_the_draw_window_when_it_starts_early() -> None:
    text = (WORKFLOWS / "live-results.yml").read_text(encoding="utf-8")
    assert "window_start_min" in text
    assert "max_wait_seconds" in text


def test_live_workflow_gives_up_early_instead_of_holding_a_runner() -> None:
    text = (WORKFLOWS / "live-results.yml").read_text(encoding="utf-8")
    assert "quá sớm" in text
    wait = re.search(r"max_wait_seconds=\$\(\(\s*(\d+)\s*\*\s*60\s*\)\)", text)
    timeout = re.search(r"^\s*timeout-minutes:\s*(\d+)", text, re.MULTILINE)
    budget = re.search(r'^\s*MAX_SECONDS:\s*"(\d+)"', text, re.MULTILINE)
    assert wait and timeout and budget
    wait_s, timeout_s, budget_s = int(wait.group(1)) * 60, int(timeout.group(1)) * 60, int(budget.group(1))
    assert timeout_s >= wait_s + budget_s + 300, "timeout không chứa nổi chờ + thăm dò + cài đặt"
    assert int(timeout.group(1)) <= 360


def test_live_window_starts_before_the_first_prize() -> None:
    text = (WORKFLOWS / "live-results.yml").read_text(encoding="utf-8")
    match = re.search(r"window_start_min=\$\(\(18 \* 60 \+ (\d+)\)\)", text)
    assert match and int(match.group(1)) <= 15


def test_live_page_reveals_numbers_one_at_a_time() -> None:
    text = (DOCS / "live.html").read_text(encoding="utf-8")
    for hook in ("revealQueue", "drainQueue", "queueReveal", "REVEAL_STAGGER_MS"):
        assert hook in text, hook


def test_live_page_respects_reduced_motion() -> None:
    text = (DOCS / "live.html").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in text
    assert "reduceMotion" in text


def test_live_page_never_builds_markup_from_strings() -> None:
    text = (DOCS / "live.html").read_text(encoding="utf-8")
    assert "innerHTML" not in text
    assert "insertAdjacentHTML" not in text


_HEAT_STYLE = re.compile(r"background:rgb\((\d+),\s*(\d+),\s*(\d+)\);color:(#[0-9a-fA-F]{6})")


def _heat_cells(slug: str = "statistics") -> list[tuple[str, str]]:
    soup = BeautifulSoup((DOCS / f"{slug}.html").read_text(encoding="utf-8"), "html.parser")
    pairs = []
    for el in soup.select("[style]"):
        found = _HEAT_STYLE.search(str(el.get("style", "")))
        if found:
            red, green, blue, ink = found.groups()
            pairs.append((f"#{int(red):02x}{int(green):02x}{int(blue):02x}", ink.lower()))
    return pairs


def test_every_heat_cell_in_the_built_page_reaches_aa() -> None:
    cells = _heat_cells()
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


def test_statistics_page_can_reach_the_rest_of_the_site() -> None:
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

    missing = sorted(t for t in targets if not (DOCS / t).exists())
    assert not missing, f"liên kết trỏ tới trang không tồn tại: {missing}"


def _ui_bg(css: str) -> str:
    match = re.search(r"--ui-bg:\s*(#[0-9a-fA-F]{3,8})", css)
    assert match, "không tìm thấy --ui-bg"
    return match.group(1).lower()


def test_the_three_copies_of_the_page_background_agree() -> None:
    from web import css_links
    from web.ui_theme import TAILWIND_LITE_CSS

    token = _ui_bg(TAILWIND_LITE_CSS)
    assert _ui_bg(css_links.CRITICAL_CSS) == token, "critical.css lệch khỏi ui.css"
    assert _ui_bg(css_links._FALLBACK_CRITICAL) == token, "bản dự phòng lệch khỏi ui.css"


def test_the_first_frame_paints_the_background_from_tokens_not_a_copy() -> None:
    from web import css_links

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
