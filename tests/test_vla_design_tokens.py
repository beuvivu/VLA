from __future__ import annotations

"""Design System phải TỰ CHỨNG MINH được, không chỉ tự khai.

Tệp này ghim ba thứ mà một hệ thống thiết kế dễ đánh mất trong im lặng:

* **Tương phản** — hợp đồng là dữ liệu trong ``CONTRAST_CONTRACT``, và ở đây
  nó được TÍNH LẠI, không phải đọc lại. Thêm một màu không đạt WCAG sau này là
  đỏ ngay, chứ không chờ ai nhớ ra phải đo.
* **Một nguồn sự thật** — CSS được sinh từ token. Một tệp CSS viết tay song
  song sẽ trôi khỏi token và không ai biết bên nào đúng.
* **Ba tầng Dark Mode** — thiếu một tầng là cái nút đổi chủ đề không hoạt
  động, đúng loại lỗi người dùng không tự chẩn đoán được.

Đo trên bảng màu chủ dự án cung cấp: 6 trong 15 cặp không đạt AA
(``text-muted`` 2,56:1; ``accent`` 4,47:1; ``success`` 3,30:1; ``warning``
3,19:1; ``info`` 4,10:1). Nên phép kiểm này không phải hình thức.
"""

import pytest

from vla_design.stylesheet import foundation_css
from vla_design.tokens import (
    CONTRAST_CONTRACT,
    DARK,
    LIGHT,
    MOTION,
    RADII,
    SPACING,
    TYPE_SCALE,
    contrast_ratio,
    relative_luminance,
)

PALETTES = {"light": LIGHT, "dark": DARK}


@pytest.mark.parametrize("palette_name", sorted(PALETTES))
def test_every_contract_pair_meets_its_wcag_threshold(palette_name: str) -> None:
    """Mọi cặp trong hợp đồng phải đạt ngưỡng của CHÍNH NÓ.

    Ngưỡng khác nhau theo mục đích: 4,5:1 cho chữ (SC 1.4.3), 3,0:1 cho thành
    phần phi văn bản như viền điều khiển và vòng focus (SC 1.4.11). Áp một
    ngưỡng cho tất cả là sai ở cả hai đầu — quá lỏng cho chữ, quá chặt cho
    đường kẻ.
    """
    palette = PALETTES[palette_name]
    failures = []
    for foreground, background, minimum, why in CONTRAST_CONTRACT:
        got = contrast_ratio(palette[foreground], palette[background])
        if got < minimum:
            failures.append(
                f"{foreground}/{background} = {got:.2f}:1 < {minimum}:1 ({why})"
            )
    assert not failures, f"{palette_name} không đạt WCAG: " + "; ".join(failures)


def test_the_contract_covers_every_colour_token_that_can_carry_text() -> None:
    """Hợp đồng phải PHỦ HẾT, nếu không nó chỉ canh những màu đã lành.

    Đây là chỗ một hợp đồng tương phản thường vô dụng: nó liệt kê đúng những
    cặp đã đạt rồi bỏ qua phần còn lại. Ở đây mọi token ``*-ink`` và mọi token
    chữ đều phải xuất hiện ít nhất một lần ở vị trí chữ.
    """
    pairs = {(foreground, background) for foreground, background, _, _ in CONTRAST_CONTRACT}
    covered = {foreground for foreground, _ in pairs}

    must_cover = {
        name
        for name in LIGHT
        if name.startswith("text-") or name.endswith("-ink") or name == "on-primary"
    }
    missing = sorted(must_cover - covered)
    assert not missing, f"token mang chữ mà không có trong hợp đồng: {missing}"

    # Và phải phủ ĐÚNG CẶP, không chỉ phủ tên. Bản đầu của phép kiểm này chỉ
    # đòi mỗi token xuất hiện đâu đó ở vị trí chữ, nên bỏ cặp
    # ``info-ink``/``info-soft`` đi nó vẫn xanh — vì ``info-ink``/``surface``
    # còn đó. Đo bằng đột biến: cặp bị bỏ chính là cặp BÓ NHẤT của màu ấy
    # (4,69:1 so với 5,13:1), tức là cặp duy nhất đáng canh.
    incomplete = sorted(
        name
        for name in LIGHT
        if name.endswith("-ink")
        and not {(name, "surface"), (name, name.replace("-ink", "-soft"))} <= pairs
    )
    assert not incomplete, (
        "token -ink phải được canh trên CẢ surface VÀ nền -soft của chính nó: "
        f"{incomplete}"
    )

    # Cùng lỗ hổng ở một tầng trên: token chữ phải được canh trên MỌI mặt nó
    # có thể nằm lên, không chỉ trên `surface`. Đo bằng đột biến: bỏ cặp
    # ``text-muted``/``surface-secondary`` thì luật ``-ink`` ở trên không bắt
    # được, mà đó lại là cặp bó hơn (4,82:1 so với 5,07:1) vì mặt phụ tối hơn
    # thẻ trắng.
    surfaces = ("surface", "surface-secondary", "background")
    text_gaps = sorted(
        f"{name}/{surface}"
        for name in LIGHT
        if name.startswith("text-")
        for surface in surfaces
        if (name, surface) not in pairs
    )
    assert not text_gaps, f"token chữ chưa được canh trên mặt nó nằm lên: {text_gaps}"


