from __future__ import annotations

"""Dựng phòng nghiên cứu tĩnh từ các artifact kiểm định khoa học."""

import argparse
import html
import json
from pathlib import Path
from lottery_codes import lottery_code

import pandas as pd

from ui_locale import mode_label, strategy_label
from ui_theme import (
    card,
    shell_close,
    shell_open,
    stylesheet_link,
    write_stylesheet,
)
from web_security import security_meta_tags
from page_output import write_page


TEST_LABELS = {
    "de_suffix_uniformity": "Độ đồng đều của hai số cuối giải Đặc Biệt",
    "all_prize_suffix_uniformity": "Độ đồng đều của hai số cuối mọi giải",
    "de_runs_independence": "Tính độc lập của chuỗi giải Đặc Biệt",
    "weekday_vs_de_tail": "Quan hệ thứ trong tuần với đuôi Đặc Biệt",
    "loto_repeat_dependency": "Phụ thuộc lặp lại của LOTO",
}

CATEGORY_LABELS = {
    "bong": "Bóng",
    "cross_prize": "Ghép chéo giải",
    "head_tail": "Đầu / đuôi",
    "kep": "Kép",
    "position": "Vị trí",
    "recency": "Gần đây",
    "repeat": "Lặp lại",
    "special": "Giải Đặc Biệt",
    "sum": "Tổng",
    "touch": "Chạm",
}


def _read_json(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def _fmt(value, digits: int = 4) -> str:
    try:
        x = float(value)
        if pd.isna(x):
            return "—"
        return f"{x:.{digits}f}"
    except (TypeError, ValueError, OverflowError):
        return html.escape(str(value)) if value not in (None, "") else "—"


def _count(value) -> str:
    """Giữ số thiếu là chưa biết, phân biệt với số đếm bằng không."""
    return f"{int(value):,}".replace(",", ".") if value is not None else "—"


def _overview(report: dict) -> str:
    """Bảng điều hành chỉ tổng hợp hai chế độ của cùng tường lửa vị trí."""
    modes = report.get("modes", {})

    def combined(key: str):
        values = [modes.get(mode, {}).get(key) for mode in ("loto", "de")]
        return sum(values) if all(value is not None for value in values) else None

    items = (
        ("hypotheses", "Giả thuyết vị trí", combined("hypotheses"), "Hai chế độ LOTO & Đặc Biệt"),
        ("fdr", "Qua FDR · huấn luyện", combined("fdr_significant_train"), "Hiệu chỉnh nhiều phép thử"),
        ("holdout", "Kỳ giữ lại · LOTO", modes.get("loto", {}).get("holdout_days"), "Dữ liệu ngoài tập chọn giả thuyết"),
        ("eligible", "Đủ điều kiện · tường lửa", combined("production_eligible_count"), "Cần xem xét; chưa tự động đưa vào vận hành"),
    )
    cards = "".join(
        f'<article class="rl-stat"><span>{label}</span><strong id="rl-{key}" data-lab-metric>{_count(value)}</strong>'
        f'<small>{hint}</small></article>' for key, label, value, hint in items
    )
    stamp = html.escape(str(report.get("anchor_date") or "Chưa có báo cáo"))
    return (
        '<section class="rl-overview" aria-label="Tóm tắt tường lửa vị trí">'
        f'<div class="rl-section-line"><span>TƯỜNG LỬA VỊ TRÍ</span><span>Báo cáo đến {stamp}</span></div>'
        f'<div class="rl-stat-grid">{cards}</div></section>'
    )


def _network() -> str:
    """Sơ đồ trang trí biểu diễn các nhánh nghiên cứu, không giả lập tiến độ."""
    return (Path(__file__).parent / "templates" / "research_network.html").read_text(encoding="utf-8")


def _primary_tests(diag: dict) -> str:
    rows = []
    for item in diag.get("primary_tests", []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(TEST_LABELS.get(str(item.get('name', '')), str(item.get('name', ''))))}</td>"
            f"<td>{_fmt(item.get('statistic'))}</td>"
            f"<td>{_fmt(item.get('p_value'))}</td>"
            f"<td>{_fmt(item.get('q_value_fdr'))}</td>"
            f"<td>{'Có' if item.get('fdr_05') else 'Không'}</td>"
            "</tr>"
        )
    return "".join(rows) or '<tr><td colspan="5">Chưa có dữ liệu</td></tr>'


