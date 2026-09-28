"""Trang Độ tin cậy dự báo: Confidence Score ba tầng cho kỳ kế tiếp.

Đọc ``data/confidence/report.json`` (do ``confidence_matrix.py`` sinh) và dựng
``docs/do-tin-cay.html``. Trang nói thẳng tầng của từng con, kèm đủ căn cứ để
người đọc tự kiểm: phân phối null, kiểm ngoài mẫu, phép kiểm giả thuyết can
thiệp và rủi ro/lợi nhuận. Không có con số nào ở đây được làm tròn về phía
đẹp hơn.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from page_output import write_page
from ui_locale import mode_label
from ui_theme import app_shell_close, app_shell_open, card, page_header, stylesheet_link, write_stylesheet
from web_security import security_meta_tags

PAGE = "do-tin-cay.html"

_TIER_BADGE = {"High": "ui-badge-ok", "Medium": "ui-badge-warn", "Low/Noise": "ui-badge-mute"}
_TIER_WORD = {"High": "Cao", "Medium": "Trung bình", "Low/Noise": "Thấp / nhiễu"}


def _pct(value: float | None, digits: int = 1) -> str:
    if value is None or value != value:
        return "—"
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def _num(value: float | None, digits: int = 3) -> str:
    if value is None or value != value:
        return "—"
    return f"{value:.{digits}f}".replace(".", ",")


def _count(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _p(value: float, floor: float) -> str:
    return f"< {_num(floor, 3)}" if value <= floor else _num(value, 3)


def _badge(tier: str) -> str:
    return (f'<span class="ui-badge {_TIER_BADGE.get(tier, "ui-badge-mute")}">'
            f"{html.escape(_TIER_WORD.get(tier, tier))}</span>")


def _table(head: list[str], rows: list[list[str]], numeric: str = "ui-r2 ui-r3 ui-r4") -> str:
    thead = "".join(f"<th>{html.escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return (f'<div class="ui-table-wrap"><table class="ui-table {numeric}">'
            f"<thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table></div>")


def summary_cards(report: dict) -> str:
    cards = []
    for mode in ("loto", "de"):
        counts = report["counts"][mode]
        top = report["max_component"][mode]
        strongest = max(top.values())
        cards.append(
            '<article class="ui-kpi">'
            f'<span class="ui-kpi-label">{html.escape(mode_label(mode))} · kỳ '
            f'{html.escape(report["generated_for"])}</span>'
            f'<b class="ui-kpi-value">{counts["High"]} · {counts["Medium"]} · {counts["Low/Noise"]}</b>'
            '<span class="ui-kpi-sub">con ở tầng Cao · Trung bình · Thấp/nhiễu. '
            f"Thành phần mạnh nhất cả bảng: <b>{_pct(strongest)}</b>.</span>"
            "</article>"
        )
    null = report["null"]
    cards.append(
        '<article class="ui-kpi">'
        '<span class="ui-kpi-label">Đối chứng</span>'
        f'<b class="ui-kpi-value">{_count(null["sims"])}</b>'
        f'<span class="ui-kpi-sub">lịch sử công bằng giả lập, mỗi lịch sử {_count(null["draws"])} kỳ '
        f"× 27 giải. Dữ liệu thật: {_count(report['draws'])} kỳ "
        f"({html.escape(report['first_draw'])} → {html.escape(report['last_draw'])}).</span>"
        "</article>"
    )
    return f'<div class="ui-kpi-grid">{"".join(cards)}</div>'


def rules_card(report: dict) -> str:
    naive = report["naive_false_alarm"]
    th = report["thresholds"]
    return (
        '<p class="ui-muted">Mỗi con có ba thành phần: <b>Bayes</b> (hậu nghiệm xác suất về cao '
        "hơn tỉ lệ nền), <b>Markov</b> (xác suất về theo đúng trạng thái kỳ trước của con đó) và "
        "<b>Cầu</b> (cầu vị trí tốt nhất ghép ra con đó từ kỳ vừa quay). Tin cậy của một thành "
        "phần là tỉ lệ lịch sử công bằng mà <b>tín hiệu mạnh nhất của cả họ</b> còn yếu hơn nó — "
        "tức 1 − p đã hiệu chỉnh cho việc soi nhiều con, nhiều cặp, nhiều cầu cùng lúc.</p>"
        + _table(
            ["Tầng", "Điều kiện", "Score"],
            [
                [_badge("High"), f"cả ba thành phần &gt; {_pct(th['high'], 0)}", "thành phần yếu nhất"],
                [_badge("Medium"), f"ít nhất hai thành phần ≥ {_pct(th['medium'], 0)}",
                 "thành phần mạnh thứ hai"],
                [_badge("Low/Noise"), "còn lại — bỏ qua / gắn cờ nhiễu", "thành phần mạnh thứ hai"],
            ],
            numeric="",
        )
        + '<p class="ui-muted">Vì sao không dùng thẳng hậu nghiệm Bayes: trong các lịch sử '
        f"hoàn toàn ngẫu nhiên, <b>{_pct(naive['bayes_99'])}</b> có ít nhất một con đạt "
        f"hậu nghiệm &gt; 99%, <b>{_pct(naive['bayes_95'])}</b> có một con &gt; 95%; bản 60 kỳ "
        f"gần nhất (kiểu \"đang nóng\") cho con &gt; 85% ở <b>{_pct(naive['bayes60_85'])}</b> "
        "lịch sử. Con số ấy nói về việc chọn con đẹp nhất trong 100 con, không nói về kỳ tới.</p>"
    )


def matrix_card(report: dict, mode: str) -> str:
    rows = [r for r in report["matrix"] if r["mode"] == mode]
    ranked = sorted(rows, key=lambda r: (-r["score"], r["number"]))
    shown = [r for r in ranked if r["published"]]
    shown += [r for r in ranked if not r["published"]][: max(0, 10 - len(shown))]
    shown = sorted(shown, key=lambda r: (-r["score"], r["number"]))

    def line(r):
        mark = " <small>(đang công bố)</small>" if r["published"] else ""
        # Tầng và Score đứng ngay sau số: trên điện thoại bảng cuộn ngang, và
        # thứ người đọc cần trước tiên phải nằm trong khung nhìn đầu.
        return [
            f"<b>{html.escape(r['number'])}</b>{mark}",
            _badge(r["tier"]),
            _pct(r["score"]),
            f"{_num(r['naive_bayes'], 3)} → <b>{_pct(r['c_bayes'])}</b>",
            f"{_num(r['markov_signal'], 2)} → <b>{_pct(r['c_markov'])}</b>",
            f"{_pct(r['cau_rate'], 2)} → <b>{_pct(r['c_cau'])}</b>",
        ]

    head = ["Số", "Tầng", "Score", "Bayes: hậu nghiệm → tin cậy", "Markov: z → tin cậy",
            "Cầu: tỉ lệ trúng → tin cậy"]
    numeric = "ui-r3 ui-r4 ui-r5 ui-r6"
    full = _table(head, [line(r) for r in sorted(rows, key=lambda r: r["number"])], numeric)
    return (
        _table(head, [line(r) for r in shown], numeric)
        + f'<details class="ui-details"><summary>Cả 100 con {html.escape(mode_label(mode))}</summary>'
        f"{full}</details>"
    )


def families_card(report: dict) -> str:
    fams = report["families"]
    floor = 1.0 / 1001
    strict = 0.05 / len(fams)
    rows = []
    for f in fams:
        if f["p"] < strict:
            verdict = "khác ngẫu nhiên, qua hiệu chỉnh"
        elif f["p"] < 0.05:
            verdict = "đạt ngưỡng đơn lẻ, KHÔNG qua hiệu chỉnh"
        else:
            verdict = "trong vùng ngẫu nhiên"
        rows.append([
            html.escape(f["label"]), _count(f["size"]),
            _num(f["observed"], 4), _num(f["null_median"], 4), _p(f["p"], floor),
            html.escape(verdict),
        ])
    return (
        _table(["Trục khảo sát", "Cỡ họ", "Thật", "Trung vị ngẫu nhiên", "p", "Kết luận"], rows,
               numeric="ui-r2 ui-r3 ui-r4 ui-r5")
        + f'<p class="ui-muted">p là tỉ lệ lịch sử công bằng có tín hiệu mạnh nhất của họ ≥ tín '
        f"hiệu thật. Soi {len(fams)} họ cùng lúc nên ngưỡng Bonferroni là "
        f"{_num(strict, 4)}.</p>"
    )


def oos_card(report: dict) -> str:
    rows = [
        [html.escape(r["label"]),
         _pct(r["in_sample"], 2) if r.get("in_sample") is not None else "—",
         f"{_pct(r['rate'], 2)} ({_count(r['hits'])}/{_count(r['n'])})",
         _pct(r["base"], 2), _num(r["z"], 2)]
        for r in report["out_of_sample"]
    ]
    if not rows:
        return '<p class="ui-table-empty">Chưa đủ lịch sử để tách mẫu.</p>'
    return (
        _table(["Tín hiệu chọn trên 2015–2023", "Trong mẫu", "Ngoài mẫu (2024 → nay)", "Nền", "z"],
               rows)
        + '<p class="ui-muted">Tín hiệu thật thì phải còn khi đổi sang dữ liệu nó chưa thấy. '
        "|z| &lt; 2 nghĩa là ngoài mẫu không phân biệt được với tỉ lệ nền.</p>"
    )


def intervention_card(report: dict) -> str:
    block = report.get("intervention")
    if not block:
        return '<p class="ui-table-empty">Chưa có bảng kết quả đầy đủ để kiểm.</p>'
    rows = [
        [html.escape(t["label"]), html.escape(t["detail"]), _num(t["p"], 3), _num(t["p_holm"], 3)]
        for t in block["tests"]
    ]
    return (
        '<p class="ui-muted">Không phép kiểm nào chứng minh được "không có can thiệp". Câu hỏi '
        "trả lời được là: nếu có sắp đặt, nó có để lại dấu vết nào trên kết quả công bố mà người "
        "ngoài khai thác được không. Bốn dấu vết thường gặp nhất:</p>"
        + _table(["Dấu vết", "Số đo", "p", "p (Holm)"], rows, numeric="ui-r3 ui-r4")
        + '<p class="ui-muted">p (Holm) ≥ 0,05 ở mọi dòng nghĩa là kết quả công bố không mang dấu '
        "vết khai thác được. Một sắp đặt nhắm vào những con <b>được đặt nhiều</b> thì không hiện "
        "trên kết quả — và khi ấy, theo những cầu phổ biến là theo đúng những con dễ bị né nhất.</p>"
    )


def risk_card(report: dict) -> str:
    risk = report["risk"]
    dist = risk["numbers_hit"]
    total = sum(dist) or 1
    head = [str(i) for i in range(min(len(dist), 6))]
    cells = [_pct(dist[i] / total) for i in range(min(len(dist), 5))]
    tail = sum(dist[5:]) / total if len(dist) > 5 else 0.0
    if len(dist) > 5:
        head[5] = "≥ 5"
        cells.append(_pct(tail))
    de_line = (
        f" Mười con Đặc Biệt đang công bố chứa con về trong {_pct(risk['de_hit_share'])} số kỳ "
        "(đoán bừa 10 con: 10%)."
        if risk.get("de_hit_share") is not None else ""
    )
    return (
        f'<p class="ui-muted">{_count(risk["scenarios"])} kỳ kế tiếp giả lập với '
        f"{len(risk['picks'])} con LOTO {', '.join(html.escape(p) for p in risk['picks'])}: "
        "số con trong nhóm có về.</p>"
        + _table(head, [cells], numeric="")
        + f'<p class="ui-muted">Trung bình {_num(risk["mean_occurrences"], 2)} lượt về mỗi kỳ.'
        f"{de_line} Hoà vốn cần trả ít nhất <b>{_num(risk['breakeven_loto'], 2)} lần</b> tiền "
        f"đặt cho mỗi lượt về LOTO và <b>{_num(risk['breakeven_de'], 0)} lần</b> cho Đặc Biệt; "
        "mọi mức trả thấp hơn cho kỳ vọng âm. Vì không con nào có xác suất khác tỉ lệ nền, "
        "<b>chọn con nào cũng không đổi được kỳ vọng</b>: rủi ro chỉ giảm khi giảm số tiền "
        "đặt, không giảm được bằng cách chọn số.</p>"
    )


def feedback_card(report: dict) -> str:
    fb = report.get("feedback") or {}
    words = {"chua_du": "chưa đủ kỳ", "vung_0": "vùng 0", "te_hon": "TỆ HƠN nền", "hon": "HƠN nền"}
    rows = []
    for check in fb.get("monitor", []):
        mode = check["mode"]
        scores = fb.get("modes", {}).get(mode, {})
        rows.append([
            html.escape(mode_label(mode)),
            f"{_num(scores.get('logloss_model'), 6)} / {_num(scores.get('logloss_base'), 6)}",
            f"{_num(scores.get('brier_model'), 6)} / {_num(scores.get('brier_base'), 6)}",
            f"{check['days']} kỳ: {html.escape(words.get(check['state'], check['state']))}",
        ])
    if not rows:
        return '<p class="ui-table-empty">Chưa có kỳ đã công bố để chấm.</p>'
    return (
        _table(["", "Log-loss mô hình / nền", "Brier mô hình / nền", "Bộ theo dõi (z = 3)"], rows)
        + '<p class="ui-muted">Vòng phản hồi chấm đúng vector xác suất đã công bố trước kỳ quay '
        'với kết quả thật; chi tiết ở trang <a href="model-quality.html">Chất lượng mô hình</a>. '
        "Trọng số chỉ được đổi khi bản mới thắng cả mặc định lẫn dự báo hằng số trên dữ liệu "
        "chưa thấy — đổi theo biến động là cách chắc nhất để khớp nhiễu.</p>"
    )


def render(report: dict) -> str:
    blocks = [
        card(summary_cards(report), title="Kết luận cho kỳ kế tiếp", span=12, flush=True),
        card(rules_card(report), title="Luật ba tầng và vì sao phải hiệu chỉnh", span=12, lift=True),
        card(matrix_card(report, "loto"), title="Ma trận suy luận · LOTO", span=12, lift=True),
        card(matrix_card(report, "de"), title="Ma trận suy luận · Đặc Biệt", span=12, lift=True),
        card(families_card(report), title="Các trục cầu kèo so với ngẫu nhiên", span=12, lift=True),
        card(oos_card(report), title="Kiểm ngoài mẫu", span=12, lift=True),
        card(intervention_card(report), title="Giả thuyết kỳ quay bị sắp đặt", span=12, lift=True),
        card(risk_card(report), title="Rủi ro / lợi nhuận", span=12, lift=True),
        card(feedback_card(report), title="Vòng phản hồi", span=12, lift=True),
    ]
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {stylesheet_link()}
  <title>Độ tin cậy dự báo — Phân tích XSMB</title>
</head>
<body>
{app_shell_open(PAGE)}
{page_header(
    "Độ tin cậy dự báo",
    "Confidence Score ba tầng cho từng con, tính bằng Bayes, Markov và cầu vị trí rồi đối chứng "
    "với hàng nghìn lịch sử quay công bằng. Thước đo xác suất, không phải lời khuyên đặt cược.",
)}
<div class="ui-grid">{"".join(blocks)}</div>
{app_shell_close(PAGE)}
</body>
</html>
"""


def build(data_dir: Path, docs_dir: Path) -> Path:
    """Dựng ``docs/do-tin-cay.html`` từ ``data/confidence/report.json``."""
    report = json.loads((data_dir / "confidence" / "report.json").read_text(encoding="utf-8"))
    write_stylesheet(docs_dir)
    out = docs_dir / PAGE
    write_page(out, render(report))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args()
    print("Wrote:", build(Path(args.data_dir), Path(args.docs_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
