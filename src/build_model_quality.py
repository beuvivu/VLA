from __future__ import annotations

"""Trang Chất lượng mô hình: báo cáo chẩn đoán, không phải bãi số.

Bản cũ in hai bảng LogLoss/Brier. Nó trả lời "hơn kém đường cơ sở bao nhiêu"
nhưng không trả lời "vì sao", mà "vì sao" mới quyết định phải sửa cái gì. Bản
này dựng quanh phân rã Murphy: tách phần hiệu chỉnh khỏi phần phân biệt, rồi
đặt độ sắc và độ phủ đánh giá cạnh nhau để không con số nào đọc lệch được.

Biểu đồ vẽ bằng SVG nội tuyến: chính sách bảo mật của trang đặt
``default-src 'self'`` nên không gọi được thư viện ngoài, và một biểu đồ vài
chục điểm thì không đáng đánh đổi lấy phụ thuộc.
"""

import argparse
import html
import json
from pathlib import Path

from page_output import write_page
import numpy as np
import pandas as pd

from ui_locale import mode_label
from ui_theme import (
    app_shell_close,
    app_shell_open,
    card,
    page_header,
    stylesheet_link,
    write_stylesheet,
)
from web_security import security_meta_tags

#: Khung vẽ mặc định cho thẻ NỬA BỀ NGANG.
#:
#: Toạ độ người dùng phải xấp xỉ số pixel thật, nếu không cỡ chữ đi theo. SVG
#: co giãn khớp bề ngang thẻ chứa, nên một viewBox rộng 520 nằm trong thẻ rộng
#: 1 200px sẽ phóng mọi thứ lên 2,3 lần: nhãn trục đặt 10px hiện ra 23px, to
#: hơn cả tiêu đề thẻ. Thẻ tràn bề ngang vì thế dùng khung riêng bên dưới.
PLOT_W, PLOT_H = 520, 300
WIDE_W, WIDE_H = 1120, 300
PAD_L, PAD_R, PAD_T, PAD_B = 64, 16, 14, 36


def _scale(value, lo, hi, out_lo, out_hi):
    if hi == lo:
        return (out_lo + out_hi) / 2
    return out_lo + (value - lo) * (out_hi - out_lo) / (hi - lo)


def _axes(x_label: str, y_label: str, ticks_x, ticks_y, w=PLOT_W, h=PLOT_H) -> str:
    """Lưới và trục ở mức LÙI LẠI: dữ liệu phải là thứ đậm nhất trên khung."""
    parts = [
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="none"/>',
    ]
    for index, (value, x) in enumerate(ticks_x):
        # Nhãn ở hai mép bị khung cắt mất một nửa nếu vẫn canh giữa.
        anchor = "start" if index == 0 else ("end" if index == len(ticks_x) - 1 else "middle")
        parts.append(
            f'<line x1="{x:.1f}" y1="{PAD_T}" x2="{x:.1f}" y2="{h - PAD_B}" '
            f'stroke="var(--ui-border)" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{h - PAD_B + 15}" text-anchor="{anchor}" '
            f'font-size="10" fill="var(--ui-ink-soft)">{html.escape(value)}</text>'
        )
    for value, y in ticks_y:
        parts.append(
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{w - PAD_R}" y2="{y:.1f}" '
            f'stroke="var(--ui-border)" stroke-width="1"/>'
            f'<text x="{PAD_L - 6}" y="{y + 3.5:.1f}" text-anchor="end" '
            f'font-size="10" fill="var(--ui-ink-soft)">{html.escape(value)}</text>'
        )
    parts.append(
        f'<text x="{(PAD_L + w - PAD_R) / 2:.0f}" y="{h - 3}" text-anchor="middle" '
        f'font-size="10" fill="var(--ui-ink-soft)">{html.escape(x_label)}</text>'
        f'<text x="12" y="{(PAD_T + h - PAD_B) / 2:.0f}" text-anchor="middle" font-size="10" '
        f'fill="var(--ui-ink-soft)" transform="rotate(-90 12 '
        f'{(PAD_T + h - PAD_B) / 2:.0f})">{html.escape(y_label)}</text>'
    )
    return "".join(parts)