def _firewall_cards(report: dict, cross: dict, conditional: dict, bong: dict) -> str:
    cards = []
    for mode, item in report.get("modes", {}).items():
        reality = item.get("reality_check", {})
        cards.append(
            '<article class="metric-card">'
            f"<span>Tường lửa nghiên cứu · {html.escape(mode_label(mode))}</span>"
            f"<strong>{int(item.get('production_eligible_count', 0))}</strong>"
            f"<em>đủ điều kiện / {int(item.get('hypotheses', 0))} giả thuyết · p kiểm tra thực tế={_fmt(reality.get('p_value'), 3)}</em>"
            "</article>"
        )
    if cross:
        cards.append(
            '<article class="metric-card">'
            "<span>Vị trí chéo độ trễ</span>"
            f"<strong>{int(cross.get('hypotheses', 0))}</strong>"
            f"<em>giả thuyết · qua cổng nghiên cứu {int(cross.get('research_gate_pass_count', 0))} · nối vào vận hành: Không</em>"
            "</article>"
        )
    if bong:
        loto = bong.get("modes", {}).get("loto", {})
        check = loto.get("reality_check", {})
        cards.append(
            '<article class="metric-card">'
            "<span>Cầu bóng · 107 ô chữ số</span>"
            f"<strong>{int(loto.get('hypotheses', 0)):,}</strong>".replace(",", ".")
            + f"<em>giả thuyết · qua FDR .05: {int(loto.get('fdr_05_count', 0))} · "
            f"độ nâng tốt nhất {loto.get('best_train_lift', 0):.3f} so với nhiễu "
            f"{check.get('null_max_lift_mean', 0):.3f} · p={check.get('p_value', 0):.2f}</em>"
            "</article>"
        )
    if conditional:
        cards.append(
            '<article class="metric-card">'
            "<span>Đặc Biệt → Loto ngày kế</span>"
            f"<strong>{html.escape(str(conditional.get('current_special_2d', '—')))}</strong>"
            f"<em>Đặc Biệt 2 số hiện tại · {int(conditional.get('rows', 0))} ô có điều kiện · FDR&lt;.05: {int(conditional.get('fdr_05_count', 0))}</em>"
            "</article>"
        )
    return "".join(cards)


def _strategy_table(df: pd.DataFrame, top: int = 10) -> str:
    if df.empty:
        return '<tr><td colspan="6">Chưa có dữ liệu</td></tr>'
    view = df.head(top)
    rows = []
    for _, r in view.iterrows():
        rows.append(
            "<tr>"
            f"<td>{html.escape(strategy_label(r.get('strategy', '')))}</td>"
            f"<td>{html.escape(CATEGORY_LABELS.get(str(r.get('category', '')), str(r.get('category', ''))))}</td>"
            f"<td>{_fmt(r.get('holdout_precision'), 4)}</td>"
            f"<td>{_fmt(r.get('holdout_lift'), 3)}</td>"
            f"<td>{_fmt(r.get('holdout_q_value_fdr'), 4)}</td>"
            f"<td>{'ĐẠT' if bool(r.get('research_gate_pass')) else '—'}</td>"
            "</tr>"
        )
    return "".join(rows)