def test_both_palettes_declare_exactly_the_same_token_names() -> None:
    """Thiếu một token ở Dark Mode là một biến CSS không xác định.

    Trình duyệt không báo lỗi cho ``var(--vla-thieu)`` — nó lặng lẽ rơi về giá
    trị rỗng, nên chỗ ấy mất màu mà không có dấu hiệu gì trong console.
    """
    only_light = sorted(set(LIGHT) - set(DARK))
    only_dark = sorted(set(DARK) - set(LIGHT))
    assert not only_light, f"chỉ có ở Light Mode: {only_light}"
    assert not only_dark, f"chỉ có ở Dark Mode: {only_dark}"


def test_dark_mode_is_not_an_inversion_of_light_mode() -> None:
    """Spec cấm làm Dark Mode bằng cách đảo ngược, nên phải kiểm được.

    Phép đảo ngược cho ra nền đen tuyệt đối và màu nhấn chói. Ghim hai điều đo
    được: nền tối phải là màu CÓ SẮC (không phải xám thuần), và màu chính phải
    SÁNG HƠN ở Dark Mode chứ không phải tối đi.
    """
    background = DARK["background"].lstrip("#")
    r, g, b = (int(background[i : i + 2], 16) for i in (0, 2, 4))
    assert max(r, g, b) - min(r, g, b) >= 6, (
        f"nền tối {DARK['background']} là xám thuần — mất sắc navy của thiết kế"
    )
    assert relative_luminance(DARK["primary"]) > relative_luminance(LIGHT["primary"]), (
        "màu chính ở Dark Mode phải sáng hơn Light Mode, không phải tối đi"
    )


def test_text_on_an_accent_fill_flips_direction_between_the_two_palettes() -> None:
    """Chữ trên mảng màu nhấn đổi chiều giữa hai bảng — dễ làm sai nhất.

    Đo được: chữ trắng trên ``primary`` của Dark Mode chỉ đạt 3,06:1, còn chữ
    màu nền tối trên cùng mảng ấy đạt 6,34:1. Dùng chung một màu chữ cho cả
    hai bảng là không đạt ở một trong hai.
    """
    assert contrast_ratio(LIGHT["on-primary"], LIGHT["primary"]) >= 4.5
    assert contrast_ratio(DARK["on-primary"], DARK["primary"]) >= 4.5
    assert relative_luminance(LIGHT["on-primary"]) > relative_luminance(
        LIGHT["primary"]
    ), "Light Mode: chữ trên nút phải SÁNG hơn nút"
    assert relative_luminance(DARK["on-primary"]) < relative_luminance(
        DARK["primary"]
    ), "Dark Mode: chữ trên nút phải TỐI hơn nút"


def test_relative_luminance_refuses_a_colour_it_cannot_measure() -> None:
    """``rgba()`` không tính được độ chói mà không biết nền dưới nó.

    Trả về một con số cho đầu vào ấy là tệ hơn ném lỗi: nó đưa một giá trị vô
    nghĩa vào thẳng hợp đồng tương phản.
    """
    for bad in ("rgba(255, 255, 255, 0.72)", "#FFF", "khong-phai-mau", "#GGGGGG"):
        with pytest.raises(ValueError):
            relative_luminance(bad)


