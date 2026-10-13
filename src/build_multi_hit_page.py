"""Trang «Lô VIP nhiều nháy»: con số về ≥ 2 nháy và cặp xiên 2 cho kỳ tới, in TỪ phép đo.

Đọc ``data/multi_hit/vip.json`` và ``data/multi_hit/benchmark.json`` (do ``multi_hit_report.py``
sinh) rồi dựng ``docs/lo-vip-nhieu-nhay.html``. Trang gọn theo yêu cầu ngày 13-10-2026: năm con, năm
cặp và một dòng số đo kiểm chứng cho mỗi khối ở trên cùng; phần giải thích thu vào mục «Chi tiết
phép đo». Không con số hay kết luận nào ở đây được đặt tay:

* tỉ lệ trúng, khoảng tin cậy, z, p và mức tin của bộ lọc là kiểm chứng walk-forward ngoài mẫu
  trên mọi kỳ đã quay;
* "hơn / không hơn chọn bừa" suy từ mức tin ấy (``multi_hit_vip.model_confidence``) và từ việc
  ứng viên của lượt thử thứ hai có qua được giai đoạn kiểm hay không;
* phép kiểm độ nhạy cho biết một kết luận âm có nghĩa: cùng giao thức PHẢI bắt được tín hiệu nhẹ
  cài sẵn, nếu không thì trang ghi "chưa kết luận" thay vì "không hơn".

Đây là khung thách đấu, không vào tổ hợp xác suất của pipeline.
"""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import NamedTuple

from lab_ui import lab_card as card, lab_footer, lab_hero, lab_styles
from multi_hit_report import SECOND_ROUND_UNTIL, benchmark_is_valid, load_history, vip_status
from multi_hit_vip import CONFIDENCE_P
from page_output import write_page
from ui_theme import app_shell_close, app_shell_open, stylesheet_link, write_stylesheet
from web_security import security_meta_tags

PAGE = "lo-vip-nhieu-nhay.html"
DATA_DIR = "multi_hit"

#: Tên hiển thị của các chiến lược trong ``multi_hit_benchmark.strategy_scores``.
STRATEGY_LABELS = {
    "random": "Chọn bừa (đối chứng)",
    "multi_hot_30": "Nhiều kỳ ≥ 2 nháy nhất · 30 kỳ",
    "multi_hot_100": "Nhiều kỳ ≥ 2 nháy nhất · 100 kỳ",
    "multi_hot_365": "Nhiều kỳ ≥ 2 nháy nhất · 365 kỳ",
    "multi_hot_all": "Nhiều kỳ ≥ 2 nháy nhất · toàn lịch sử",
    "nhay_hot_7": "Nhiều nháy nhất · 7 kỳ",
    "nhay_hot_30": "Nhiều nháy nhất · 30 kỳ",
    "nhay_hot_100": "Nhiều nháy nhất · 100 kỳ",
    "nhay_hot_365": "Nhiều nháy nhất · 365 kỳ",
    "nhay_hot_all": "Nhiều nháy nhất · toàn lịch sử",
    "nhay_cold_30": "Ít nháy nhất · 30 kỳ",
    "nhay_cold_365": "Ít nháy nhất · 365 kỳ",
    "gan_longest": "Gan lâu nhất",
    "gan_shortest": "Vừa về gần nhất",
    "repeat_yesterday": "Lặp số nháy kỳ trước",
    "repeat_multi_yesterday": "Lặp con ≥ 2 nháy kỳ trước",
    "weekday_52": "Cùng thứ trong tuần · 52 tuần",
    "position_bias_all": "Thiên lệch theo vị trí giải · toàn lịch sử",
    "position_bias_365": "Thiên lệch theo vị trí giải · 365 kỳ",
    "digit_bias": "Thiên lệch theo chữ số",
    "vip_v1": "Bộ lọc VIP (lượt một)",
    "logistic_all_features": "Hồi quy logistic · mọi đặc trưng",
    "gbm_all_features": "Cây tăng cường · mọi đặc trưng",
}

_LEVEL_WORD = {"High": "Cao", "Medium": "Trung bình", "Low": "Thấp"}
#: Ngưỡng ``z`` mà một chiến lược ở giai đoạn kiểm "trông như có tín hiệu" khi đọc lướt.
Z_GLANCE = 2.0


# --------------------------------------------------------------------------- định dạng


def _pct(value: float | None, digits: int = 2) -> str:
    if value is None or value != value:
        return "—"
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def _num(value: float | None, digits: int = 2, *, sign: bool = False) -> str:
    if value is None or value != value:
        return "—"
    return f"{value:{'+' if sign else ''}.{digits}f}".replace(".", ",")