def _gap_table(touch: pd.DataFrame, sums: pd.DataFrame, top: int = 6) -> str:
    rows = []
    if not touch.empty:
        for _, r in touch.head(top).iterrows():
            rows.append(
                f"<tr><td>Chạm {int(r['digit'])}</td><td>{int(r['gap_days'])}</td><td>{html.escape(str(r.get('last_date', '—')))}</td></tr>"
            )
    if not sums.empty:
        for _, r in sums.head(top).iterrows():
            rows.append(
                f"<tr><td>Tổng {int(r['digit_sum'])}</td><td>{int(r['gap_days'])}</td><td>{html.escape(str(r.get('last_date', '—')))}</td></tr>"
            )
    return "".join(rows) or '<tr><td colspan="3">Chưa có dữ liệu</td></tr>'


def _legacy_diagnostics(advanced: dict) -> str:
    tests = [
        ("Chuyển tiếp LOTO tổng hợp 2×2", advanced.get("aggregate_transition", {})),
        ("Thứ trong tuần × đuôi Đặc Biệt 7×10", advanced.get("weekday_special_tail", {})),
    ]
    rows = []
    for label, item in tests:
        rows.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{_fmt(item.get('statistic'))}</td>"
            f"<td>{_fmt(item.get('p_value'))}</td>"
            f"<td>{html.escape(str(item.get('method', '—')))}</td>"
            "</tr>"
        )
    rows.append(
        "<tr>"
        "<td>ACF/Bartlett toàn giải Đặc Biệt</td>"
        f"<td>{int(advanced.get('full_special_acf_rows', 0))} độ trễ</td>"
        "<td>—</td>"
        f"<td>{int(advanced.get('full_special_acf_fdr_05', 0))} độ trễ có FDR&lt;.05</td>"
        "</tr>"
    )
    return "".join(rows) if rows else '<tr><td colspan="4">Chưa có dữ liệu</td></tr>'


def _crosslag_table(df: pd.DataFrame, top: int = 10) -> str:
    if df.empty:
        return '<tr><td colspan="7">Chưa có dữ liệu</td></tr>'
    view = df.sort_values(
        ["research_gate_pass", "holdout_lift", "validation_lift", "train_q_value_fdr"],
        ascending=[False, False, False, True],
    ).head(top)
    rows = []
    for _, r in view.iterrows():
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(r.get('operator', '')))}</td>"
            f"<td>{html.escape(str(r.get('position_a_name', '')))}</td>"
            f"<td>{int(r.get('lag_a_days', 0))}</td>"
            f"<td>{html.escape(str(r.get('position_b_name', '—')) or '—')}</td>"
            f"<td>{int(r.get('lag_b_days', -1)) if pd.notna(r.get('lag_b_days')) else -1}</td>"
            f"<td>{_fmt(r.get('holdout_lift'), 3)}</td>"
            f"<td>{'CẦN XEM XÉT' if bool(r.get('research_gate_pass')) else '—'}</td>"
            "</tr>"
        )
    return "".join(rows)


def _bong_bridge_table(df: pd.DataFrame, top: int = 10) -> str:
    """Các đường cầu mạnh nhất trên tập huấn luyện, kèm số phận ngoài mẫu.

    Cột quan trọng nhất là hai cột cuối. Một đường cầu có thật thì độ nâng của
    nó phải giữ được khi sang những kỳ chưa từng dùng để chọn nó.
    """
    if df.empty:
        return '<tr><td colspan="5">Chưa có dữ liệu</td></tr>'
    rows = []
    for _, r in df.head(top).iterrows():
        source = (
            f"{html.escape(str(r['slot_a']))} ({html.escape(str(r['op_a']))}, lag {int(r['lag_a'])})"
            f" + {html.escape(str(r['slot_b']))} ({html.escape(str(r['op_b']))}, lag {int(r['lag_b'])})"
        )
        rows.append(
            "<tr>"
            f"<td>{source}</td>"
            f"<td>{_fmt(r.get('train_lift'), 3)}</td>"
            f"<td>{_fmt(r.get('validation_lift'), 3)}</td>"
            f"<td>{_fmt(r.get('holdout_lift'), 3)}</td>"
            f"<td>{_fmt(r.get('train_q_fdr'), 3)}</td>"
            "</tr>"
        )
    return "".join(rows)