def test_the_glass_surfaces_stay_out_of_the_contrast_contract() -> None:
    """Mặt kính là ``rgba()`` nên KHÔNG đo được — phải nằm ngoài hợp đồng.

    Và đó cũng là lý do spec chỉ cho dùng glassmorphism ở mặt trang trí, không
    cho dùng dưới bảng thống kê dày: không đo được tương phản thì không bảo
    đảm được đọc ra.
    """
    in_contract = {name for pair in CONTRAST_CONTRACT for name in pair[:2]}
    assert "surface-glass" not in in_contract
    for palette in PALETTES.values():
        assert palette["surface-glass"].startswith("rgba(")


def test_the_generated_css_carries_every_token() -> None:
    """CSS phải sinh ra từ token, không viết tay song song.

    Một tệp CSS viết tay sẽ trôi khỏi token và không ai biết bên nào đúng —
    chính lớp lỗi mà giao diện cũ mắc: cùng một khái niệm ba giá trị.
    """
    css = foundation_css()
    for name, value in LIGHT.items():
        assert f"--vla-{name}: {value};" in css, f"Light Mode thiếu {name}"
    for name, value in DARK.items():
        assert f"--vla-{name}: {value};" in css, f"Dark Mode thiếu {name}"
    for step in SPACING:
        assert f"--vla-space-{step}: {step}px;" in css, step
    for name in RADII:
        assert f"--vla-radius-{name}:" in css, name
    for name in MOTION:
        assert f"--vla-motion-{name}:" in css, name
    for name in TYPE_SCALE:
        assert f"--vla-font-{name}-size:" in css, name


def test_the_theme_switch_has_all_three_layers_in_the_right_order() -> None:
    """Ba tầng, và tầng theo-hệ-điều-hành PHẢI nhường cho lựa chọn tường minh.

    Thiếu ``:not([data-theme="light"])`` thì người đọc chọn sáng trong lúc máy
    đặt tối sẽ vẫn thấy trang tối — tức cái nút không hoạt động, và người dùng
    không có cách nào tự chẩn đoán.
    """
    css = foundation_css()
    assert "@media (prefers-color-scheme: dark)" in css
    assert ':root:not([data-theme="light"])' in css
    assert ':root[data-theme="dark"]' in css

    media = css.index("@media (prefers-color-scheme: dark)")
    explicit = css.index(':root[data-theme="dark"]')
    assert media < explicit, (
        "khối chọn tường minh phải nằm SAU khối theo hệ điều hành, "
        "nếu không nó bị ghi đè và cái nút vô hiệu"
    )


def test_reduced_motion_and_focus_visibility_are_not_optional() -> None:
    """Hai thứ này bị bỏ quên nhiều nhất, nên ghim thẳng."""
    css = foundation_css()
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css
    assert "outline: 2px solid var(--vla-focus-ring);" in css
    # Ghim TỪNG bộ chọn, không chỉ ghim chuỗi "tabular-nums" có mặt đâu đó.
    # Bản đầu chỉ kiểm chuỗi, nên bỏ `.vla-table td` đi nó vẫn xanh — mà ô
    # bảng chính là chỗ cần nhất: một cột số lệch nhau làm sai chính việc so
    # sánh bằng mắt mà mọi trang VLA tồn tại để phục vụ.
    numeric_block = css[css.index(".vla-num,") : css.index("a {")]
    for selector in (".vla-num,", "td.vla-num,", "th.vla-num,", ".vla-table td,", ".vla-kpi-value"):
        assert selector in numeric_block, f"thiếu {selector} trong nhóm chữ số thẳng cột"
    assert "font-variant-numeric: tabular-nums;" in numeric_block


def test_no_motion_duration_is_long_enough_to_feel_like_waiting() -> None:
    """Trên trang phân tích, chuyển động dài là chờ đợi chứ không phải phản hồi."""
    for name, value in MOTION.items():
        if value.endswith("ms"):
            assert int(value.removesuffix("ms")) <= 240, f"{name} = {value} quá dài"


def test_the_spacing_scale_holds_no_arbitrary_value() -> None:
    """Spec đòi bội số của bốn. Một giá trị lẻ là đầu dây của sự lệch lạc."""
    assert all(step % 4 == 0 for step in SPACING), SPACING
    assert list(SPACING) == sorted(SPACING), "thang phải tăng dần"