def _count(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


def _p(value: float) -> str:
    return "< 0,001" if value < 0.001 else _num(value, 3)


def _date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def _table(head: list[str], rows: list[list[str]], numeric: str) -> str:
    thead = "".join(f"<th>{html.escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return (f'<div class="ui-table-wrap"><table class="ui-table {numeric}">'
            f"<thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table></div>")


def _confidence_rule() -> str:
    return (f"p luôn hợp lệ trên các kỳ tiến cứu — Cao: lift > 1 và p < {_num(CONFIDENCE_P['High'], 2)} · "
            f"Trung bình: lift > 1 và p < {_num(CONFIDENCE_P['Medium'], 2)} · còn lại Thấp")


def _prospective_line(pro: dict) -> str:
    if not pro["draws"]:
        return f"Chưa có kỳ quay nào sau ngày {_date(pro['after'])}, nên chưa có bằng chứng tiến cứu."
    return (f"{_count(pro['draws'])} kỳ quay sau ngày {_date(pro['after'])}: top-k trúng "
            f"{_count(pro['hits'])} lượt so với {_num(pro['expected'], 1)} của chọn bừa, p luôn hợp lệ = "
            f"{_p(pro['p_anytime'])}.")


def strategy_label(name: str) -> str:
    return STRATEGY_LABELS.get(name, name)


# --------------------------------------------------------------------------- kết luận


class Loaded(NamedTuple):
    """Hai tệp đo đã đối chiếu với lịch sử hiện tại."""

    vip: dict | None
    bench: dict | None
    vip_state: str          # "current" | "behind" | "invalid" | "missing"
    last_date: str          # kỳ mới nhất của sổ kết quả
    behind_by: int          # số kỳ sổ có thêm sau lần đo bộ lọc


def load(data_dir: Path) -> Loaded:
    """Đọc hai tệp đo và đối chiếu từng tệp với lịch sử hiện tại.

    Bước đo có thể hỏng giữa chừng (pipeline chạy mềm). Hai tệp vì thế có thể là số đo của một lịch
    sử khác: ``vip.json`` của hôm qua sau khi đã có kỳ mới, hay ``benchmark.json`` của một lịch sử
    mà một kỳ cũ đã được sửa. Tệp bộ lọc không khớp thì trang không in top-k cho một kỳ đã quay;
    tệp lượt hai không phải số đo của đúng đoạn lịch sử đã đăng ký (đến ``SECOND_ROUND_UNTIL``) thì
    bị bỏ.
    """
    folder = data_dir / DATA_DIR

    def read(name: str) -> dict | None:
        """Tệp đọc không được (cụt, hỏng) thì trả ``{}``: có tệp nhưng không phải số đo hợp lệ."""
        path = folder / name
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    draws, labels = load_history(data_dir)
    vip, bench = read("vip.json"), read("benchmark.json")
    state = "missing" if vip is None else vip_status(vip, draws, labels)
    if state == "invalid":
        print(f"data/{DATA_DIR}/vip.json không khớp lịch sử hiện tại — không in số đo.")
        vip = None
    if bench is not None and not benchmark_is_valid(bench, draws, labels):
        print(f"data/{DATA_DIR}/benchmark.json không khớp đoạn lịch sử đã đăng ký — không in.")
        bench = None
    behind = len(draws) - int(vip["draws"]) if vip is not None else 0
    return Loaded(vip, bench, state, labels[-1], behind)


def verdict(vip: dict, bench: dict | None) -> dict:
    """Kết luận của trang, rút TỪ số đo; không có nhánh nào chọn câu chữ theo ý người viết.

    * ``vip_beats_random``: mức tin của bộ lọc là Trung bình/Cao, tức lift > 1 và p một phía < 0,05
      trên kiểm chứng walk-forward.
    * ``second_round_passes``: ứng viên duy nhất của lượt thử thứ hai qua giai đoạn kiểm.
    * ``protocol_sensitive``: cùng giao thức bắt được tín hiệu cài sẵn. Không bắt được — hoặc
      CHƯA CÓ số đo lượt hai và phép kiểm độ nhạy (thiếu tệp, hay tệp bị loại vì lịch sử đã đổi) —
      thì một kết luận âm không có căn cứ: trang ghi "chưa kết luận".
    """
    beats = vip["confidence"] in ("High", "Medium")
    second = None if bench is None else bool(bench["candidate_passes"])
    # Đủ nhạy = tỉ lệ đạt trên nhiều lịch sử cài tín hiệu ≥ ngưỡng đặt trước, không phải một lượt may.
    sensitive = None if bench is None else bool(bench["power"]["sensitive"])
    reason = ""
    if beats or second:
        state = "hon"
    elif sensitive is None:
        state, reason = "chua-ket-luan", "thieu-so-do"
    elif sensitive is False:
        state, reason = "chua-ket-luan", "giao-thuc-mu"
    else:
        state = "khong-hon"
    return {"state": state, "reason": reason, "vip_beats_random": beats,
            "second_round_passes": second, "protocol_sensitive": sensitive}


_HEADLINE = {
    ("hon", ""): "Có bằng chứng hơn chọn bừa — cần kiểm lại trên các kỳ chưa từng thấy",
    # Không bác bỏ được "không kỹ năng" chưa phải là chứng minh không có lợi thế: lợi thế nhỏ hơn mức
    # phép kiểm độ nhạy thấy được vẫn tương thích với số đo. Vì vậy tiêu đề nói "không có bằng chứng".
    ("khong-hon", ""): "Không có bằng chứng hơn chọn bừa",
    ("chua-ket-luan", "giao-thuc-mu"): "Chưa kết luận được: giao thức không bắt được tín hiệu cài sẵn",
    ("chua-ket-luan", "thieu-so-do"): "Chưa kết luận được: chưa có số đo của lượt thử thứ hai và "
                                      "phép kiểm độ nhạy",
}


#: Luật chọn cặp không có lượt thử thứ hai hay phép kiểm độ nhạy riêng, nên khi chưa đạt thì chỉ nói
#: "chưa có bằng chứng", không bao giờ "không hơn".
_PAIR_HEADLINE = {
    "hon": "Có bằng chứng hơn chọn bừa — cần kiểm lại trên các kỳ chưa từng thấy",
    "chua-co-bang-chung": "Chưa có bằng chứng hơn chọn bừa",
}


def pair_verdict(section: dict) -> str:
    """Kết luận của khối cặp, rút từ mức tin (p luôn hợp lệ trên các kỳ tiến cứu)."""
    return "hon" if section["confidence"] in ("High", "Medium") else "chua-co-bang-chung"


def verdict_text(vip: dict, bench: dict | None) -> tuple[str, str]:
    """(tiêu đề, đoạn giải thích) của kết luận, mọi con số lấy từ hai tệp đo."""
    v = verdict(vip, bench)
    bt = vip["backtest"]
    parts = [
        f"Trên {_count(bt['draws'])} kỳ ({_date(bt['first_date'])} → {_date(bt['last_date'])}), "
        f"mỗi kỳ chấm bằng trọng số chọn trên {vip['config']['weight_window']} kỳ ngay trước nó, "
        f"top-{vip['config']['top_k']} của bộ lọc trúng ≥ 2 nháy {_count(bt['hits'])}/"
        f"{_count(bt['picks'])} lượt ({_pct(bt['rate'])}); chọn bừa trên chính các kỳ ấy kỳ vọng "
        f"{_num(bt['expected'], 1)} lượt ({_pct(bt['random_rate'])}). "
        f"z = {_num(bt['z'], 2, sign=True)}, p một phía = {_p(bt['p_value'])}. Đây là mô tả HỒI CỨU: "
        f"bộ lọc được thiết kế sau khi đã xem lịch sử ấy, nên mức tin chỉ tính trên các kỳ quay sau ngày "
        f"{_date(vip['prospective']['after'])}, bằng p luôn hợp lệ vì trang xem lại mỗi ngày. "
        + _prospective_line(vip["prospective"])
        + f" → mức tin {_LEVEL_WORD.get(vip['confidence'], vip['confidence'])}."
    ]
    if bench is not None:
        ct = bench["candidate_test"]
        tried = sum(1 for s in bench["strategies"] if s["name"] != "random")
        parts.append(
            f"Lượt thử thứ hai dò {tried} chiến lược, chọn trước "
            f"«{strategy_label(bench['candidate'])}» trên giai đoạn phát triển rồi kiểm một lần trên "
            f"{_count(bench['test_draws'])} kỳ cuối: {_pct(ct['rate'])} so với {_pct(bench['base_test'])} "
            f"của chọn bừa, p = {_p(ct['p'])} — "
            + ("ĐẠT" if v["second_round_passes"] else "không đạt")
            + f" ngưỡng α = {_num(bench['alpha'], 2)}."
        )
        pw = bench["power"]
        parts.append(
            f"Cùng giao thức trên {pw['runs']} lịch sử giả định có cài tín hiệu nhẹ đạt ở "
            f"{pw['passes']}/{pw['runs']} lịch sử (độ nhạy {_pct(pw['rate'], 0)}, ngưỡng đặt trước "
            f"{_pct(pw['required'], 0)}), "
            + ("nên phép đo đủ nhạy để thấy một lợi thế cỡ ấy; nó không loại trừ được một lợi thế nhỏ "
               "hơn." if v["protocol_sensitive"] else "nên kết luận âm ở đây chưa đủ căn cứ.")
        )
    else:
        parts.append("Chưa có số đo của lượt thử thứ hai, nên chưa biết phép đo có đủ nhạy để thấy "
                     "một tín hiệu nếu nó có.")
    return _HEADLINE[(v["state"], v["reason"])], " ".join(parts)


# --------------------------------------------------------------------------- các khối


def conclusion_card(vip: dict, bench: dict | None) -> str:
    headline, text = verdict_text(vip, bench)
    bt = vip["backtest"]
    pro = vip["prospective"]
    lo, hi = bt["ci95"]
    kpis = [
        ("Bộ lọc VIP · hồi cứu", _pct(bt["rate"]),
         f"KTC 95% {_pct(lo)} – {_pct(hi)} (theo cụm kỳ, deff {_num(bt['design_effect'], 2)}) · "
         f"{_count(bt['hits'])}/{_count(bt['picks'])} lượt"),
        ("Chọn bừa cùng kỳ", _pct(bt["random_rate"]),
         f"Lý thuyết P(X ≥ 2), X ~ Nhị thức(27; 1/100): {_pct(vip['base_theory'], 3)}"),
        ("So với chọn bừa · hồi cứu", f"×{_num(bt['lift'], 3)}",
         f"z = {_num(bt['z'], 2, sign=True)} · p một phía = {_p(bt['p_value'])} (mô tả)"),
        (f"Tiến cứu sau {_date(pro['after'])}", f"{_count(pro['draws'])} kỳ",
         (f"trúng {_count(pro['hits'])} / chọn bừa {_num(pro['expected'], 1)} · p luôn hợp lệ = "
          f"{_p(pro['p_anytime'])}") if pro["draws"] else "chưa có kỳ quay nào"),
    ]
    tiles = "".join(
        '<article class="ui-kpi">'
        f'<span class="ui-kpi-label">{html.escape(label)}</span>'
        f'<b class="ui-kpi-value">{html.escape(value)}</b>'
        f'<span class="ui-kpi-sub">{html.escape(sub)}</span></article>'
        for label, value, sub in kpis
    )
    tiles += (
        '<article class="ui-kpi">'
        '<span class="ui-kpi-label">Mức tin của bộ lọc</span>'
        f'<b class="ui-kpi-value" data-level="{html.escape(vip["confidence"])}">'
        f'{html.escape(_LEVEL_WORD.get(vip["confidence"], vip["confidence"]))}</b>'
        f'<span class="ui-kpi-sub">{html.escape(_confidence_rule())}</span></article>'
    )
    return (
        f'<p class="ui-muted" data-evidence-split><b>{html.escape(headline)}.</b> {html.escape(text)}</p>'
        f'<div class="ui-kpi-grid" data-evidence-split>{tiles}</div>'
    )


def _check_line(bt: dict, pro: dict, what: str) -> str:
    """Một dòng số đo: tỉ lệ trúng đã kiểm trên mọi kỳ, và phần tiến cứu sau ngày chốt."""
    retro = (f"Đã kiểm {_count(bt['draws'])} kỳ: {what} trúng {_pct(bt['rate'])} · chọn bừa cùng kỳ "
             f"{_pct(bt['random_rate'])}")
    after = _date(pro["after"])
    later = (f"sau {after}: {_count(pro['draws'])} kỳ, trúng {_count(pro['hits'])} / chọn bừa "
             f"{_num(pro['expected'], 1)}") if pro["draws"] else f"sau {after}: chưa có kỳ nào"
    return f'<p class="app-vip-line" data-evidence-split>{html.escape(retro)} · {html.escape(later)}.</p>'


def _strip(items: list[tuple[str, str]], label: str, extra: str = "") -> str:
    lis = "".join(f"<li><b>{html.escape(big)}</b><small>{html.escape(small)}</small></li>"
                  for big, small in items)
    return (f'<ol class="app-lab-number-strip app-vip-strip{extra}" aria-label="{html.escape(label)}">'
            f"{lis}</ol>")


def picks_card(vip: dict, bench: dict | None = None, *, picks: bool = True) -> str:
    """Năm con cho kỳ tới, kết luận và một dòng số đo. ``picks=False``: số đo chậm hơn sổ, không in con."""
    v = verdict(vip, bench)
    head = ""
    if picks:
        head = _strip([(p["number"], f"P {_pct(p['probability'])}") for p in vip["picks"]],
                      "Các con xếp cao nhất để về từ hai nháy ở kỳ tới")
    return (
        head
        + f'<p class="app-vip-verdict" data-verdict="{v["state"]}">'
        f"<b>{html.escape(_HEADLINE[(v['state'], v['reason'])])}.</b></p>"
        + _check_line(vip["backtest"], vip["prospective"], f"top-{vip['config']['top_k']}")
    )


def pairs_card(section: dict | None, *, picks: bool = True) -> str:
    """Năm cặp xiên 2 cho kỳ tới, kết luận và một dòng số đo."""
    if section is None:
        return '<p class="ui-table-empty">Chưa đủ lịch sử để chọn cặp.</p>'
    window = section["config"]["window"]
    head = ""
    if picks:
        head = _strip([(" · ".join(p["pair"]), f"{p['together']}/{window} kỳ") for p in section["picks"]],
                      "Các cặp xiên 2 hay về cùng nhau nhất", " app-vip-strip-pairs")
    state = pair_verdict(section)
    return (
        head
        + f'<p class="app-vip-pair-verdict" data-verdict="{state}"><b>'
        f"{html.escape(_PAIR_HEADLINE[state])}.</b></p>"
        + _check_line(section["backtest"], section["prospective"], f"{section['config']['top_k']} cặp")
    )


def _pick_chip(pick: dict) -> str:
    hits = int(pick["hits"])
    tone = "ui-badge-ok" if hits >= 2 else "ui-badge-mute"
    return (f'<span class="ui-badge {tone}" data-hits="{hits}">'
            f"{html.escape(pick['number'])} · {hits} nháy</span>")


def _pair_chip(pick: dict) -> str:
    tone = "ui-badge-ok" if pick["hit"] else "ui-badge-mute"
    return (f'<span class="ui-badge {tone}" data-hit="{int(pick["hit"])}">'
            f"{html.escape(' · '.join(pick['pair']))}</span>")


def recent_card(vip: dict) -> str:
    recent = vip["recent"]
    if not recent:
        return '<p class="ui-table-empty">Chưa có kỳ nào được chấm.</p>'
    pairs = {r["date"]: r for r in (vip.get("pairs") or {}).get("recent", [])}
    k = vip["config"]["top_k"]
    rows = []
    for r in recent:
        p = pairs.get(r["date"])
        rows.append([_date(r["date"]), " ".join(_pick_chip(x) for x in r["picks"]), str(r["multi"]),
                     " ".join(_pair_chip(x) for x in p["picks"]) if p else "—",
                     str(p["hits"]) if p else "—"])
    hits = sum(r["multi"] for r in recent)
    # Kỳ vọng của chọn bừa phụ thuộc số con về ≥ 2 nháy của TỪNG kỳ đang hiện, không phải trung bình.
    expected = sum(r["expected"] for r in recent)
    line = (f"{len(recent)} kỳ: lô trúng {hits}/{len(recent) * k} lượt ≥ 2 nháy (chọn bừa kỳ vọng "
            f"{_num(expected, 2)})")
    shown = [pairs[r["date"]] for r in recent if r["date"] in pairs]
    if shown:
        line += (f" · cặp trúng {sum(p['hits'] for p in shown)}/{sum(len(p['picks']) for p in shown)} "
                 f"(chọn bừa kỳ vọng {_num(sum(p['expected'] for p in shown), 2)})")
    return (
        f'<p class="app-vip-line" data-evidence-split>{html.escape(line)}.</p>'
        + _table(["Kỳ", f"Top-{k} lô · số nháy về", "Lô ≥ 2 nháy", "Cặp xiên 2 (xanh = cùng về)",
                  "Cặp trúng"], rows, numeric="ui-r3 ui-r5")
    )


def _strategy_row(s: dict, candidate: str) -> list[str]:
    label = html.escape(strategy_label(s["name"]))
    if s["name"] == candidate:
        label += ' <span class="ui-badge ui-badge-warn">ứng viên</span>'
    dev, test = s["dev"], s["test"]
    return [label, _pct(dev["rate"]), _num(dev["z"], 2, sign=True), _num(s["dev_holm"], 3),
            _pct(test["rate"]), _num(test["z"], 2, sign=True)]


def benchmark_card(bench: dict | None) -> str:
    if bench is None:
        return '<p class="ui-table-empty">Chưa có số đo của lượt thử thứ hai.</p>'
    others = [s for s in bench["strategies"] if s["name"] != "random"]
    glance = sum(1 for s in others if s["test"]["z"] >= Z_GLANCE)
    by_chance = len(others) * 0.5 * math.erfc(Z_GLANCE / math.sqrt(2))
    rho = bench["rank_correlation"]
    rho_planted = bench["power_check"]["rank_correlation"]
    rows = [_strategy_row(s, bench["candidate"]) for s in bench["strategies"]]
    return (
        f'<p class="ui-muted">Giao thức cố định TRƯỚC khi chạy. Giai đoạn phát triển '
        f"{_date(bench['dev'][0])} → {_date(bench['dev'][1])} ({_count(bench['dev_draws'])} kỳ): mọi "
        "chiến lược được chấm, p hiệu chỉnh Holm, và chiến lược có z cao nhất là ứng viên DUY NHẤT. "
        f"Giai đoạn kiểm {_date(bench['test'][0])} → {_date(bench['test'][1])} "
        f"({_count(bench['test_draws'])} kỳ) chỉ quyết định ứng viên ấy: đạt khi p một phía &lt; "
        f"{_num(bench['alpha'], 2)}. Đây là phép kiểm MỘT LẦN trên lịch sử đến ngày "
        f"{_date(bench['registered_until'])}, không đo lại khi có kỳ mới: đo lại mỗi tháng trên 1 000 kỳ "
        "cuối trượt dần là nhìn lại gần như cùng một tập kiểm ở cùng α.</p>"
        + _table(["Chiến lược (xếp theo z phát triển)", "Phát triển: trúng", "z", "p Holm",
                  "Kiểm: trúng", "z"], rows, numeric="ui-r2 ui-r3 ui-r4 ui-r5 ui-r6")
        + f'<p class="ui-muted" data-evidence-split>Ở giai đoạn kiểm, {glance}/{len(others)} chiến lược '
        f"có z ≥ {_num(Z_GLANCE, 0)}; chỉ do may rủi đã kỳ vọng {_num(by_chance, 1)}. Chọn chiến lược "
        "đẹp nhất SAU khi thấy giai đoạn kiểm là rò rỉ, nên bảng in chúng để minh bạch chứ không "
        f"dùng để kết luận. Tương quan hạng Spearman giữa z hai giai đoạn: {_num(rho, 2, sign=True)} "
        f"(lịch sử có cài tín hiệu cho {_num(rho_planted, 2, sign=True)}) — chiến lược mạnh ở giai đoạn "
        "này không mạnh ở giai đoạn sau là dấu hiệu của dao động ngẫu nhiên.</p>"
    )


def any_hit_card(bench: dict | None) -> str:
    if bench is None:
        return '<p class="ui-table-empty">Chưa có số đo.</p>'
    cand, rnd = bench["any_hit"]["candidate"], bench["any_hit"]["random"]
    ks = sorted(cand["multi"], key=int)
    rows = [[f"Top-{k}", _pct(cand["multi"][k], 1), _pct(rnd["multi"][k], 1),
             _pct(cand["single"][k], 1), _pct(rnd["single"][k], 1)] for k in ks]
    n = bench["test_draws"]
    widest = max(ks, key=lambda k: abs(cand["multi"][k] - rnd["multi"][k]))
    gap = cand["multi"][widest] - rnd["multi"][widest]
    # Hai cột đo trên CÙNG các kỳ nên là cặp: sai số chuẩn lấy từ hiệu từng kỳ, do bước đo tính.
    se = bench["any_hit"]["paired_se"]["multi"][widest]
    return (
        f'<p class="ui-muted">Tỉ lệ kỳ có ÍT NHẤT một con trong top-k trúng, trên '
        f"{_count(n)} kỳ của giai đoạn kiểm: ứng viên «"
        f"{html.escape(strategy_label(bench['candidate']))}» so với chọn bừa. Tỉ lệ tăng theo số "
        "con chọn ở CẢ hai cột; chỉ phần chênh giữa hai cột cùng hàng mới là của chiến lược.</p>"
        + _table(["Số con chọn", "≥ 2 nháy · ứng viên", "≥ 2 nháy · chọn bừa",
                  "≥ 1 nháy · ứng viên", "≥ 1 nháy · chọn bừa"], rows,
                 numeric="ui-r2 ui-r3 ui-r4 ui-r5")
        + f'<p class="ui-muted" data-evidence-split>Chênh lệch lớn nhất ở cột ≥ 2 nháy là top-{widest}: '
        f"{_num(gap * 100, 1, sign=True)} điểm %; sai số chuẩn của hiệu ấy, tính từ hiệu từng kỳ "
        f"trên {_count(n)} kỳ, là {_num(se * 100, 1)} điểm % (|hiệu| / sai số = "
        f"{_num(abs(gap) / se if se else float('nan'), 1)}).</p>"
    )


def power_card(bench: dict | None) -> str:
    if bench is None:
        return '<p class="ui-table-empty">Chưa có số đo.</p>'
    pc = bench["power_check"]
    pw = bench["power"]
    ct = pc["candidate_test"]
    planted = ", ".join(pc["planted"])
    lo, hi = pw["ci95"]
    return (
        f'<p class="ui-muted" data-evidence-split>Một kết quả âm chỉ đáng đọc khi phép đo đủ nhạy để '
        "thấy một tín hiệu nếu nó có — và khi ấy nó chỉ cho biết không có lợi thế cỡ tín hiệu đã cài, "
        "không loại trừ một lợi thế nhỏ hơn. Lịch sử giả định cùng độ dài "
        f"({_count(bench['draws'])} kỳ, 27 lô đều trên 00–99), mỗi kỳ {planted} được cài thêm "
        f"≥ 2 nháy với xác suất {_pct(pc['plant_rate'], 0)}. Chạy lại đúng giao thức trên "
        f"{pw['runs']} lịch sử như thế (khác hạt giống): ứng viên qua giai đoạn kiểm ở <b>{pw['passes']}/"
        f"{pw['runs']}</b> lịch sử, tức độ nhạy {_pct(pw['rate'], 0)} (KTC 95% {_pct(lo, 0)} – "
        f"{_pct(hi, 0)}); ngưỡng đặt trước để coi là đủ nhạy là {_pct(pw['required'], 0)} → "
        f"<b>{'đủ nhạy' if pw['sensitive'] else 'chưa đủ nhạy'}</b>. Ví dụ lịch sử đầu (hạt giống "
        f"{pc['seed']}): giao thức chọn «"
        f"{html.escape(strategy_label(pc['candidate']))}» (z phát triển "
        f"{_num(pc['candidate_dev_z'], 2, sign=True)}); giai đoạn kiểm trúng {_pct(ct['rate'])} so với "
        f"nền {_pct(pc['base_test'])}, z = {_num(ct['z'], 2, sign=True)}, p = {_p(ct['p'])} → "
        f"<b>{'đạt' if pc['candidate_passes'] else 'không đạt'}</b>. Tương quan hạng giữa hai giai "
        f"đoạn {_num(pc['rank_correlation'], 2, sign=True)}.</p>"
    )


def method_card(vip: dict) -> str:
    cfg = vip["config"]
    items = [
        "Một kỳ có 27 lô (hai số cuối của 27 giải). Quay công bằng thì số nháy của một con định "
        "trước là X ~ Nhị thức(27; 1/100), nên chọn bừa một con trúng ≥ 2 nháy với xác suất "
        f"P(X ≥ 2) = {_pct(vip['base_theory'], 3)}.",
        "Bộ lọc VIP cộng bốn thành phần đã chuẩn hoá chéo 100 con trong cùng kỳ: tần suất & điểm "
        "rơi, dị thường Poisson (số kỳ ≥ 2 nháy so với kỳ vọng), đồng xuất hiện với các con đã về "
        f"kỳ trước, và cầu nhịp. Cửa sổ {cfg['window']} kỳ; đặc trưng của kỳ t chỉ đọc các kỳ trước t.",
        f"Trọng số chọn trên lưới đơn hình bằng backtest {cfg['weight_window']} kỳ NGAY TRƯỚC kỳ được "
        "chấm (walk-forward lồng nhau), nên tỉ lệ trúng báo ra không mang thiên lệch của chính phép "
        "chọn trọng số.",
        "Mốc so là chọn bừa k con trong CÙNG kỳ: với m con về ≥ 2 nháy ở kỳ ấy, số lượt trúng theo "
        "phân phối siêu bội. Cộng qua các kỳ ra z và p một phía.",
        "Khoảng tin cậy là Wilson 95% trên cỡ mẫu hiệu dụng: các con cùng kỳ chấm trên cùng 27 lô nên "
        "không độc lập, cỡ mẫu được chia cho hệ số thiết kế deff = phương sai số trúng từng kỳ / "
        "(k·p·(1 − p)).",
        "Bộ lọc được thiết kế sau khi đã xem lịch sử đến ngày "
        f"{_date(vip['prospective']['after'])}, nên kiểm chứng trên lịch sử ấy là MÔ TẢ hồi cứu, không "
        "phải bằng chứng chưa từng thấy. Mức tin chỉ tính trên các kỳ quay sau ngày ấy.",
        "Trang chấm lại bộ lọc mỗi ngày, nên p của một lần xem không đủ: xem lại đủ lâu với cùng ngưỡng "
        "thì sớm muộn sẽ vượt ngưỡng chỉ do may. p luôn hợp lệ lấy từ e-process: tích các hệ số cược "
        "1 + λ·(trúng − kỳ vọng chọn bừa) của từng kỳ tiến cứu, trung bình trên một lưới λ chốt sẵn; khi "
        "bộ lọc không có kỹ năng, xác suất tích ấy có lúc nào vượt 1/α không quá α (bất đẳng thức "
        "Ville), nên p = 1 / giá trị lớn nhất của tích đúng dù xem bao nhiêu lần.",
        f"Mức tin của bộ lọc — {_confidence_rule()}. Mức tin của từng con không vượt mức tin của "
        "bộ lọc.",
        "Số đo của bộ lọc tính lại mỗi ngày. Lượt thử thứ hai và phép kiểm độ nhạy là phép kiểm một "
        f"lần, đóng băng ở lịch sử đến ngày {_date(SECOND_ROUND_UNTIL)}; chỉ đo lại khi chính đoạn lịch "
        "sử ấy được sửa.",
    ]
    pairs = vip.get("pairs")
    if pairs is not None:
        pc = pairs["config"]
        items += [
            f"Cặp xiên 2: điểm của một cặp là số kỳ trong {pc['window']} kỳ gần nhất mà cả hai con cùng "
            "về; hoà điểm thì cặp cùng về gần đây hơn đứng trước. Lấy "
            f"{pc['top_k']} cặp, mỗi con nằm trong tối đa {pc['max_per_number']} cặp. Luật chốt trước khi "
            "kiểm chứng.",
            "Hai con định trước cùng về với xác suất 1 − 2·0,99²⁷ + 0,98²⁷ = "
            f"{_pct(pairs['base_theory'], 2)}. Mốc so là chọn bừa cùng số cặp trong CÙNG kỳ: kỳ có d con "
            "khác nhau về thì C(d, 2) trong 4 950 cặp cùng về. Sai số lấy từ hiệu từng kỳ vì các cặp chung "
            f"một con trúng hay trượt cùng nhau. Mức tin tính như bộ lọc, trên các kỳ sau ngày "
            f"{_date(pairs['prospective']['after'])}.",
        ]
    return '<ol class="app-vip-method">' + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ol>"


# --------------------------------------------------------------------------- trang


def behind_notice(vip: dict, last_date: str, behind_by: int) -> str:
    """Thay cho top-k khi số đo bộ lọc chậm hơn sổ kết quả: top-k ấy là cho một kỳ đã quay."""
    return (
        f'<p class="ui-table-empty" data-vip-behind="{behind_by}">Chưa có xếp hạng cho kỳ kế tiếp: '
        f"số đo của bộ lọc dừng ở ngày {_date(vip['source_date'])}, còn sổ kết quả đã có thêm "
        f"{behind_by} kỳ (đến ngày {_date(last_date)}). Các con và cặp của lần đo ấy là cho một kỳ đã "
        "quay nên không in; số đo kiểm chứng vẫn đúng cho đoạn lịch sử đã đo.</p>"
    )


def _page(body: str, meta: str) -> str:
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {stylesheet_link()}
  {lab_styles()}
  <title>Lô VIP nhiều nháy — Phân tích XSMB</title>
</head>
<body>
{app_shell_open(PAGE)}
<div class="app-lab app-lab-multi-hit" data-lab-layout="multi-hit">
{lab_hero(PAGE,
    "Lô VIP nhiều nháy",
    "Đề xuất cho kỳ tới: năm con dễ về từ hai nháy nhất theo mô hình, và năm cặp xiên 2 hay về "
    "cùng nhau nhất. Mỗi khối kèm tỉ lệ trúng đã kiểm trên mọi kỳ đã quay.",
    eyebrow="LÔ ≥ 2 NHÁY · XIÊN 2", core="ĐỐI CHỨNG",
    meta=meta,
    action=("#app-vip-picks", "Xem đề xuất"),
)}
{body}
{lab_footer()}</div>
{app_shell_close(PAGE)}
</body>
</html>
"""


def render_unavailable(last_date: str) -> str:
    """Trang khi không có số đo nào khớp lịch sử hiện tại: không in con số nào của lịch sử khác."""
    body = card(
        '<p class="ui-table-empty" data-vip-unavailable>Chưa có số đo của bộ lọc khớp với sổ kết quả '
        f"hiện tại (đến ngày {_date(last_date)}). Trang không in số đo của một lịch sử khác; số đo "
        "sẽ có lại ở lượt cập nhật kế tiếp.</p>",
        title="Kết luận từ phép đo", span=12, ident="app-lab-conclusion")
    return _page(f'<div class="ui-grid">{body}</div>', f"Sổ kết quả đến: {_date(last_date)}")


def render(vip: dict, bench: dict | None, *, last_date: str = "", behind_by: int = 0) -> str:
    fresh = behind_by <= 0
    notice = "" if fresh else behind_notice(vip, last_date, behind_by)
    top = [
        card(notice + picks_card(vip, bench, picks=fresh), title="Lô về ≥ 2 nháy · kỳ tới", span=6,
             ident="app-vip-picks"),
        card(pairs_card(vip.get("pairs"), picks=fresh), title="Xiên 2 · cặp cùng về kỳ tới", span=6,
             ident="app-vip-pairs"),
        card(recent_card(vip), title="10 kỳ gần nhất", span=12, lift=True, ident="app-vip-recent"),
    ]
    detail = [
        card(conclusion_card(vip, bench), title="Kết luận từ phép đo", span=12, ident="app-lab-conclusion"),
        card(benchmark_card(bench), title="Lượt thử thứ hai: dò rộng, chọn trước, kiểm một lần",
             span=12, ident="app-vip-benchmark"),
        card(any_hit_card(bench), title="Ít nhất một con về", span=12, ident="app-vip-any"),
        card(power_card(bench), title="Phép đo có đủ nhạy?", span=12, ident="app-vip-power"),
        card(method_card(vip), title="Cách đo", span=12, ident="app-vip-method"),
    ]
    # Giải thích dài thu vào một mục mở rộng; nút "Cách đọc báo cáo" của phần đầu trang trỏ vào nó.
    body = (
        f'<div class="ui-grid">{"".join(top)}</div>\n'
        '<details class="app-lab-guide app-vip-details" id="app-lab-guide"><summary>Chi tiết phép đo '
        "<span>KIỂM CHỨNG &amp; PHƯƠNG PHÁP</span></summary>"
        f'<div class="ui-grid">{"".join(detail)}</div></details>'
    )
    return _page(body, f"Dữ liệu đến: {_date(vip['source_date'])} · {_count(vip['draws'])} kỳ")


def build(data_dir: Path, docs_dir: Path) -> Path | None:
    got = load(data_dir)
    write_stylesheet(docs_dir)
    out = docs_dir / PAGE
    if got.vip is None:
        # Thiếu tệp hay tệp không khớp lịch sử: vẫn GHI ĐÈ trang, đừng để trang cũ với số đo cũ.
        print(f"data/{DATA_DIR}/vip.json {'chưa có' if got.vip_state == 'missing' else 'không khớp'} — "
              "dựng trang chưa có số đo.")
        write_page(out, render_unavailable(got.last_date))
    else:
        write_page(out, render(got.vip, got.bench, last_date=got.last_date, behind_by=got.behind_by))
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