def _conditional_table(df: pd.DataFrame, current_special: str, top: int = 10) -> str:
    if df.empty:
        return '<tr><td colspan="6">Chưa có dữ liệu</td></tr>'
    try:
        state = int(current_special)
    except (TypeError, ValueError, OverflowError):
        return '<tr><td colspan="6">Chưa có trạng thái Đặc Biệt hiện tại</td></tr>'
    view = df[df["special"].astype(int) == state].copy()
    if view.empty:
        return '<tr><td colspan="6">Chưa đủ lịch sử cho trạng thái này</td></tr>'
    view = view.sort_values(["p_eb", "q_value_fdr", "hits"], ascending=[False, True, False]).head(
        top
    )
    rows = []
    for _, r in view.iterrows():
        rows.append(
            "<tr>"
            f"<td>{html.escape(lottery_code(r.get('number')))}</td>"
            f"<td>{int(r.get('trials', 0))}</td>"
            f"<td>{int(r.get('hits', 0))}</td>"
            f"<td>{_fmt(r.get('p_raw'), 4)}</td>"
            f"<td>{_fmt(r.get('p_eb'), 4)}</td>"
            f"<td>{_fmt(r.get('q_value_fdr'), 4)}</td>"
            "</tr>"
        )
    return "".join(rows)


