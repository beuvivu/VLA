from __future__ import annotations

"""Dựng phòng nghiên cứu tĩnh từ các artifact kiểm định khoa học."""

import argparse
import html
import json
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from ui_locale import mode_label, strategy_label
from ui_theme import card, shell_close, shell_open, tailwind_style_tag
from web_security import security_meta_tags


TEST_LABELS = {
    "de_suffix_uniformity": "Độ đồng đều của hai số cuối giải đặc biệt",
    "all_prize_suffix_uniformity": "Độ đồng đều của hai số cuối mọi giải",
    "de_runs_independence": "Tính độc lập của chuỗi giải đặc biệt",
    "weekday_vs_de_tail": "Quan hệ thứ trong tuần với đuôi đặc biệt",
    "loto_repeat_dependency": "Phụ thuộc lặp lại của lô tô",
}

CATEGORY_LABELS = {
    "bong": "Bóng",
    "cross_prize": "Ghép chéo giải",
    "head_tail": "Đầu / đuôi",
    "kep": "Kép",
    "position": "Vị trí",
    "recency": "Gần đây",
    "repeat": "Lặp lại",
    "special": "Giải đặc biệt",
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


def _firewall_cards(report: dict, cross: dict, conditional: dict) -> str:
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
            '<span>Vị trí chéo độ trễ</span>'
            f"<strong>{int(cross.get('hypotheses', 0))}</strong>"
            f"<em>giả thuyết · qua cổng nghiên cứu {int(cross.get('research_gate_pass_count', 0))} · nối vào vận hành: Không</em>"
            "</article>"
        )
    if conditional:
        cards.append(
            '<article class="metric-card">'
            '<span>ĐB → Loto ngày kế</span>'
            f"<strong>{html.escape(str(conditional.get('current_special_2d', '—')))}</strong>"
            f"<em>ĐB 2 số hiện tại · {int(conditional.get('rows', 0))} ô có điều kiện · FDR&lt;.05: {int(conditional.get('fdr_05_count', 0))}</em>"
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
        ("Chuyển tiếp lô tô tổng hợp 2×2", advanced.get("aggregate_transition", {})),
        ("Thứ trong tuần × đuôi ĐB 7×10", advanced.get("weekday_special_tail", {})),
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
        "<td>ACF/Bartlett toàn giải đặc biệt</td>"
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


def _conditional_table(df: pd.DataFrame, current_special: str, top: int = 10) -> str:
    if df.empty:
        return '<tr><td colspan="6">Chưa có dữ liệu</td></tr>'
    try:
        state = int(current_special)
    except Exception:
        return '<tr><td colspan="6">Chưa có trạng thái ĐB hiện tại</td></tr>'
    view = df[df["special"].astype(int) == state].copy()
    if view.empty:
        return '<tr><td colspan="6">Chưa đủ lịch sử cho trạng thái này</td></tr>'
    view = view.sort_values(["p_eb", "q_value_fdr", "hits"], ascending=[False, True, False]).head(top)
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


def _inject_link(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    if soup.find(id="research-lab-link") is not None or soup.body is None:
        return
    link = soup.new_tag("a", href="research-lab.html", id="research-lab-link")
    link.string = "🧪 Phòng nghiên cứu"
    link["style"] = (
        "position:fixed;right:16px;bottom:16px;z-index:9999;padding:10px 14px;"
        "border-radius:999px;background:#0f172a;color:#fff;text-decoration:none;"
        "font:700 12px/1.2 system-ui;box-shadow:0 10px 28px rgba(15,23,42,.25)"
    )
    soup.body.append(link)
    path.write_text(str(soup), encoding="utf-8")


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
    conditional_manifest = _read_json(data_dir / "conditional" / "manifest.json")
    conditional = _read_csv(data_dir / "conditional" / "loto_nextday_given_special_long.csv")
    current_special = str(conditional_manifest.get("current_special_2d", ""))

    def _table(title, desc, headers, align_cls, rows_html, span=6):
        head = "".join(f"<th>{h}</th>" for h in headers)
        body = (
            f'<div class="vla-table-wrap"><table class="vla-table {align_cls}">'
            f"<thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table></div>"
        )
        intro = f'<p class="vla-muted">{desc}</p>' if desc else ""
        return card(intro + body, title=title, span=span, lift=True)

    cards = "".join([
        _table(
            "Chẩn đoán tính ngẫu nhiên và phụ thuộc",
            "Các phép kiểm định chính được hiệu chỉnh bằng Benjamini–Hochberg FDR.",
            ["Phép kiểm định", "Thống kê", "p", "q (FDR)", "FDR&lt;.05"],
            "vla-r2 vla-r3 vla-r4 vla-m5",
            _primary_tests(diagnostics),
        ),
        _table(
            "Gan tổng / chạm",
            "Khôi phục thống kê mô tả hữu ích từ các repo cũ, không dùng trực tiếp làm xác suất.",
            ["Nhóm", "Gan ngày", "Lần cuối"],
            "vla-r2 vla-m3",
            _gap_table(touch, sums),
        ),
        _table(
            "Kiểm tra tương thích cũ · đúng ngữ nghĩa",
            "Các kiểm định đặt câu hỏi thống kê khác với bộ kiểm tra hiện đại nên được giữ riêng để không làm mất ngữ nghĩa.",
            ["Chẩn đoán", "Thống kê", "p", "Phương pháp / FDR"],
            "vla-r2 vla-r3",
            _legacy_diagnostics(advanced),
        ),
        _table(
            f"ĐB {html.escape(current_special or chr(8212))} → Lô tô ngày kế",
            "Ma trận có điều kiện chỉ dùng cặp ngày lịch liên tiếp; pEB được co về xác suất nền biên và q là BH-FDR.",
            ["Số", "Cỡ mẫu", "Số lần trúng", "p thô", "p EB", "q"],
            "vla-r2 vla-r3 vla-r4 vla-r5 vla-r6",
            _conditional_table(conditional, current_special),
        ),
        _table(
            "Phòng chiến lược · Lô tô",
            "",
            ["Chiến lược", "Nhóm", "Độ chính xác", "Độ nâng", "q", "Cổng"],
            "vla-r3 vla-r4 vla-r5 vla-m6",
            _strategy_table(strategy_loto),
        ),
        _table(
            "Phòng chiến lược · Đặc Biệt",
            "",
            ["Chiến lược", "Nhóm", "Độ chính xác", "Độ nâng", "q", "Cổng"],
            "vla-r3 vla-r4 vla-r5 vla-m6",
            _strategy_table(strategy_de),
        ),
        _table(
            "Họ vị trí chéo độ trễ",
            "Khôi phục họ cầu dọc/chéo giữa các ngày khác nhau: ghép, lộn, bộ-bóng, chạm và tổng. "
            "Mỗi quy tắc chỉ đọc ngày mục tiêu trừ độ trễ theo lịch, sau đó đi qua tập huấn luyện, "
            "kiểm định và tập giữ lại chưa chạm cùng FDR/Bonferroni. “Qua cổng nghiên cứu” chỉ có "
            "nghĩa là đáng xem tiếp, không phải đủ điều kiện vận hành.",
            ["Phép biến đổi", "Vị trí A", "Trễ A", "Vị trí B", "Trễ B", "Độ nâng trên tập giữ lại", "Cổng"],
            "vla-r3 vla-r5 vla-r6 vla-m7",
            _crosslag_table(cross_rules),
            span=12,
        ),
        card(
            "<p class=\"vla-muted\">Hệ thống quét 27×27 vị trí cho hai họ đuôi–đuôi và đầu–đuôi, "
            "sau đó chia huấn luyện/kiểm định/tập giữ lại theo thời gian. FDR chỉ áp dụng trên tập "
            "huấn luyện; tập kiểm định và tập giữ lại chưa chạm phải duy trì cỡ ảnh hưởng/độ nâng, "
            "đồng thời phép kiểm tra thực tế dịch vòng với thống kê cực đại kiểm soát rủi ro dò dữ "
            "liệu trên toàn họ.</p>",
            title="Tường lửa nghiên cứu",
            span=12,
        ),
    ])

    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags()}
{tailwind_style_tag()}
<title>Phòng nghiên cứu VLA</title>
<style>
.rl-hero{{padding:1.75rem;border-radius:var(--vla-r-xl);background:var(--vla-ink);
color:#fff;margin-bottom:1.25rem}}
.rl-hero h1{{color:#fff;margin:.5rem 0 .625rem;font-size:clamp(1.75rem,4vw,2.5rem)}}
.rl-hero p{{margin:0;max-width:60rem;color:#cbd5e1;line-height:1.65}}
.rl-hero a{{color:#bfdbfe}}
.rl-metrics{{display:grid;grid-template-columns:repeat(1,minmax(0,1fr));
gap:1rem;margin-bottom:1.5rem}}
@media(min-width:640px){{.rl-metrics{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(min-width:1024px){{.rl-metrics{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}
.metric-card{{background:var(--vla-surface);border:1px solid var(--vla-border);
border-radius:var(--vla-r-lg);padding:1.125rem;box-shadow:var(--vla-sh-sm)}}
.metric-card span,.metric-card em{{display:block;color:var(--vla-ink-soft);
font-style:normal;font-size:.75rem;line-height:1.5}}
.metric-card strong{{display:block;font-size:2rem;font-weight:600;
color:var(--vla-ink);margin:.25rem 0;letter-spacing:-.02em;
font-variant-numeric:tabular-nums}}
</style></head><body>
{shell_open(wide=True)}
<section class="rl-hero"><div><a href="index.html">← Trang chính</a></div>
<h1>Phòng nghiên cứu khoa học</h1>
<p>Không gian kiểm chứng riêng cho thống kê, cầu và chiến lược. Mọi kết quả tại đây được tách khỏi bộ dự báo vận hành cho đến khi vượt qua tập giữ lại theo thời gian, kiểm soát nhiều phép thử, cổng cỡ ảnh hưởng và kiểm tra thực tế chống dò dữ liệu.</p></section>
<div class="vla-note" style="margin-bottom:1.25rem">Phòng nghiên cứu dùng để <b>bác bỏ nhiễu trước khi tin tín hiệu</b>. Giá trị p nhỏ hoặc độ nâng lịch sử cao không đồng nghĩa với lợi thế dự đoán tương lai. Các bảng kiểm tra tương thích cũ và vị trí chéo độ trễ bên dưới <b>không được nối vào trọng số vận hành</b>.</div>
<section class="rl-metrics">{_firewall_cards(firewall, cross_report, conditional_manifest)}</section>
<div class="vla-grid">{cards}</div>
{shell_close()}
</body></html>"""
    docs_dir.mkdir(parents=True, exist_ok=True)
    out = docs_dir / "research-lab.html"
    out.write_text(page, encoding="utf-8")
    for name in ("index.html", "landing.html", "landing_desktop.html", "statistics.html", "dashboard.html", "model-quality.html"):
        _inject_link(docs_dir / name)
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