def _frame(body: str, label: str, w=PLOT_W, h=PLOT_H) -> str:
    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
        f'aria-label="{html.escape(label)}" style="display:block;max-width:100%;height:auto">'
        f"{body}</svg>"
    )


def calibration_chart(rows: list[dict], base_rate: float, label: str) -> str:
    """Xác suất dự báo so với tỉ lệ thực, từng nhóm phân vị.

    Đường chéo là hiệu chỉnh hoàn hảo. Thanh dọc là khoảng Wilson 95%: thiếu
    nó thì một nhóm 31 dòng trông ngang hàng một nhóm 11 680 dòng, và người
    đọc kết luận sai về đúng cái nhóm ít tin cậy nhất.
    """
    if not rows:
        return '<p class="ui-table-empty">Chưa đủ dữ liệu.</p>'
    lo = min(min(r["predicted"] for r in rows), min(r["ci_low"] for r in rows))
    hi = max(max(r["predicted"] for r in rows), max(r["ci_high"] for r in rows))
    pad = (hi - lo) * 0.08 or 0.001
    lo, hi = lo - pad, hi + pad

    def px(v):
        return _scale(v, lo, hi, PAD_L, PLOT_W - PAD_R)

    def py(v):
        return _scale(v, lo, hi, PLOT_H - PAD_B, PAD_T)

    ticks = [lo + (hi - lo) * f for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
    body = [_axes("Xác suất dự báo", "Tỉ lệ về thực tế",
                  [(_num(t, 4), px(t)) for t in ticks],
                  [(_num(t, 4), py(t)) for t in ticks])]
    body.append(
        f'<line x1="{px(lo):.1f}" y1="{py(lo):.1f}" x2="{px(hi):.1f}" y2="{py(hi):.1f}" '
        f'stroke="var(--ui-ink-soft)" stroke-width="2" stroke-dasharray="5 4" opacity=".55"/>'
    )
    body.append(
        f'<line x1="{PAD_L}" y1="{py(base_rate):.1f}" x2="{PLOT_W - PAD_R}" '
        f'y2="{py(base_rate):.1f}" stroke="var(--ui-ink-soft)" stroke-width="1" '
        f'stroke-dasharray="2 4" opacity=".7"/>'
    )
    for r in rows:
        x, y = px(r["predicted"]), py(r["observed"])
        radius = 4 + 5 * (r["count"] / max(q["count"] for q in rows)) ** 0.5
        body.append(
            f'<line x1="{x:.1f}" y1="{py(r["ci_low"]):.1f}" x2="{x:.1f}" '
            f'y2="{py(r["ci_high"]):.1f}" stroke="var(--ui-chart-1)" stroke-width="2" opacity=".45"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="var(--ui-chart-1)" '
            f'stroke="var(--ui-surface)" stroke-width="2">'
            f"<title>{_count(r['count'])} dòng · dự báo {r['predicted']:.5f} · "
            f"thực tế {r['observed']:.5f} · KTC 95% [{r['ci_low']:.5f}, {r['ci_high']:.5f}]</title>"
            "</circle>"
        )
    return _frame("".join(body), label)


def sharpness_chart(sharp: dict, label: str) -> str:
    """Mô hình dám rời tỉ lệ nền bao xa. Vạch đứt là chính tỉ lệ nền."""
    bars = sharp.get("histogram") or []
    if not bars:
        return '<p class="ui-table-empty">Chưa đủ dữ liệu.</p>'
    lo, hi = bars[0]["lo"], bars[-1]["hi"]
    top = max(b["count"] for b in bars) or 1

    def px(v):
        return _scale(v, lo, hi, PAD_L, PLOT_W - PAD_R)

    ticks_x = [lo + (hi - lo) * f for f in (0.0, 0.5, 1.0)]
    body = [_axes("Xác suất dự báo", "Số ô",
                  [(_num(t, 4), px(t)) for t in ticks_x],
                  [(_count(top * f),
                    _scale(top * f, 0, top, PLOT_H - PAD_B, PAD_T)) for f in (0, .5, 1)])]
    width = (px(bars[0]["hi"]) - px(bars[0]["lo"]))
    for b in bars:
        if not b["count"]:
            continue
        y = _scale(b["count"], 0, top, PLOT_H - PAD_B, PAD_T)
        body.append(
            f'<rect x="{px(b["lo"]) + 1:.1f}" y="{y:.1f}" width="{max(width - 2, 1):.1f}" '
            f'height="{PLOT_H - PAD_B - y:.1f}" rx="3" fill="var(--ui-chart-1)">'
            f"<title>{b['lo']:.5f}–{b['hi']:.5f}: {b['count']:,} ô</title></rect>".replace(",", ".")
        )
    base = sharp.get("base_rate", 0.0)
    if lo <= base <= hi:
        body.append(
            f'<line x1="{px(base):.1f}" y1="{PAD_T}" x2="{px(base):.1f}" y2="{PLOT_H - PAD_B}" '
            f'stroke="var(--ui-ink)" stroke-width="2" stroke-dasharray="5 4"/>'
            f'<text x="{px(base) + 5:.1f}" y="{PAD_T + 11}" font-size="10" '
            f'fill="var(--ui-ink-soft)">tỉ lệ nền</text>'
        )
    return _frame("".join(body), label)


def skill_chart(skill: dict, label: str) -> str:
    """Kỹ năng từng kỳ quanh mốc 0, kèm dải ±1,96·SE của trung bình.

    Bảng cũ in "-0,08%" mỗi ngày mà không nói mức dao động thuần nhiễu là bao
    nhiêu, nên không ai đọc ra được con số ấy có đáng kể hay không.

    Thang dọc cắt ở phân vị 2-98 chứ không ôm trọn dải. Lịch sử này có vài kỳ
    hỏng nặng đầu năm — một kỳ xuống tận −96% — và nếu để chúng định thang thì
    227 kỳ còn lại dồn thành một vạch ngang, tức biểu đồ không nói gì về đoạn
    mà người đọc quan tâm. Điểm nằm ngoài thang KHÔNG bị bỏ đi: nó được vẽ
    thành hình tam giác ghim ở mép, và chú thích đếm rõ có bao nhiêu điểm như
    thế. Cắt thang mà im lặng mới là giấu dữ liệu.
    """
    points = skill.get("points") or []
    if len(points) < 2:
        return '<p class="ui-table-empty">Chưa đủ lịch sử.</p>'
    values = np.asarray([p["skill"] for p in points], dtype=float)
    # Trung vị ± 6·IQR chứ không phải phân vị 2-98: lịch sử này có 20/229 kỳ
    # hỏng nặng, nên phân vị 2 vẫn còn ở −84% và thang vẫn bị đè bẹp. Khoảng
    # tứ phân vị không bị đuôi kéo, nên nó bám đúng phần thân của phân phối.
    q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75])
    iqr = float(q3 - q1)
    span = max(abs(median) + 6.0 * iqr, 1e-4)

    def px(i):
        return _scale(i, 0, len(points) - 1, PAD_L, WIDE_W - PAD_R)

    def py(v):
        return _scale(max(-span, min(span, v)), -span, span, WIDE_H - PAD_B, PAD_T)

    middle = len(points) // 2
    body = [_axes("Kỳ mở thưởng", "Kỹ năng LogLoss",
                  [(points[0]["date"][5:], px(0)),
                   (points[middle]["date"][5:], px(middle)),
                   (points[-1]["date"][5:], px(len(points) - 1))],
                  [(f"{v:+.1%}".replace(".", ","), py(v)) for v in (-span, 0.0, span)],
                  w=WIDE_W, h=WIDE_H)]
    # Dải chỉ vẽ khi nó NẰM LỌT trong thang. Sai số chuẩn ở đây bị 25 kỳ hỏng
    # thổi lên 1,5% — rộng hơn cả thang — nên vẽ ra thì nó phủ kín khung và
    # người đọc tưởng toàn bộ nền là dải, chứ không đọc được gì.
    band = 1.96 * skill.get("stderr", 0.0)
    band_fits = 0 < band <= span
    if band_fits:
        body.append(
            f'<rect x="{PAD_L}" y="{py(band):.1f}" width="{WIDE_W - PAD_R - PAD_L}" '
            f'height="{abs(py(-band) - py(band)):.1f}" fill="var(--ui-ink-soft)" opacity=".13"/>'
        )
    body.append(
        f'<line x1="{PAD_L}" y1="{py(0):.1f}" x2="{WIDE_W - PAD_R}" y2="{py(0):.1f}" '
        f'stroke="var(--ui-ink)" stroke-width="2" opacity=".55"/>'
    )
    clipped = 0
    for i, point in enumerate(points):
        value = point["skill"]
        x, y = px(i), py(value)
        tip = f"{point['date']}: {value:+.3%}".replace(".", ",")
        if value < -span or value > span:
            clipped += 1
            # Tam giác chỉ RA NGOÀI khung: đáy nằm phía trong, đỉnh chạm mép.
            # Chỉ vào trong thì nó trông như một điểm dữ liệu bình thường.
            base = y - 6.0 if value < 0 else y + 6.0
            body.append(
                f'<path d="M{x - 4:.1f} {base:.1f} L{x + 4:.1f} {base:.1f} '
                f'L{x:.1f} {y:.1f} Z" fill="var(--ui-bad)">'
                f"<title>{html.escape(tip)} · ngoài thang</title></path>"
            )
            continue
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="var(--ui-chart-1)" opacity=".5">'
            f"<title>{html.escape(tip)}</title></circle>"
        )
    # Đường tích luỹ NGẮT QUÃNG ở đoạn ra ngoài thang. Vẽ liền thì nó bị ghim
    # bẹt vào mép và trông như một đường dữ liệu thật nằm ở −1,2%, trong khi
    # giá trị thật ở đó là −7%. Đường đứt đoạn nói đúng rằng chỗ ấy không đọc
    # được trên thang này.
    segments: list[list[str]] = []
    for i, point in enumerate(points):
        value = point["cumulative"]
        if -span <= value <= span:
            command = "M" if not segments or not segments[-1] else "L"
            if not segments or segments[-1] == []:
                segments.append([])
                command = "M"
            segments[-1].append(f"{command}{px(i):.1f} {py(value):.1f}")
        elif segments and segments[-1]:
            segments.append([])
    for segment in segments:
        if len(segment) >= 2:
            body.append(
                f'<path d="{" ".join(segment)}" fill="none" stroke="var(--ui-chart-1)" '
                f'stroke-width="2" stroke-linejoin="round"/>'
            )
    # Chú thích PHẢI mô tả đúng những gì được vẽ. Bản trước nói "đường đậm là
    # trung bình tích luỹ, dải xám là ±1,96·SE" trong khi cả hai đều nằm ngoài
    # thang nên không có trên hình — người đọc đi tìm thứ không tồn tại.
    notes = ["Mỗi chấm là kỹ năng của một kỳ; đường ngang đậm là mốc 0."]
    if any(-span <= point["cumulative"] <= span for point in points):
        notes.append("Đường liền là trung bình tích luỹ, ngắt quãng ở đoạn ra ngoài thang.")
    else:
        notes.append(
            "Trung bình tích luỹ nằm trọn ngoài thang nên không vẽ được — "
            "nó bị chính các kỳ hỏng kéo xuống."
        )
    if band_fits:
        notes.append("Dải xám là ±1,96·SE quanh 0.")
    else:
        notes.append(
            "Dải ±1,96·SE rộng hơn cả thang nên không vẽ được: sai số chuẩn bị "
            "chính các kỳ hỏng thổi lên."
        )
    if clipped:
        notes.append(
            f"{clipped} kỳ nằm ngoài thang, vẽ thành tam giác ghim ở mép — các kỳ hỏng "
            "nặng đầu lịch sử. Để chúng định thang thì phần còn lại không đọc được nữa."
        )
    joined = " ".join(notes)
    caption = f'<p class="ui-muted">{joined}</p>'
    return _frame("".join(body), label, w=WIDE_W, h=WIDE_H) + caption



