from __future__ import annotations

"""Build the static Research Lab page from generated scientific artifacts."""

import argparse
import html
import json
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup


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
            f"<td>{html.escape(str(item.get('name', '')))}</td>"
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
            f"<span>Research firewall · {html.escape(mode.upper())}</span>"
            f"<strong>{int(item.get('production_eligible_count', 0))}</strong>"
            f"<em>eligible / {int(item.get('hypotheses', 0))} giả thuyết · reality p={_fmt(reality.get('p_value'), 3)}</em>"
            "</article>"
        )
    if cross:
        cards.append(
            '<article class="metric-card">'
            '<span>Cross-lag positional</span>'
            f"<strong>{int(cross.get('hypotheses', 0))}</strong>"
            f"<em>hypotheses · research gate pass {int(cross.get('research_gate_pass_count', 0))} · production wired: Không</em>"
            "</article>"
        )
    if conditional:
        cards.append(
            '<article class="metric-card">'
            '<span>ĐB → Loto ngày kế</span>'
            f"<strong>{html.escape(str(conditional.get('current_special_2d', '—')))}</strong>"
            f"<em>ĐB 2D hiện tại · {int(conditional.get('rows', 0))} conditional cells · FDR&lt;.05: {int(conditional.get('fdr_05_count', 0))}</em>"
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
            f"<td>{html.escape(str(r.get('strategy', '')))}</td>"
            f"<td>{html.escape(str(r.get('category', '')))}</td>"
            f"<td>{_fmt(r.get('holdout_precision'), 4)}</td>"
            f"<td>{_fmt(r.get('holdout_lift'), 3)}</td>"
            f"<td>{_fmt(r.get('holdout_q_value_fdr'), 4)}</td>"
            f"<td>{'PASS' if bool(r.get('research_gate_pass')) else '—'}</td>"
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
        ("Aggregate Loto transition 2×2", advanced.get("aggregate_transition", {})),
        ("Weekday × đuôi ĐB 7×10", advanced.get("weekday_special_tail", {})),
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
        "<td>Full-special ACF/Bartlett</td>"
        f"<td>{int(advanced.get('full_special_acf_rows', 0))} lags</td>"
        "<td>—</td>"
        f"<td>{int(advanced.get('full_special_acf_fdr_05', 0))} lag FDR&lt;.05</td>"
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
            f"<td>{'REVIEW' if bool(r.get('research_gate_pass')) else '—'}</td>"
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
    link.string = "🧪 Research Lab"
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

    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VLA Research Lab</title>
<style>
:root{{--bg:#f5f7fb;--panel:#fff;--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#2563eb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1240px;margin:auto;padding:28px}}a{{color:var(--accent)}}.hero{{padding:28px;border-radius:28px;background:#0f172a;color:#fff;margin-bottom:18px}}
.hero h1{{margin:0 0 10px;font-size:clamp(30px,5vw,54px)}}.hero p{{margin:0;max-width:900px;color:#cbd5e1;line-height:1.65}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}.metrics{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:16px 0}}
.metric-card,.card{{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:18px;box-shadow:0 12px 30px rgba(15,23,42,.06)}}
.metric-card span,.metric-card em{{display:block;color:var(--muted);font-style:normal;font-size:12px}}.metric-card strong{{display:block;font-size:34px;margin:5px 0}}
.card h2{{margin:0 0 7px}}.card p{{color:var(--muted);line-height:1.55}}.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:12px}}
th,td{{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}th{{background:#f8fafc}}.warn{{padding:12px 14px;border-radius:14px;background:#fffbeb;border:1px solid #fde68a;color:#92400e;margin:12px 0}}
@media(max-width:850px){{.grid,.metrics{{grid-template-columns:1fr}}main{{padding:15px}}}}
</style></head><body><main>
<section class="hero"><div><a href="index.html" style="color:#bfdbfe">← Trang chính</a></div><h1>Scientific Research Lab</h1>
<p>Không gian kiểm chứng riêng cho thống kê, cầu và strategy. Mọi kết quả tại đây được tách khỏi production predictor cho đến khi vượt chronological holdout, multiple-testing control, effect-size gate và data-snooping reality check.</p></section>
<div class="warn">Research Lab dùng để <b>bác bỏ nhiễu trước khi tin tín hiệu</b>. p-value nhỏ hoặc lift lịch sử cao không đồng nghĩa với lợi thế dự đoán tương lai. Các bảng Legacy completeness và Cross-lag bên dưới <b>không được nối vào production weights</b>.</div>
<section class="metrics">{_firewall_cards(firewall, cross_report, conditional_manifest)}</section>
<section class="grid">
<article class="card"><h2>Randomness & dependence diagnostics</h2><p>Primary tests được hiệu chỉnh Benjamini–Hochberg FDR.</p><div class="table-wrap"><table><thead><tr><th>Test</th><th>Statistic</th><th>p</th><th>q(FDR)</th><th>FDR&lt;.05</th></tr></thead><tbody>{_primary_tests(diagnostics)}</tbody></table></div></article>
<article class="card"><h2>Gan tổng / chạm</h2><p>Khôi phục thống kê mô tả hữu ích từ các repo cũ, không dùng trực tiếp làm xác suất.</p><div class="table-wrap"><table><thead><tr><th>Nhóm</th><th>Gan ngày</th><th>Lần cuối</th></tr></thead><tbody>{_gap_table(touch,sums)}</tbody></table></div></article>
<article class="card"><h2>Legacy completeness · exact semantics</h2><p>Các kiểm định có câu hỏi thống kê khác với battery hiện đại nên được giữ riêng để không mất semantics.</p><div class="table-wrap"><table><thead><tr><th>Diagnostic</th><th>Statistic</th><th>p</th><th>Method / FDR</th></tr></thead><tbody>{_legacy_diagnostics(advanced)}</tbody></table></div></article>
<article class="card"><h2>ĐB {html.escape(current_special or '—')} → Loto ngày kế</h2><p>Conditional matrix chỉ dùng cặp ngày lịch liên tiếp; pEB được shrink về marginal baseline và q là BH-FDR.</p><div class="table-wrap"><table><thead><tr><th>Số</th><th>Trials</th><th>Hits</th><th>p raw</th><th>p EB</th><th>q</th></tr></thead><tbody>{_conditional_table(conditional,current_special)}</tbody></table></div></article>
<article class="card"><h2>Strategy Lab · Loto</h2><div class="table-wrap"><table><thead><tr><th>Strategy</th><th>Nhóm</th><th>Precision</th><th>Lift</th><th>q</th><th>Gate</th></tr></thead><tbody>{_strategy_table(strategy_loto)}</tbody></table></div></article>
<article class="card"><h2>Strategy Lab · Đề</h2><div class="table-wrap"><table><thead><tr><th>Strategy</th><th>Nhóm</th><th>Precision</th><th>Lift</th><th>q</th><th>Gate</th></tr></thead><tbody>{_strategy_table(strategy_de)}</tbody></table></div></article>
</section>
<section class="card" style="margin-top:16px"><h2>Cross-lag positional family</h2><p>Phục hồi family cầu dọc/chéo giữa các ngày khác nhau: concat, lộn, bộ-bóng, chạm và tổng. Mỗi rule chỉ đọc target−lag theo ngày lịch, sau đó qua train/validation/untouched holdout và FDR/Bonferroni. `research gate` chỉ có nghĩa đáng xem tiếp, không phải production eligible.</p><div class="table-wrap"><table><thead><tr><th>Op</th><th>Vị trí A</th><th>Lag A</th><th>Vị trí B</th><th>Lag B</th><th>Holdout lift</th><th>Gate</th></tr></thead><tbody>{_crosslag_table(cross_rules)}</tbody></table></div></section>
<section class="card" style="margin-top:16px"><h2>Research firewall</h2><p>Hệ thống quét 27×27 vị trí cho hai family tail-tail và head-tail, sau đó chia train/validation/holdout theo thời gian. FDR chỉ áp dụng trên train; validation và untouched holdout phải giữ effect/lift, đồng thời max-statistic circular-shift reality check kiểm soát data snooping ở cấp toàn family.</p></section>
</main></body></html>"""
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
    print(f"[OK] research lab -> {out}")


if __name__ == "__main__":
    main()
