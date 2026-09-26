from __future__ import annotations

"""Dựng phòng nghiên cứu tĩnh từ các artifact kiểm định khoa học."""

import argparse
import html
import json
from pathlib import Path

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
    except Exception:
        return html.escape(str(value)) if value not in (None, "") else "—"


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
    except Exception:
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
            f"<td>{html.escape(str(r.get('number_str', int(r.get('number', 0)))))}</td>"
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

    def _table(title, desc, headers, align_cls, rows_html, span=6):
        head = "".join(f"<th>{h}</th>" for h in headers)
        body = (
            f'<div class="ui-table-wrap"><table class="ui-table {align_cls}">'
            f"<thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table></div>"
        )
        intro = f'<p class="ui-muted">{desc}</p>' if desc else ""
        return card(intro + body, title=title, span=span, lift=True)

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
                "Khôi phục thống kê mô tả hữu ích từ các repo cũ, không dùng trực tiếp làm xác suất.",
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
                "Họ cầu rộng nhất dự án từng quét: nối một chữ số BẤT KỲ bên trong số đầy đủ "
                "của kỳ trước với một chữ số bất kỳ khác, mỗi chữ số được phép đi qua bóng dương "
                "hoặc bóng âm. 206.082 giả thuyết, gấp 15,7 lần họ vị trí chéo. "
                "Ngũ hành không có cột riêng vì Kim 2–7, Mộc 5–0, Thủy 1–6, Hỏa 3–8, Thổ 4–9 "
                "chính là ánh xạ bóng dương, chỉ khác tên gọi. "
                "Hai cột cuối mới là thứ đáng đọc: chúng chấm lại đúng những đường cầu ấy trên "
                "những kỳ chưa từng dùng để chọn ra chúng.",
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
                '<p class="ui-muted">Hệ thống quét 27×27 vị trí cho hai họ đuôi–đuôi và đầu–đuôi, '
                "sau đó chia huấn luyện/kiểm định/tập giữ lại theo thời gian. FDR chỉ áp dụng trên tập "
                "huấn luyện; tập kiểm định và tập giữ lại chưa chạm phải duy trì cỡ ảnh hưởng/độ nâng, "
                "đồng thời phép kiểm tra thực tế dịch vòng với thống kê cực đại kiểm soát rủi ro dò dữ "
                "liệu trên toàn họ.</p>",
                title="Tường lửa nghiên cứu",
                span=12,
            ),
        ]
    )

    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags()}
{stylesheet_link()}
<title>Phòng nghiên cứu</title>
<style>
/* Dải tiêu đề cố ý tối ở CẢ hai chế độ màu, nên KHÔNG dùng var(--ui-ink):
   token đó lật thành màu sáng ở chế độ tối, để lại chữ trắng trên nền sáng —
   đo được 1,17:1, gần như không đọc nổi. Giá trị cố định là đúng ở đây vì
   thành phần này không đổi theo chế độ. */
.rl-hero{{padding:1.75rem;border-radius:var(--ui-r-xl);background:#0f172a;
color:#fff;margin-bottom:1.25rem}}
.rl-hero h1{{color:#fff;margin:.5rem 0 .625rem;font-size:clamp(1.75rem,4vw,2.5rem)}}
.rl-hero p{{margin:0;max-width:60rem;color:#cbd5e1;line-height:1.65}}
.rl-hero a{{color:#bfdbfe}}
.rl-metrics{{display:grid;grid-template-columns:repeat(1,minmax(0,1fr));
gap:1rem;margin-bottom:1.5rem}}
@media(min-width:640px){{.rl-metrics{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(min-width:1024px){{.rl-metrics{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}
.metric-card{{background:var(--ui-surface);border:1px solid var(--ui-border);
border-radius:var(--ui-r-lg);padding:1.125rem;box-shadow:var(--ui-sh-sm)}}
.metric-card span,.metric-card em{{display:block;color:var(--ui-ink-soft);
font-style:normal;font-size:.75rem;line-height:1.5}}
.metric-card strong{{display:block;font-size:2rem;font-weight:600;
color:var(--ui-ink);margin:.25rem 0;letter-spacing:-.02em;
font-variant-numeric:tabular-nums}}
</style></head><body>
{shell_open(wide=True)}
<section class="rl-hero"><div><a href="index.html">← Trang chính</a></div>
<h1>Phòng nghiên cứu khoa học</h1>
<p>Không gian kiểm chứng riêng cho thống kê, cầu và chiến lược. Mọi kết quả tại đây được tách khỏi bộ dự báo vận hành cho đến khi vượt qua tập giữ lại theo thời gian, kiểm soát nhiều phép thử, cổng cỡ ảnh hưởng và kiểm tra thực tế chống dò dữ liệu.</p></section>
<div class="ui-note" style="margin-bottom:1.25rem">Phòng nghiên cứu dùng để <b>bác bỏ nhiễu trước khi tin tín hiệu</b>. Giá trị p nhỏ hoặc độ nâng lịch sử cao không đồng nghĩa với lợi thế dự đoán tương lai. Các bảng kiểm tra tương thích cũ và vị trí chéo độ trễ bên dưới <b>không được nối vào trọng số vận hành</b>.</div>
<section class="rl-metrics">{_firewall_cards(firewall, cross_report, conditional_manifest, bong_report)}</section>
<div class="ui-grid">{cards}</div>
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