def _num(value, digits: int = 7) -> str:
    """Số thập phân theo quy ước Việt Nam: dấu phẩy làm dấu thập phân.

    Báo cáo cắt ngắn hoặc hỏng sẽ cho ``None`` ở chỗ chờ một con số. Trang
    phải hiện dấu gạch chứ không được ném ``TypeError`` — một trang chẩn đoán
    sập vì thiếu một trường thì đúng lúc cần nhất lại không đọc được gì.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number:
        return "—"
    return f"{number:.{digits}f}".replace(".", ",")


def _count(value: int) -> str:
    """Số đếm với dấu chấm phân nhóm nghìn, đúng quy ước Việt Nam."""
    return f"{int(value):,}".replace(",", ".")


def _pct(value: float, digits: int = 4) -> str:
    return f"{value * 100:+.{digits}f}%".replace(".", ",")


def murphy_table(mu: dict) -> str:
    """Ba thành phần của Brier, kèm ý nghĩa của từng thành phần.

    Cố tình là BẢNG chứ không phải cột chồng. Độ phân giải bằng khoảng 0,02%
    độ bất định, nên trên cột chồng nó là một lát mỏng hơn một pixel — đúng
    kiểu biểu đồ giấu mất chính con số đáng đọc nhất.
    """
    share = mu["resolution_share_of_uncertainty"]
    rows = [
        ("Độ tin cậy", mu["reliability"], "càng nhỏ càng tốt",
         "Nói 24% thì có đúng 24% số lần xảy ra không. Sửa được bằng hiệu chỉnh."),
        ("Độ phân giải", mu["resolution"], "càng lớn càng tốt",
         "Tách được nhóm khả năng cao khỏi nhóm khả năng thấp không. Đây mới là lợi thế dự báo."),
        ("Độ bất định", mu["uncertainty"], "không đụng tới được",
         "Phương sai của chính kết quả. Trần của bài toán, không mô hình nào hạ được."),
    ]
    body = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{_num(value)}</td>"
        f"<td>{html.escape(direction)}</td><td>{html.escape(note)}</td></tr>"
        for name, value, direction, note in rows
    )
    return (
        '<div class="ui-table-wrap"><table class="ui-table ui-r2">'
        "<thead><tr><th>Thành phần</th><th>Giá trị</th><th>Chiều tốt</th><th>Nghĩa là gì</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
        f'<p class="ui-muted">Tin cậy − phân giải + bất định = '
        f"{_num(mu['brier_from_decomposition'])}, khớp đúng Brier của dự báo <b>đã gộp "
        f"nhóm</b> ({_num(mu.get('brier_binned', float('nan')))}). Brier đo trực tiếp trên "
        f"dự báo thô là {_num(mu['brier_direct'])}; chênh lệch "
        f"{_num(mu.get('binning_residual', 0.0))} là phần dư do chia nhóm, không phải sai số "
        f"tính toán. Độ phân giải bằng <b>{_num(share * 100, 4)}%</b> độ bất định.</p>"
    )


def calibration_table(rows: list[dict]) -> str:
    """Bảng cho chính dữ liệu của biểu đồ hiệu chỉnh — để đọc được không cần màu."""
    if not rows:
        return '<p class="ui-table-empty">Chưa đủ dữ liệu.</p>'
    body = "".join(
        "<tr>"
        f"<td>{r['bin'] + 1}</td><td>{_count(r['count'])}</td>"
        f"<td>{_num(r['predicted'], 5)}</td><td>{_num(r['observed'], 5)}</td>"
        f"<td>{_num(r['ci_low'], 5)} – {_num(r['ci_high'], 5)}</td>"
        "</tr>"
        for r in rows
    )
    return (
        '<div class="ui-table-wrap"><table class="ui-table ui-r2 ui-r3 ui-r4">'
        "<thead><tr><th>Nhóm</th><th>Số ô</th><th>Dự báo</th><th>Thực tế</th>"
        "<th>KTC 95%</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def coverage_cards(coverage: dict) -> str:
    """Bao nhiêu phần lịch sử được chấm từ artifact THẬT đã phát hành.

    Đặt ngay đầu trang vì nó đổi cách đọc mọi con số phía dưới: hai nhóm dòng
    cho kết quả lệch nhau rất xa, nên một con số gộp là con số vô nghĩa.
    """
    cards = []
    for row in coverage.get("by_mode", []):
        exact = row["exact_mean_skill"]
        recon = row["reconstructed_mean_skill"]
        exact_text = _pct(exact, 3) if exact == exact else "—"
        recon_text = _pct(recon, 3) if recon == recon else "—"
        cards.append(
            '<article class="ui-kpi">'
            f'<span class="ui-kpi-label">{html.escape(mode_label(row["mode"]))}'
            " · nguồn đánh giá</span>"
            f'<b class="ui-kpi-value">{row["exact_artifact_rows"]}/{row["rows"]}</b>'
            f'<span class="ui-kpi-sub">dòng chấm từ artifact đã phát hành '
            f"({row['exact_share']:.0%}).<br>Kỹ năng nhóm ấy <b>{exact_text}</b>; "
            f"nhóm dựng lại về sau <b>{recon_text}</b>.</span>"
            "</article>"
        )
    joined = "".join(cards)
    return f'<div class="ui-kpi-grid">{joined}</div>'



#: Lời cho từng trạng thái của bộ theo dõi kỹ năng (``skill_monitor``).
_MONITOR_WORDS = {
    "chua_du": "Chưa đủ kỳ để kết luận.",
    "vung_0": "Trong vùng 0 — đúng như một kỳ quay công bằng.",
    "te_hon": "TỆ HƠN đường cơ sở một cách có ý nghĩa — pipeline đã báo động.",
    "hon": "HƠN đường cơ sở một cách có ý nghĩa — phải kiểm lại trước khi tin.",
}


def source_cards(report: dict) -> str:
    """Các con số bên dưới chấm từ đâu, và kỹ năng ngoài mẫu đang ở vùng nào.

    Trang từng chấm một bản DỰNG LẠI bỏ qua hiệu chỉnh — một mô hình khác mô
    hình được công bố — và in "nhóm dựng lại −7,4%" lẫn Đặc Biệt 25,9%. Nay
    chấm thẳng vector đã công bố; thẻ này nói rõ điều ấy và cho thấy kết luận
    của bộ theo dõi, để người đọc không phải tự suy từ biểu đồ.
    """
    monitor = {row["mode"]: row for row in report.get("monitor", [])}
    cards = []
    for mode, block in report.get("modes", {}).items():
        if block.get("source") == "published":
            origin = (
                f"kỳ đã công bố, chấm với kết quả quay thật "
                f"({html.escape(block['first_day'])} → {html.escape(block['last_day'])})."
            )
        else:
            origin = "kỳ DỰNG LẠI — chưa đủ artifact đã công bố để chấm trực tiếp."
        row = monitor.get(mode)
        if row:
            verdict = (
                f"<br>{row['days']} kỳ gần nhất: kỹ năng <b>{_pct(row['mean'], 4)}</b>, "
                f"khoảng [{_pct(row['low'], 4)}, {_pct(row['high'], 4)}] ở "
                f"z={row['z']:g}. {html.escape(_MONITOR_WORDS.get(row['state'], ''))}"
            )
        else:
            verdict = ""
        cards.append(
            '<article class="ui-kpi">'
            f'<span class="ui-kpi-label">{html.escape(mode_label(mode))} · nguồn chấm</span>'
            f'<b class="ui-kpi-value">{block.get("days", 0)}</b>'
            f'<span class="ui-kpi-sub">{origin}{verdict}</span>'
            "</article>"
        )
    return f'<div class="ui-kpi-grid">{"".join(cards)}</div>'


def _staleness(data_dir: Path, report: dict) -> str:
    """Báo cáo có cũ hơn lịch sử đánh giá hiện có không.

    Bước chẩn đoán chạy với ``allow_fail`` trong pipeline, nên khi nó hỏng thì
    builder vẫn dựng trang từ ``report.json`` của lần chạy trước và xuất bản
    như thường. Không có phép đối chiếu này thì một hỏng hóc lặng lẽ có thể
    kéo dài nhiều ngày — đúng cách mà bộ ``post-finalization`` từng đỏ 130 lần
    liên tiếp mà không ai thấy.

    Returns:
        Chuỗi mô tả độ lệch, hoặc chuỗi rỗng khi báo cáo còn đúng thời.
    """
    history = data_dir / "prob_eval" / "ensemble_history.csv"
    if not history.exists():
        return ""
    try:
        latest = str(pd.read_csv(history, usecols=["target_date"])["target_date"].max())
    except (ValueError, KeyError, OSError):
        return ""
    covered = report.get("covers_through")
    if not covered:
        return (
            "Báo cáo không ghi ngày chấm cuối cùng, nên không đối chiếu được với lịch sử "
            f"đánh giá (mới nhất {html.escape(latest)}). Nhiều khả năng nó do một phiên bản "
            "cũ hơn sinh ra."
        )
    if str(covered) < latest:
        return (
            f"Báo cáo chỉ chấm tới {html.escape(str(covered))} trong khi lịch sử đánh giá đã "
            f"có tới {html.escape(latest)}. Bước chẩn đoán nhiều khả năng đã hỏng ở lần chạy "
            "gần nhất và trang này đang hiện số liệu cũ."
        )
    return ""


def build(data_dir: Path, docs_dir: Path) -> Path:
    """Dựng ``docs/model-quality.html`` từ báo cáo chẩn đoán."""
    report_path = data_dir / "model_quality" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    modes = report.get("modes", {})

    blocks = []
    stale = _staleness(data_dir, report)
    if stale:
        blocks.append(
            card(
                f'<p class="ui-muted">{html.escape(stale)}</p>',
                title="⚠ Báo cáo chẩn đoán đang cũ hơn dữ liệu",
                span=12,
                lift=True,
            )
        )
    if report.get("brier_rows_rescaled"):
        blocks.append(
            card(
                f'<p class="ui-muted">{report["brier_rows_rescaled"]} dòng Brier của Đặc Biệt '
                "trong lịch sử đã lưu được đưa về cùng định nghĩa với các dòng mới. "
                "Bản sửa mã đổi <code>categorical_brier</code> từ trung bình sang tổng đã vào "
                "từ lâu nhưng lịch sử thì chưa ai chuyển đổi, nên cột Brier từng chứa hai đơn "
                "vị cạnh nhau và bước nhảy 100 lần trông như mô hình hỏng đột ngột. "
                "Phát hiện bằng bất biến toán học chứ không bằng mốc ngày cứng.</p>",
                title="Đã sửa một lỗi đơn vị trong dữ liệu đã xuất bản",
                span=12,
                lift=True,
            )
        )

    blocks.append(
        card(
            source_cards(report)
            if any("source" in block for block in modes.values())
            else coverage_cards(report.get("coverage", {})),
            title="Nguồn của các con số bên dưới",
            span=12,
            flush=True,
        )
    )

    for mode, block in modes.items():
        name = mode_label(mode)
        mu = block["murphy"]
        blocks.append(
            card(
                murphy_table(mu),
                title=f"Vì sao kỹ năng gần bằng 0 · {name}",
                span=12,
                lift=True,
            )
        )
        blocks.append(
            card(
                calibration_chart(block["calibration"], mu["base_rate"],
                                  f"Biểu đồ hiệu chỉnh {name}")
                + '<p class="ui-muted">Đường chéo đứt là hiệu chỉnh hoàn hảo. Bán kính điểm '
                "theo số ô trong nhóm; thanh dọc là khoảng Wilson 95%. "
                "<b>Điểm đáng đọc nhất là tỉ lệ giữa hai bề rộng</b>: dải xác suất mà mô "
                "hình dám đưa ra hẹp hơn hẳn khoảng tin cậy của chính phép đo, nên toàn bộ "
                "điểm dồn vào giữa khung. Nói cách khác, mức phân biệt của mô hình nhỏ hơn "
                "nhiễu lấy mẫu của chỗ dùng để kiểm nó.</p>"
                + calibration_table(block["calibration"]),
                title=f"Độ hiệu chỉnh · {name}",
                span=6,
                lift=True,
            )
        )
        sharp = block["sharpness"]
        blocks.append(
            card(
                sharpness_chart(sharp, f"Độ sắc {name}")
                + f'<p class="ui-muted">Độ lệch chuẩn của xác suất dự báo là '
                f"{_num(sharp['std'], 5)}, bằng "
                f"{_num(sharp['spread_vs_base'] * 100, 2)}% tỉ lệ nền "
                f"{_num(sharp['base_rate'], 5)}. Một mô hình hiệu chỉnh hoàn hảo mà luôn trả "
                "đúng tỉ lệ nền thì mọi thước đo hiệu chỉnh đều đẹp và mô hình vẫn vô dụng, "
                "nên hai chỉ số này phải đọc cùng nhau.</p>",
                title=f"Độ sắc · {name}",
                span=6,
                lift=True,
            )
        )
        skill = block["skill"]
        verdict = (
            "khác 0 một cách rõ rệt"
            if skill.get("distinguishable_from_zero")
            else "KHÔNG phân biệt được với 0"
        )
        blocks.append(
            card(
                skill_chart(skill, f"Kỹ năng theo thời gian {name}")
                + f'<p class="ui-muted">Trung bình {_pct(skill.get("mean", 0.0), 4)} '
                f"± {_num(1.96 * skill.get('stderr', 0.0) * 100, 4)} điểm phần trăm — "
                f"{verdict}. Tệ hơn đường cơ sở ở "
                f"{skill.get('share_worse_than_baseline', 0):.0%} số kỳ.</p>",
                title=f"Kỹ năng theo thời gian · {name}",
                span=12,
                lift=True,
            )
        )

    page = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {stylesheet_link()}
  <title>Chất lượng mô hình — Phân tích XSMB</title>
</head>
<body>
{app_shell_open("model-quality.html")}
{page_header(
    "Chất lượng mô hình",
    "Phân rã Brier thành phần hiệu chỉnh và phần phân biệt, để thấy kỹ năng đến từ đâu "
    "và thiếu ở đâu. Đây là thước đo xác suất, không phải cam kết kết quả.",
)}
<div class="ui-grid">{"".join(blocks)}</div>
{app_shell_close("model-quality.html")}
</body>
</html>
"""
    # Trang dùng token --ui-chart-1 của biểu định kiểu dùng chung. Dựng trang
    # mà quên ghi lại biểu định kiểu thì token không tồn tại, `var()` rơi về
    # giá trị rỗng và mọi nét dữ liệu tô ĐEN — đúng lỗi đã đo được ở bản đầu.
    write_stylesheet(docs_dir)
    out = docs_dir / "model-quality.html"
    write_page(out, page)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args()
    print("Wrote:", build(Path(args.data_dir), Path(args.docs_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