def build(data_dir: Path, docs_dir: Path) -> Path:
    research = data_dir / "research"
    desc = data_dir / "descriptive_ext"
    diagnostics = _read_json(research / "scientific_diagnostics.json")
    firewall = _read_json(research / "research_firewall_report.json")
    strategy_loto = _read_csv(research / "strategy_lab_loto.csv")
    strategy_de = _read_csv(research / "strategy_lab_de.csv")
    touch = _read_csv(desc / "gap_touch_loto.csv")
    sums = _read_csv(desc / "gap_digit_sum_loto.csv")

    advanced = _read_json(research / "legacy_advanced" / "manifest.json")
    cross_report = _read_json(research / "crosslag_positional" / "report.json")
    cross_rules = _read_csv(research / "crosslag_positional" / "crosslag_rules.csv")
    bong_report = _read_json(research / "bong_bridge" / "report.json")
    bong_rules = _read_csv(research / "bong_bridge" / "top_rules_loto.csv")
    conditional_manifest = _read_json(data_dir / "conditional" / "manifest.json")
    conditional = _read_csv(data_dir / "conditional" / "loto_nextday_given_special_long.csv")
    current_special = str(conditional_manifest.get("current_special_2d", ""))

    table_index = 0
    anchors = ("rl-diagnostics", "rl-descriptive", "rl-legacy", "rl-conditional",
               "rl-bong", "rl-loto", "rl-special", "rl-crosslag")

    def _table(title, desc, headers, align_cls, rows_html, span=6):
        nonlocal table_index
        anchor = anchors[table_index]
        table_index += 1
        head = "".join(f'<th scope="col">{h}</th>' for h in headers)
        body = (
            f'<div class="ui-table-wrap" tabindex="0" role="region" aria-label="{html.escape(title)}"><table class="ui-table {align_cls}">'
            f"<thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table></div>"
        )
        intro = f'<p class="ui-muted">{desc}</p>' if desc else ""
        return (
            f'<article class="ui-card rl-panel" id="{anchor}">'
            f'<header class="rl-panel-head"><div><p class="rl-eyebrow">HỒ SƠ / {table_index:02d}</p>'
            f'<h2>{title}</h2></div><a class="rl-back" href="#rl-top" aria-label="Về đầu trang">↑</a></header>'
            f'{intro}{body}</article>'
        )

    cards = "".join(
        [
            _table(
                "Chẩn đoán tính ngẫu nhiên và phụ thuộc",
                "Các phép kiểm định chính được hiệu chỉnh bằng Benjamini–Hochberg FDR.",
                ["Phép kiểm định", "Thống kê", "p", "q (FDR)", "FDR&lt;.05"],
                "ui-r2 ui-r3 ui-r4 ui-m5",
                _primary_tests(diagnostics),
            ),
            _table(
                "Gan tổng / chạm",
                "Thời gian chưa xuất hiện của nhóm tổng và chạm. Đây là thống kê mô tả, không dùng trực tiếp làm xác suất.",
                ["Nhóm", "Gan ngày", "Lần cuối"],
                "ui-r2 ui-m3",
                _gap_table(touch, sums),
            ),
            _table(
                "Kiểm tra tương thích cũ · đúng ngữ nghĩa",
                "Các kiểm định đặt câu hỏi thống kê khác với bộ kiểm tra hiện đại nên được giữ riêng để không làm mất ngữ nghĩa.",
                ["Chẩn đoán", "Thống kê", "p", "Phương pháp / FDR"],
                "ui-r2 ui-r3",
                _legacy_diagnostics(advanced),
            ),
            _table(
                f"Đặc Biệt {html.escape(current_special or chr(8212))} → LOTO ngày kế",
                "Ma trận có điều kiện chỉ dùng cặp ngày lịch liên tiếp; pEB được co về xác suất nền biên và q là BH-FDR.",
                ["Số", "Cỡ mẫu", "Số lần trúng", "p thô", "p EB", "q"],
                "ui-r2 ui-r3 ui-r4 ui-r5 ui-r6",
                _conditional_table(conditional, current_special),
            ),
            _table(
                "Cầu bóng trên toàn bộ 107 ô chữ số",
                "Ghép các chữ số từ kết quả đầy đủ của những kỳ trước, với phép biến đổi gốc, bóng dương hoặc bóng âm. "
                "Các đường cầu được chọn trên tập huấn luyện rồi chấm lại trên tập kiểm định và tập giữ lại. "
                "Đối chiếu độ nâng ở cả ba tập để nhận biết tín hiệu chỉ đẹp trong mẫu.",
                ["Đường cầu", "Độ nâng (huấn luyện)", "Kiểm định", "Giữ lại", "q"],
                "ui-r2 ui-r3 ui-r4 ui-r5",
                _bong_bridge_table(bong_rules),
                span=12,
            ),
            _table(
                "Phòng chiến lược · LOTO",
                "",
                ["Chiến lược", "Nhóm", "Độ chính xác", "Độ nâng", "q", "Cổng"],
                "ui-r3 ui-r4 ui-r5 ui-m6",
                _strategy_table(strategy_loto),
            ),
            _table(
                "Phòng chiến lược · Đặc Biệt",
                "",
                ["Chiến lược", "Nhóm", "Độ chính xác", "Độ nâng", "q", "Cổng"],
                "ui-r3 ui-r4 ui-r5 ui-m6",
                _strategy_table(strategy_de),
            ),
            _table(
                "Họ vị trí chéo độ trễ",
                "Khôi phục họ cầu dọc/chéo giữa các ngày khác nhau: ghép, lộn, bộ-bóng, chạm và tổng. "
                "Mỗi quy tắc chỉ đọc ngày mục tiêu trừ độ trễ theo lịch, sau đó đi qua tập huấn luyện, "
                "kiểm định và tập giữ lại chưa chạm cùng FDR/Bonferroni. “Qua cổng nghiên cứu” chỉ có "
                "nghĩa là đáng xem tiếp, không phải đủ điều kiện vận hành.",
                [
                    "Phép biến đổi",
                    "Vị trí A",
                    "Trễ A",
                    "Vị trí B",
                    "Trễ B",
                    "Độ nâng trên tập giữ lại",
                    "Cổng",
                ],
                "ui-r3 ui-r5 ui-r6 ui-m7",
                _crosslag_table(cross_rules),
                span=12,
            ),
            card(
                '<p id="rl-firewall" class="ui-muted">Hệ thống quét 27×27 vị trí cho hai họ đuôi–đuôi và đầu–đuôi, '
                "sau đó chia huấn luyện/kiểm định/tập giữ lại theo thời gian. FDR chỉ áp dụng trên tập "
                "huấn luyện; tập kiểm định và tập giữ lại chưa chạm phải duy trì cỡ ảnh hưởng/độ nâng, "
                "đồng thời phép kiểm tra thực tế dịch vòng với thống kê cực đại kiểm soát rủi ro dò dữ "
                "liệu trên toàn họ.</p>",
                title="Tường lửa nghiên cứu",
                span=12,
            ),
        ]
    )

    css = (Path(__file__).parent / "templates" / "research_lab.css").read_text(encoding="utf-8")
    sample = _count(diagnostics.get("draw_days"))
    start_date = html.escape(str(diagnostics.get("start_date") or "—"))
    end_date = html.escape(str(diagnostics.get("end_date") or "Chưa có báo cáo"))
    navigation = (
        ("rl-protocol", "Quy trình"), ("rl-diagnostics", "Kiểm định nền"),
        ("rl-conditional", "Có điều kiện"), ("rl-bong", "Cầu & vị trí"),
        ("rl-loto", "Chiến lược"), ("rl-glossary", "Thuật ngữ"),
    )
    nav = "".join(f'<a href="#{anchor}">{label}</a>' for anchor, label in navigation)
    stages = (
        ("Dữ liệu", "Kết quả đã công bố", "rl-diagnostics"),
        ("Giả thuyết", "Đăng ký họ quy tắc", "rl-bong"),
        ("Kiểm định", "FDR & cỡ ảnh hưởng", "rl-diagnostics"),
        ("Ngoài mẫu", "Kiểm định / giữ lại", "rl-loto"),
        ("Cổng vận hành", "Xem xét độc lập", "rl-firewall"),
    )
    pipeline = "".join(
        f'<li><a href="#{anchor}"><span class="rl-step">{i:02d}</span><strong>{label}</strong><small>{hint}</small></a></li>'
        for i, (label, hint, anchor) in enumerate(stages, 1)
    )
    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags()}
{stylesheet_link()}
<title>Phòng nghiên cứu AI · Kiểm chứng tín hiệu</title>
<style>
.rl-hero{{background:#091321;color:#edf5ff}}
{css}
</style></head><body data-research-layout="command">
{shell_open(wide=True)}
<div class="rl-lab" id="rl-top">
<div class="rl-topbar"><a href="statistics.html">Thống kê / Phòng nghiên cứu</a><span class="rl-label">AI RESEARCH LAB</span></div>
<section class="rl-hero">
<div class="rl-hero-copy">
<p class="rl-eyebrow"><span class="rl-dot"></span> TRUNG TÂM NGHIÊN CỨU ĐỊNH LƯỢNG</p>
<h1>Khám phá tín hiệu.<br><em>Kiểm chứng bằng dữ liệu.</em></h1>
<p class="rl-lead">Phòng nghiên cứu khoa học về thống kê, mô hình và chiến lược. Mỗi giả thuyết đi qua dữ liệu, kiểm định và bằng chứng ngoài mẫu.</p>
<div class="rl-hero-actions"><a class="rl-primary" href="#rl-diagnostics">Khám phá nghiên cứu <span aria-hidden="true">↗</span></a><a class="rl-secondary" href="#rl-protocol">Xem quy trình ↓</a></div>
<div class="rl-hero-stats"><div><strong>{sample}</strong><span>kỳ trong báo cáo chẩn đoán</span></div><div><span>Phạm vi dữ liệu</span><b>{start_date} → {end_date}</b></div></div>
</div>
<div class="rl-network">{_network()}<div class="rl-network-caption"><span class="rl-dot"></span> Sơ đồ các lớp nghiên cứu</div></div>
</section>
<nav class="rl-nav" aria-label="Các khu nghiên cứu">{nav}</nav>
{_overview(firewall)}
<section class="rl-protocol" id="rl-protocol" aria-labelledby="rl-protocol-title">
<header class="rl-section-heading"><div><p class="rl-eyebrow">PHƯƠNG PHÁP NGHIÊN CỨU</p><h2 id="rl-protocol-title">Từ giả thuyết đến bằng chứng</h2></div><span class="rl-label">QUY TRÌNH KIỂM CHỨNG</span></header>
<ol class="rl-pipeline">{pipeline}</ol>
<div class="rl-principle"><span aria-hidden="true">◈</span><p><strong>Bác bỏ nhiễu trước khi tin tín hiệu.</strong> Giá trị p nhỏ hay độ nâng lịch sử cao cần được kiểm chứng trên dữ liệu ngoài mẫu. Các kết quả nghiên cứu tại đây <b>không được nối vào trọng số vận hành</b>.</p></div>
</section>
<section class="rl-family-section" aria-label="Các họ giả thuyết"><header class="rl-section-heading"><div><p class="rl-eyebrow">BẢN ĐỒ NGHIÊN CỨU</p><h2>Các họ giả thuyết đang được đánh giá</h2></div><span class="rl-label">KẾT QUẢ TỪ BÁO CÁO</span></header>
<section class="rl-metrics" data-evidence-split>{_firewall_cards(firewall, cross_report, conditional_manifest, bong_report) or '<p class="rl-empty">Chưa có báo cáo cho các họ giả thuyết.</p>'}</section></section>
<section class="rl-glossary" id="rl-glossary" aria-label="Thuật ngữ nghiên cứu"><details><summary>Đọc hiểu các chỉ số nghiên cứu <span>p · q · lift · holdout</span></summary><dl><div><dt>p-value & q (FDR)</dt><dd>p-value đo mức tương thích với giả thuyết không; q hiệu chỉnh nhiều phép thử. Riêng p thô và p EB trong bảng có điều kiện là các ước lượng xác suất trúng.</dd></div><div><dt>Độ nâng (lift)</dt><dd>Tỉ lệ trúng chia cho tỉ lệ nền. Cần xem độ nâng ngoài mẫu cùng cỡ mẫu và độ bất định.</dd></div><div><dt>Tập giữ lại (holdout)</dt><dd>Các kỳ được giữ riêng theo thời gian, không dùng để chọn giả thuyết, để đánh giá kết quả ngoài mẫu.</dd></div><div><dt>Cổng nghiên cứu</dt><dd>Kết quả đạt cổng vẫn cần thẩm định độc lập trước khi xem xét đưa vào vận hành.</dd></div></dl></details></section>
<div class="rl-section-heading rl-dossiers"><div><p class="rl-eyebrow">HỒ SƠ THỰC NGHIỆM</p><h2>Bằng chứng & kết quả kiểm định</h2></div><span class="rl-label">ĐỐI CHIẾU TỪNG HỌ</span></div>
<div class="ui-grid rl-evidence-grid">{cards}</div>
<footer class="rl-footer"><span>RESEARCH LAB / EVIDENCE FIRST</span><a href="do-tin-cay.html">Xem đánh giá độ tin cậy ↗</a><a href="#rl-top">Về đầu trang ↑</a></footer>
</div>
{shell_close()}
</body></html>"""
    docs_dir.mkdir(parents=True, exist_ok=True)
    write_stylesheet(docs_dir)
    out = docs_dir / "research-lab.html"
    write_page(out, page)
    # Liên kết phòng nghiên cứu lấy từ SITE_NAV trong khung điều hướng chung.
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--docs-dir", default="docs")
    args = ap.parse_args()
    out = build(Path(args.data_dir), Path(args.docs_dir))
    print(f"[OK] phòng nghiên cứu -> {out}")


if __name__ == "__main__":
    main()
