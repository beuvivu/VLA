"""Trang Vietlott của VLA, dựng từ engine ``vietlott/`` (chép từ VLM ngày 07-10-2026).

Trước đây VLA tự cào một trang tin và lưu vào SQLite riêng: chỉ có số quay và
một con số jackpot bóc từ chữ, không Keno/Bingo18, không bảng giải, không số
người trúng. Nay mọi dữ liệu đi qua engine:

* ``vlm.web.dashboard.build_dashboard`` — kết quả đã xác thực của 7 sản phẩm
  đang phát hành, bảng giải đúng mã kỳ, cơ cấu giải, dự báo ĐĂNG KÝ TRƯỚC kỳ
  quay và đối chiếu với kết quả thật. Hàm ấy không gọi mạng, không sửa sổ.
* ``vietlott_engine.forecast`` — kết luận của bộ tự học (e-value hợp lệ ở mọi
  thời điểm) và sổ chấm dự báo.

Luật riêng của trang (CLAUDE.md): không vẽ danh tính nguồn dữ liệu ra trình
duyệt. Dữ liệu engine mang trường ``source``, ``source_url``, ``official_url``
và cảnh báo nhắc tên nguồn; trang KHÔNG in trường nào trong số đó — mọi chữ ra
trang đi qua các hàm dựng dưới đây, đọc đúng trường đã liệt kê. Giá trị khuyết
(jackpot, số người trúng chưa công bố) in "—", không lấy của kỳ trước.
"""

from __future__ import annotations

import contextlib
import html
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from css_links import stylesheet_link
from page_output import write_page
from ui_theme import app_shell_close, app_shell_open
from web_security import security_meta_tags

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "vietlott"

#: Tên trang của từng sản phẩm — giữ nguyên địa chỉ đã xuất bản.
PRODUCTS: dict[str, tuple[str, str, str]] = {
    "lotto535": ("Lotto 5/35", "vietlott-lotto-535.html", "5 số + số đặc biệt"),
    "mega645": ("Mega 6/45", "vietlott-mega-645.html", "6 số"),
    "power655": ("Power 6/55", "vietlott-power-655.html", "6 số + số đặc biệt"),
    "max3d": ("Max 3D / Max 3D+", "vietlott-max-3d.html", "20 bộ ba số"),
    "max3dpro": ("Max 3D Pro", "vietlott-max-3d-pro.html", "20 bộ ba số"),
    "keno": ("Keno", "vietlott-keno.html", "20 số / kỳ"),
    "bingo18": ("Bingo18", "vietlott-bingo18.html", "3 số / kỳ"),
}
MATRIX = ("mega645", "power655", "lotto535")
MAX = ("max3d", "max3dpro")
#: Số đối chiếu hiện trên trang sản phẩm (engine giữ 30).
COMPARISONS_SHOWN = 10


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def vn_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def money(value: int | None) -> str:
    return "—" if value is None else vn_int(int(value)) + " ₫"


def day_label(value: str | None) -> str:
    """``2026-10-04T00:00:00+07:00`` → ``04/10/2026``; khuyết thì "—"."""
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y")
    except ValueError:
        return esc(str(value)[:10])


def stamp_label(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value)).strftime("%H:%M %d/%m/%Y")
    except ValueError:
        return esc(value)


def _two(value: object) -> str:
    return f"{int(value):02d}"


# ---------------------------------------------------------------- nạp engine


@contextlib.contextmanager
def _engine_importable():
    """Cho phép ``import vietlott_engine`` / ``vlm`` và chạy trong thư mục engine.

    Engine đọc một số đường dẫn tương đối (``data/``, ``data/seed``) như khi
    chạy trong kho riêng của nó, nên phải đổi thư mục làm việc trong lúc gọi.
    """
    src = str(ENGINE / "src")
    added = src not in sys.path
    if added:
        sys.path.insert(0, src)
    try:
        with contextlib.chdir(ENGINE):
            yield
    finally:
        if added:
            sys.path.remove(src)


def _states_dir(work: Path, cache_states: Path | None) -> Path:
    """Thư mục sổ + trạng thái bộ dự báo để đọc (KHÔNG ghi gì vào sổ thật).

    Hai sổ dự báo đã commit được chép sang thư mục tạm; trạng thái lấy từ cache
    của workflow engine nếu có (đã đồng bộ tới kỳ mới nhất), không thì để
    trống — phần phân tích tự học lại từ dữ liệu đi kèm.
    """
    forecast = ENGINE / "data" / "forecast"
    work.mkdir(parents=True, exist_ok=True)
    for name in ("ledger.jsonl", "ml-ledger.jsonl"):
        if (forecast / name).exists():
            shutil.copyfile(forecast / name, work / name)
    if cache_states and cache_states.is_dir():
        for path in cache_states.glob("*.json"):
            shutil.copyfile(path, work / path.name)
        if (cache_states / "ml").is_dir():
            shutil.copytree(cache_states / "ml", work / "ml", dirs_exist_ok=True)
    return work


def _analysis(directory: Path, products: tuple[str, ...] = tuple(PRODUCTS)) -> dict[str, dict]:
    """Kết luận của bộ tự học + sổ chấm, theo sản phẩm.

    Dùng trạng thái có sẵn trong ``directory``; sản phẩm nào chưa có thì học
    lại từ dữ liệu đi kèm (vài giây) — kết luận ghi rõ học tới kỳ nào.
    """
    from vietlott_engine.core.products import ProductCode
    from vietlott_engine.forecast.data import load_series
    from vietlott_engine.forecast.engine import Forecaster, scoreboard, state_path

    boards = {row["product"]: row for row in scoreboard(directory)}
    out: dict[str, dict] = {}
    for code in products:
        product = ProductCode(code)
        path = state_path(directory, product)
        if path.exists():
            forecaster = Forecaster.load(path)
        else:
            forecaster = Forecaster(code)
            forecaster.update(load_series(code, seed_dir=Path("data/seed")))
        rep = forecaster.forecast().model_dump(mode="json")
        out[code] = {
            "draws": rep["draws"], "last_id": rep["last_id"], "last_date": rep["last_date"],
            "verdict": rep["verdict"], "evidence": rep["evidence"], "board": boards.get(code),
            "max_rtp": _max_rtp(rep["components"]),
        }
    return out


def _max_rtp(components: list[dict]) -> float | None:
    """RTP cao nhất theo mô hình trong mọi cửa của một sản phẩm (None khi không có cửa)."""
    rtps = [b["rtp_model"] for c in components for kind in ("digit", "set") if c.get(kind)
            for b in (c[kind].get("bets") or []) + (c[kind].get("keno") or [])]
    return max(rtps) if rtps else None


def randomness_summary(analysis: dict, names: dict[str, str]) -> str:
    """Kết luận về độ ngẫu nhiên in TỪ SỐ ĐO của engine, không viết cứng.

    Max 3D / Max 3D Pro từng mâu thuẫn với câu viết cứng "kỳ quay đã kiểm là ngẫu
    nhiên": cả hai lệch thật ở chữ số hàng đơn vị (số 6 ≈ 11% thay vì 10%, ổn định
    qua thời gian, lặp lại trên hai sản phẩm độc lập), e-value vượt ngưỡng 20.
    """
    if not analysis:
        return "Chưa có phân tích độ ngẫu nhiên của kỳ quay."
    found = [code for code in names if ((analysis.get(code) or {}).get("evidence") or {}).get("found")]
    if not found:
        return ("Phép kiểm e-value của engine chưa thấy sản phẩm nào lệch khỏi máy quay công bằng; "
                "dự báo không làm tăng xác suất trúng.")
    # Chỉ nói về những sản phẩm mà mô hình TÍNH được RTP. Mega/Power/Lotto không có RTP
    # trong phân tích, mà jackpot dồn hay chia giải có thể đẩy RTP của chúng vượt 1.
    priced = [c for c in names if (analysis.get(c) or {}).get("max_rtp") is not None]
    money = ""
    if priced and max(analysis[c]["max_rtp"] for c in priced) < 1:
        best = f"{max(analysis[c]['max_rtp'] for c in priced):.2f}".replace(".", ",")
        money = (f" Dù vậy mọi cửa của {_join([names[c] for c in priced])} mà mô hình tính được vẫn có kỳ vọng âm: "
                 f"RTP cao nhất là {best} (dưới 1).")
    return (f"Phép kiểm e-value của engine thấy độ lệch nhỏ có ý nghĩa thống kê ở {_join([names[c] for c in found])}; "
            f"các sản phẩm còn lại chưa lệch khỏi máy quay công bằng.{money}")


def _join(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " và " + labels[-1]


def load(cache_states: Path | None = None, products: tuple[str, ...] = tuple(PRODUCTS)) -> dict[str, Any]:
    """Bảng điều khiển của engine + phân tích, đọc từ dữ liệu ``vietlott/`` đã commit."""
    # Phân giải TRƯỚC khi chuyển vào thư mục engine: workflow truyền đường dẫn tính từ
    # gốc kho (``vietlott/data/forecast``), sau chdir nó thành ``vietlott/vietlott/...``.
    cache_states = Path(cache_states).resolve() if cache_states else None
    with tempfile.TemporaryDirectory() as tmp, _engine_importable():
        from vlm.web.dashboard import build_dashboard

        directory = _states_dir(Path(tmp) / "forecast", cache_states)
        data = Path("data")
        dashboard = build_dashboard(data, data / "seed", directory, data / "results" / "results.jsonl")
        dashboard["analysis"] = _analysis(directory, products)
    return dashboard


# ---------------------------------------------------------------- khối hiển thị


def balls(values: list, bonus: object = None, *, product: str = "") -> str:
    fmt = (lambda x: str(int(x))) if product == "bingo18" else _two
    out = "".join(f'<span class="vl-ball">{esc(fmt(x))}</span>' for x in values)
    if bonus is not None:
        out += (f'<span class="vl-plus" aria-hidden="true">+</span><span class="vl-ball vl-ball--bonus" '
                f'aria-label="Số đặc biệt {esc(_two(bonus))}">{esc(_two(bonus))}</span>')
    matrix = " vl-number-sequence--matrix" if product in MATRIX else ""
    return f'<span class="vl-number-sequence{matrix}">' + out + "</span>"


def _max_result_markup(product: str, draw: dict, *, matched_symbol: str | None = None) -> str:
    """Giữ từng giải trên một hàng; tô Đặc biệt theo nhóm, không theo tập bộ ba."""
    groups = [p for p in draw.get("prizes") or [] if isinstance(p, dict) and "numbers" in p]
    if not groups:
        numbers = draw.get("numbers") or []
        return _comparison_balls(product, numbers, matched=[x == matched_symbol for x in numbers],
                                 sequence_class="vl-number-sequence")
    rows = []
    for group in groups:
        label = str(group.get("label") or "")
        special = product == "max3dpro" and label.strip().casefold() == "đặc biệt"
        numbers = group["numbers"]
        sequence = _comparison_balls(product, numbers, matched=[x == matched_symbol for x in numbers],
                                     special=special, sequence_class="vl-number-sequence", label=label + ": ")
        modifier = " vl-prize-row--special" if special else ""
        rows.append(f'<div class="vl-prize-row{modifier}"><span class="vl-prize-label">{esc(label)}</span>{sequence}</div>')
    return '<div class="vl-3d">' + "".join(rows) + "</div>"


def result_markup(product: str, draw: dict) -> str:
    """Bộ số của một kỳ, đúng hình dạng từng sản phẩm."""
    if product in MAX:
        return _max_result_markup(product, draw)
    out = balls(draw.get("numbers") or [], draw.get("bonus"), product=product)
    facts = draw.get("facts") or {}
    if product == "bingo18" and facts:
        out += f'<span class="vl-meta">Tổng <b>{esc(facts.get("sum"))}</b> · {esc(facts.get("size"))}</span>'
    if product == "keno" and facts:
        out += (f'<span class="vl-meta">Lớn {esc(facts.get("large"))} · Nhỏ {esc(facts.get("small"))}'
                f' · Chẵn {esc(facts.get("even"))} · Lẻ {esc(facts.get("odd"))}</span>')
    return out


def prize_table(product: str, draw: dict) -> str:
    """Bảng giải của ĐÚNG kỳ ấy (Mega/Power/Lotto): giá trị và số người trúng."""
    rows = [p for p in draw.get("prizes") or [] if isinstance(p, dict) and "code" in p]
    if product not in MATRIX or not rows:
        return ""
    body = "".join(
        f'<tr><th scope="row">{esc(p["label"])}</th><td>{esc(p.get("condition"))}</td>'
        f'<td class="vl-num">{money(p.get("value_vnd"))}</td>'
        f'<td class="vl-num">{"—" if p.get("winners") is None else vn_int(int(p["winners"]))}</td></tr>'
        for p in rows)
    return (f'<div class="vl-table-wrap"><table class="vl-table"><caption>Bảng giải kỳ #{esc(draw["draw_id"])}'
            f' — "—" là chưa có dữ liệu cho kỳ này</caption><thead><tr><th scope="col">Giải</th>'
            '<th scope="col">Điều kiện</th><th scope="col">Giá trị</th><th scope="col">Số người trúng</th>'
            f'</tr></thead><tbody>{body}</tbody></table></div>')


def catalogue_table(rows: list[dict]) -> str:
    if not rows:
        return ""
    body = []
    for r in rows:
        value = r.get("value_text") or money(r.get("value_vnd"))
        product = f'{esc(r["product"])} · ' if r.get("product") else ""
        note = f'<br><small>{esc(r["note"])}</small>' if r.get("note") else ""
        body.append(f'<tr><th scope="row">{product}{esc(r.get("label"))}</th><td>{esc(r.get("condition"))}{note}</td>'
                    f'<td class="vl-num">{esc(value)}</td></tr>')
    return ('<div class="vl-table-wrap"><table class="vl-table"><caption>Cơ cấu giải thưởng</caption><thead><tr>'
            '<th scope="col">Giải</th><th scope="col">Điều kiện</th><th scope="col">Giá trị</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def _symbol(product: str, numbers: list) -> str:
    if product in MAX:
        return "".join(str(int(x)) for x in numbers)
    if product == "bingo18":
        return "-".join(str(int(x)) for x in numbers)
    return " ".join(_two(x) for x in numbers)


def forecast_markup(product: str, forecast: dict | None) -> str:
    """Bộ số engine đề xuất cho kỳ kế tiếp, kèm trạng thái đăng ký."""
    if not forecast:
        return '<p class="vl-muted">Chưa có dự báo hợp lệ cho kỳ kế tiếp.</p>'
    if forecast.get("registered"):
        state = (f'<span class="vl-badge vl-badge--ok">Đã đăng ký trước kỳ</span> ghi lúc '
                 f'{stamp_label(forecast.get("made_at"))}')
    else:
        state = '<span class="vl-badge">Tham khảo</span> ' + esc(forecast.get("note") or "")
    target = f'Kỳ #{esc(forecast.get("target_id"))}'
    if forecast.get("target_date"):
        target += f" · {day_label(forecast['target_date'])}"
    parts = [f'<p class="vl-forecast-head"><strong>{target}</strong> · {state}</p>']
    components = []
    for comp in forecast.get("components") or []:
        rows = []
        for t in (comp.get("top") or [])[:5]:
            numbers = t["numbers"]
            if product in MAX:
                symbol = _symbol(product, numbers)
                sequence = f'<span class="vl-number-sequence"><span class="vl-ball vl-ball--symbol">{esc(symbol)}</span></span>'
            elif comp.get("name") == "special":
                sequence = '<span class="vl-number-sequence">' + "".join(
                    f'<span class="vl-ball vl-ball--bonus">{esc(_two(number))}</span>' for number in numbers) + '</span>'
            else:
                sequence = balls(numbers, product=product)
            rows.append(f'<li><div class="vl-ticket-row"><span class="vl-ticket" aria-label="{esc(_symbol(product, numbers))}">{sequence}</span>'
                        "</div></li>")
        key = comp.get("name") or ""
        label = {"main": "Bộ số chính", "special": "Số đặc biệt", "digits": "Bộ ba số", "dice": "Bộ ba số"}.get(key, key)
        components.append(f'<div class="vl-forecast-component" data-vl-component="{esc(key)}">'
                          f'<h4 class="vl-forecast-label">{esc(label)}</h4><ol class="vl-tickets">{"".join(rows)}</ol></div>')
    parts.append('<div class="vl-forecast-layout"><div class="vl-forecast-components">' + "".join(components) + '</div></div>')
    return "".join(parts)


def _ticket_score(product: str, ticket: dict) -> tuple[int, int] | None:
    """Số trùng và mẫu số của từng vé, giữ cách chấm riêng của engine."""
    if product in MAX:
        return None
    key = "position_hits" if product == "bingo18" else "hits"
    numbers = ticket.get("numbers") or []
    if ticket.get(key) is None or not numbers:
        return None
    return int(ticket[key]), len(numbers)


def _hit_percent(hits: int, denominator: int) -> str:
    return f"{100 * hits / denominator:.1f}%".replace(".", ",")


def _comparison_balls(product: str, values: list, *, matched: list[bool] | None = None,
                      bonus: object = None, bonus_hit: bool = False, bonus_main: object = None,
                      label: str = "", special: bool = False, sequence_class: str = "vl-comparison-balls") -> str:
    """Đánh dấu theo từng vị trí; bộ ba Max giữ nguyên chuỗi và số 0 đầu."""
    fmt = str if product in MAX else (lambda x: str(int(x))) if product == "bingo18" else _two
    marks = matched or []
    spans = []
    for index, number in enumerate(values):
        is_match = index < len(marks) and marks[index]
        is_bonus = bonus_main is not None and number == bonus_main
        modifier = " vl-ball--symbol" if product in MAX else ""
        if special or is_bonus:
            modifier += " vl-ball--bonus"
        modifier += " vl-ball--match" if is_match else " vl-ball--bonus-hit" if is_bonus else ""
        description = " · trùng số chính" if is_match and product in MATRIX else " · trùng" if is_match else " · trùng số phụ" if is_bonus else ""
        spans.append(f'<span class="vl-ball{modifier}" aria-label="{esc(fmt(number) + description)}">{esc(fmt(number))}</span>')
    text = " · ".join(fmt(x) for x in values) if product in MAX else " ".join(fmt(x) for x in values)
    if bonus is not None:
        text += " + " + _two(bonus)
        modifier = " vl-ball--bonus-hit" if bonus_hit else ""
        spans.append(f'<span class="vl-plus" aria-hidden="true">+</span><span class="vl-ball vl-ball--bonus{modifier}" '
                     f'aria-label="Số đặc biệt {esc(_two(bonus))}{" · trùng" if bonus_hit else ""}">{esc(_two(bonus))}</span>')
    tag = "span" if sequence_class == "vl-number-sequence" else "div"
    return f'<{tag} class="{sequence_class}" aria-label="{esc(label + text)}">{"".join(spans)}</{tag}>'


def _stored_tickets(product: str, comparison: dict) -> list[dict]:
    """Giữ bộ số đã ghi khi kỳ đang chờ; không dựng dự báo mới để lấp chỗ trống."""
    if comparison.get("tickets"):
        return comparison["tickets"]
    components = {c.get("name"): c for c in comparison.get("components") or []}
    name = "digits" if product in MAX else "dice" if product == "bingo18" else "main"
    special = ((components.get("special") or {}).get("top") or [{}])[0].get("numbers") or []
    return [{"numbers": row.get("numbers") or [], **({"special": special[0]} if special else {})}
            for row in (components.get(name) or {}).get("top") or []]


def _ticket_prize(product: str, ticket: dict) -> str:
    """Chỉ hiện phân hạng có sẵn trong kết quả engine, không suy từ phần trăm."""
    if product in MAX:
        return " · ".join(str(t) for t in ticket["tiers"]) if ticket.get("tiers") else "Không trùng hạng giải" if "tiers" in ticket else "Chưa có phân hạng"
    if product not in MATRIX:
        return "Chưa phân hạng cược"
    labels = {"jackpot1": "Jackpot 1" if product == "power655" else "Độc đắc" if product == "lotto535" else "Jackpot", "jackpot2": "Jackpot 2",
              "first": "Giải Nhất", "second": "Giải Nhì", "third": "Giải Ba", "fourth": "Giải Tư",
              "fifth": "Giải Năm", "consolation": "Khuyến khích"}
    if "tier" not in ticket:
        return "Chưa có phân hạng"
    return labels.get(ticket["tier"], "Chưa có phân hạng") if ticket["tier"] else "Không trúng giải"


def _comparison_summary(product: str, comparisons: list[dict]) -> str:
    scored = [t for c in comparisons if c.get("status") == "matched" for t in c.get("tickets") or []]
    pairs = [pair for t in scored if (pair := _ticket_score(product, t)) is not None]
    hits = sum(pair[0] for pair in pairs)
    denominator = sum(pair[1] for pair in pairs)
    percent = _hit_percent(hits, denominator) if denominator else "—"
    detail = f"{hits} / {denominator} {'vị trí' if product == 'bingo18' else 'số chính'} của các vé" if denominator else "Chưa có vé đủ dữ liệu để tính"
    if product in MAX:
        percent, detail = "Không áp dụng", "Bộ ba được đối chiếu nguyên vẹn"
    cards = [("Số vé đã chấm", str(len(scored)), "Trong các kỳ hiển thị bên dưới"),
             ("Kỳ chờ kết quả", str(sum(c.get("status") == "pending" for c in comparisons)), "Chưa được đưa vào tỷ lệ"),
             ("Kỳ lệch ngày", str(sum(c.get("status") == "date_mismatch" for c in comparisons)), "Cần kiểm tra lại kỳ đối chiếu"),
             ("Tỷ lệ trùng theo từng vé", percent, detail)]
    return '<div class="vl-comparison-summary">' + "".join(
        f'<div class="vl-comparison-stat"><span>{esc(label)}</span><strong>{esc(value)}</strong><small>{esc(note)}</small></div>'
        for label, value, note in cards) + "</div>"


def comparisons_markup(product: str, comparisons: list[dict]) -> str:
    """Dự báo đã đăng ký đối chiếu từng vé với kết quả đúng kỳ, đúng ngày."""
    if not comparisons:
        return '<p class="vl-muted">Chưa có dự báo đăng ký trước kỳ nào để đối chiếu.</p>'
    shown = comparisons[:COMPARISONS_SHOWN]
    rows = []
    for c in shown:
        scored = c.get("status") == "matched"
        # Mã kỳ đúng mà ngày khác là lỗi ghép, không phải đang chờ kết quả.
        status = {"matched": "Đã chấm", "pending": "Chờ kết quả", "date_mismatch": "Lệch ngày"}.get(c.get("status"), "Chờ kết quả")
        state_class = " vl-badge--ok" if scored else " vl-badge--warn" if c.get("status") == "date_mismatch" else ""
        tickets = _stored_tickets(product, c)
        result = c.get("result") or {}
        total = max(1, len(tickets))
        rowspan = f' rowspan="{total}"' if total > 1 else ""
        metadata = (f'<th scope="row"{rowspan} class="vl-comparison-meta">#{esc(c.get("target_id"))}</th>'
                    f'<td class="vl-comparison-meta vl-comparison-date"{rowspan}>{day_label(c.get("target_date"))}</td>'
                    f'<td class="vl-comparison-meta"{rowspan}><span class="vl-badge{state_class}">{status}</span></td>')
        for index, ticket in enumerate(tickets or [None], 1):
            if ticket is None:
                rows.append(f'<tr data-vl-comparison-status="{esc(c.get("status") or "pending")}" '
                            f'data-vl-comparison-target="{esc(c.get("target_id"))}" data-vl-comparison-ticket="{index}">{metadata}'
                            '<td class="vl-comparison-prediction">—</td><td class="vl-comparison-result">'
                            '<span class="vl-muted">Chưa có vé để đối chiếu</span></td><td class="vl-comparison-score-cell">'
                            '<span class="vl-muted">Chưa chấm · —</span></td></tr>')
                continue
            numbers = ticket.get("numbers") or []
            drawn = result.get("numbers") or []
            matches = ticket.get("matched_numbers") or []
            bonus_hit = bool(ticket.get("bonus_hit")) if scored else False
            if product in MAX:
                symbol = ticket.get("symbol") or _symbol(product, numbers)
                pred_values = [symbol]
                pred_marks = [bool(ticket.get("hits")) and scored]
                drawn_marks = [scored and value == symbol for value in drawn]
            elif product == "bingo18":
                pred_values = numbers
                pred_marks = ticket.get("position_matches") or [] if scored else []
                drawn_marks = pred_marks
            else:
                pred_values = numbers
                pred_marks = [scored and value in matches for value in numbers]
                drawn_marks = [scored and value in matches for value in drawn]
            special = ticket.get("special") if product == "lotto535" else None
            bonus_main = result.get("bonus") if scored and product == "power655" and bonus_hit else None
            prediction = ('<div class="vl-comparison-ticket"' + (f' data-vl-ticket="{index}"' if scored else "") + '>'
                          f'<small>Vé {index}</small>' + _comparison_balls(product, pred_values, matched=pred_marks,
                          bonus=special, bonus_hit=bonus_hit, bonus_main=bonus_main, label="Bộ số đã đăng ký: ") + '</div>')
            actual = '<span class="vl-muted">Chưa đối chiếu kết quả</span>'
            score = '<span class="vl-muted">Chưa chấm · —</span>'
            if scored:
                sequence = (_max_result_markup(product, result, matched_symbol=symbol) if product in MAX else
                            _comparison_balls(product, drawn, matched=drawn_marks, bonus=result.get("bonus") if product in MATRIX else None,
                                              bonus_hit=bonus_hit, label="Kết quả: "))
                actual = f'<div class="vl-comparison-actual"><small>Đối chiếu vé {index}</small>{sequence}</div>'
                pair = _ticket_score(product, ticket)
                score = f"{pair[0]} / {pair[1]} · {_hit_percent(*pair)}" if pair else f"Xuất hiện {int(ticket['hits'])} lần" if product in MAX and ticket.get("hits") is not None else "Chưa đủ dữ liệu chấm"
                secondary = ""
                if product == "bingo18" and ticket.get("multiset_hits") is not None:
                    secondary = f'<small class="vl-comparison-secondary">Bộ có lặp: {int(ticket["multiset_hits"])} / {len(numbers)}</small>'
                elif product in ("power655", "lotto535"):
                    secondary = f'<small class="vl-comparison-secondary">Số {"phụ" if product == "power655" else "đặc biệt"}: {"trùng" if bonus_hit else "không trùng"}</small>'
                score = (f'<div class="vl-comparison-score"><small>Vé {index}{" · theo vị trí" if product == "bingo18" else ""}</small>'
                         f'<strong>{esc(score)}</strong>{secondary}<span class="vl-comparison-tier">{esc(_ticket_prize(product, ticket))}</span></div>')
            rows.append(f'<tr data-vl-comparison-status="{esc(c.get("status") or "pending")}" '
                        f'data-vl-comparison-target="{esc(c.get("target_id"))}" data-vl-comparison-ticket="{index}">'
                        f'{metadata if index == 1 else ""}<td class="vl-comparison-prediction">{prediction}</td>'
                        f'<td class="vl-comparison-result">{actual}</td><td class="vl-comparison-score-cell">{score}</td></tr>')
    unit = "Tỷ lệ đếm vị trí trùng của từng vé Bingo18; bộ có lặp được đếm riêng." if product == "bingo18" else "Max 3D đối chiếu cả bộ ba; số lần xuất hiện và hạng giải do engine chấm." if product in MAX else "Tỷ lệ = tổng số chính trùng / tổng số chính đã chọn trên từng vé; số phụ được xét riêng."
    note = (unit + " Đây là mức khớp của các vé đã chấm, không phải xác suất trúng giải.") if product not in MAX else unit
    legend = ('<div class="vl-comparison-legend"><span><span class="vl-ball vl-ball--match" aria-hidden="true">✓</span> Trùng</span>'
              '<span><span class="vl-ball" aria-hidden="true">•</span> Không trùng</span>'
              + ('<span><span class="vl-ball vl-ball--bonus" aria-hidden="true">+</span> Số đặc biệt / phụ</span>' if product in ("power655", "lotto535") else "") + '</div>')
    return (_comparison_summary(product, shown) + f'<p class="vl-comparison-note">{esc(note)}</p>' + legend
            + '<div class="vl-table-wrap"><table class="vl-table vl-comparison-table"><caption>Dự báo ghi TRƯỚC kỳ quay, '
            f'chấm với kết quả đúng mã kỳ và ngày · {len(shown)} kỳ hiển thị</caption><thead><tr>'
            '<th scope="col">Kỳ</th><th scope="col">Ngày</th><th scope="col">Trạng thái</th>'
            '<th scope="col">Bộ số đã đăng ký</th><th scope="col">Kết quả theo từng vé</th><th scope="col">Mức trùng và hạng giải</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def analysis_markup(analysis: dict | None) -> str:
    if not analysis:
        return ""
    ev = analysis.get("evidence") or {}
    badge = ('<span class="vl-badge vl-badge--warn">Có tín hiệu thống kê</span>' if ev.get("found")
             else '<span class="vl-badge">Chưa hơn ngẫu nhiên</span>')
    board = analysis.get("board") or {}
    if board.get("scored"):
        ledger = (f'{vn_int(board["recorded"])} dự báo ghi trước kỳ, {vn_int(board["scored"])} đã chấm: trùng '
                  f'{board["hits"]:.0f} so với kỳ vọng ngẫu nhiên {board["expected"]:.1f}.')
    elif board:
        ledger = f'{vn_int(board.get("recorded", 0))} dự báo đã ghi, chưa kỳ nào được chấm.'
    else:
        ledger = "Chưa có dự báo nào được ghi trước kỳ quay."
    return (f'<p>{badge} Học từ {vn_int(analysis["draws"])} kỳ, dữ liệu tới #{esc(analysis["last_id"])} '
            f'ngày {day_label(analysis["last_date"])}.</p><p>{esc(analysis.get("verdict"))}</p>'
            f'<p class="vl-muted">{esc(ev.get("text"))}</p><p class="vl-muted">Sổ dự báo: {esc(ledger)}</p>')


def draw_card(product: str, draw: dict) -> str:
    jackpots = "".join(
        f'<span>{esc(p["label"])}: <b>{money(p.get("value_vnd"))}</b></span>'
        for p in draw.get("prizes") or []
        if isinstance(p, dict) and p.get("pool") and p.get("value_vnd") is not None)
    return (f'<article class="vl-draw" data-date="{esc(str(draw.get("draw_date", ""))[:10])}" data-id="{esc(draw["draw_id"])}">'
            f'<div class="vl-draw-head"><div><small>KỲ QUAY</small><strong>#{esc(draw["draw_id"])}</strong></div>'
            f'<time>{day_label(draw.get("draw_date"))}</time></div>'
            f'<div class="vl-result">{result_markup(product, draw)}</div>'
            f'<div class="vl-jackpots">{jackpots}</div></article>')


STYLE = (Path(__file__).with_name("templates") / "vietlott_main.css").read_text(encoding="utf-8")


SEARCH_SCRIPT = (
    "<script>(()=>{const q=document.getElementById('vl-search');if(!q)return;q.addEventListener('input',()=>{"
    "const s=q.value.trim().toLowerCase();document.querySelectorAll('#vl-grid .vl-draw').forEach(x=>"
    "x.hidden=!!s&&!((x.dataset.date+' '+x.dataset.id).toLowerCase().includes(s)));});})();</script>"
)
COMPARISON_SCRIPT = '<script src="assets/vietlott-comparison.js" defer></script>'


def _head(title: str) -> str:
    return (f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1">{security_meta_tags()}{stylesheet_link()}'
            f'<title>{esc(title)}</title><style>{STYLE}</style></head><body>')


def nav_products(active: str = "") -> str:
    links = "".join(
        f'<a class="vl-product" href="{file}"' + (' aria-current="page"' if key == active else "") + f">{esc(name)}</a>"
        for key, (name, file, _desc) in PRODUCTS.items())
    return '<nav class="vl-products" aria-label="Sản phẩm Vietlott"><a class="vl-product" href="vietlott.html"' + (
        ' aria-current="page"' if not active else "") + f">Tổng quan</a>{links}</nav>"


def _by_code(dashboard: dict) -> dict[str, dict]:
    return {p["product"]: p for p in dashboard.get("products") or []}


def jackpot_card(product: str, data: dict | None) -> str:
    """Jackpot đúng kỳ mới nhất; pool chưa công bố vẫn hiện dấu gạch."""
    latest = (data or {}).get("latest") or {}
    pools = {p.get("code"): p for p in latest.get("prizes") or [] if p.get("pool")}
    labels = [("jackpot1", "Jackpot 1"), ("jackpot2", "Jackpot 2")] if product == "power655" else [("jackpot1", "Jackpot")]
    values = "".join(
        f'<div class="vl-jackpot-pool"><span>{label}</span><strong class="vl-jackpot-value">'
        f'{money((pools.get(code) or {}).get("value_vnd"))}</strong></div>'
        for code, label in labels)
    stamp = (f'Kỳ #{esc(latest["draw_id"])} · {day_label(latest.get("draw_date"))}'
             if latest else "Chưa có kết quả đã xác thực")
    name, file, _ = PRODUCTS[product]
    return (f'<article class="vl-jackpot-card" data-vl-jackpot="{product}" aria-label="Jackpot của kỳ mới nhất">'
            f'<span class="vl-kicker">JACKPOT · KỲ MỚI NHẤT</span><h2>{esc(name)}</h2>'
            f'<p class="vl-jackpot-stamp">{stamp}</p>{values}'
            '<p class="vl-jackpot-note">Dấu — cho biết chưa có dữ liệu giá trị của kỳ này.</p>'
            f'<a class="vl-button vl-button--secondary" href="{file}#vl-latest">Xem bảng giải <span aria-hidden="true">↗</span></a></article>')


def pick_board(product: str) -> str:
    """Bộ chọn cục bộ; không ghi sổ dự báo và không tạo giao dịch."""
    if product not in ("mega645", "power655"):
        return ""
    maximum = 45 if product == "mega645" else 55
    buttons = "".join(
        f'<button class="vl-pick" type="button" data-vl-number="{number}" aria-pressed="false" '
        f'aria-label="Số {number:02d}" tabindex="{0 if number == 1 else -1}">{number:02d}</button>'
        for number in range(1, maximum + 1))
    slots = "".join('<span class="vl-pick-slot" data-vl-slot>—</span>' for _ in range(6))
    name = PRODUCTS[product][0]
    return (f'<section class="vl-section vl-picks" id="vl-picks" data-vl-picks="{product}" '
            f'data-vl-name="{esc(name)}" aria-labelledby="vl-picks-title">'
            '<div class="vl-section-heading"><div><span class="vl-kicker">BỘ SỐ CỦA BẠN</span>'
            '<h2 id="vl-picks-title">Chọn sáu con số</h2></div><span class="vl-chip" data-vl-count>0 / 6</span></div>'
            '<p class="vl-muted">Tạo bộ số nháp để lưu riêng. Chọn nhanh tạo số ngẫu nhiên.</p>'
            '<div class="vl-picks-layout"><div><div class="vl-pick-grid" role="group" '
            f'aria-label="Chọn 6 số từ 1 đến {maximum}" aria-describedby="vl-pick-help">{buttons}</div>'
            '<p class="vl-pick-help" id="vl-pick-help">Dùng phím mũi tên để di chuyển; Enter hoặc Space để chọn.</p>'
            '<div class="vl-pick-actions"><button type="button" class="vl-button vl-button--secondary" data-vl-random>'
            'Chọn nhanh</button><button type="button" class="vl-button vl-button--ghost" data-vl-clear>Xóa bộ số</button></div>'
            '<p class="vl-pick-status" data-vl-status role="status" aria-live="polite">Chọn 6 số khác nhau để xem trước.</p></div>'
            '<aside class="vl-pick-ticket" aria-label="Bộ số nháp"><span class="vl-kicker">XEM TRƯỚC</span>'
            f'<h3>{esc(name)}</h3><div class="vl-pick-slots" aria-hidden="true">{slots}</div>'
            '<p class="vl-muted">Bộ số chỉ được lưu trên thiết bị của bạn.</p>'
            '<button type="button" class="vl-button" data-vl-review disabled>Xem bộ số</button></aside></div>'
            '<noscript><p class="vl-muted">Bật JavaScript để chọn và tải bộ số nháp.</p></noscript>'
            '<dialog class="vl-pick-dialog" aria-labelledby="vl-draft-title"><span class="vl-kicker">BỘ SỐ NHÁP</span>'
            f'<h2 id="vl-draft-title">{esc(name)}</h2><p class="vl-pick-preview" data-vl-preview></p>'
            '<p class="vl-muted">Đây là bộ số nháp, chưa phải vé đã mua. Bộ số không được gửi đến hệ thống đặt vé.</p>'
            '<div class="vl-pick-actions"><button type="button" class="vl-button" data-vl-download>Tải bộ số</button>'
            '<button type="button" class="vl-button vl-button--secondary" data-vl-close>Chỉnh sửa</button></div></dialog></section>')


def comparison_widget(product: str) -> str:
    """Đối chiếu bộ số người dùng nhập, độc lập với sổ dự báo đã đăng ký."""
    if product not in MATRIX:
        return ""
    count, maximum = (5, 35) if product == "lotto535" else (6, 45 if product == "mega645" else 55)
    name = PRODUCTS[product][0]
    sample = "01 02 03 04 05" + (" 06" if count == 6 else "")
    fields = (f'<label class="vl-comparison-field">Bộ số dự đoán ({count} số)<input type="text" '
              f'data-vl-prediction required autocomplete="off" placeholder="{sample}" aria-describedby="vl-manual-help"></label>'
              f'<label class="vl-comparison-field">Kết quả thực tế ({count} số)<input type="text" '
              f'data-vl-actual autocomplete="off" placeholder="{sample}" aria-describedby="vl-manual-help"></label>')
    if product == "lotto535":
        fields += ('<label class="vl-comparison-field">Số đặc biệt dự đoán (1–12)<input type="number" '
                   'data-vl-predicted-bonus min="1" max="12" step="1" placeholder="Tùy chọn"></label>')
    if product in ("power655", "lotto535"):
        bonus_max = 55 if product == "power655" else 12
        label = "Số phụ thực tế" if product == "power655" else "Số đặc biệt thực tế"
        fields += (f'<label class="vl-comparison-field">{label} (1–{bonus_max})<input type="number" '
                   f'data-vl-actual-bonus min="1" max="{bonus_max}" step="1" placeholder="Tùy chọn"></label>')
    return (f'<section class="vl-section vl-comparison-widget" id="vl-manual-compare" aria-labelledby="vl-manual-title">'
            '<div class="vl-section-heading"><div><span class="vl-kicker">CÔNG CỤ ĐỐI CHIẾU</span>'
            f'<h2 id="vl-manual-title">Kiểm tra bộ số {esc(name)}</h2></div></div>'
            f'<form data-vl-comparison-widget="{product}" novalidate><p class="vl-muted" id="vl-manual-help">'
            f'Nhập {count} số chính khác nhau từ 1 đến {maximum}, cách nhau bằng dấu cách hoặc dấu phẩy. '
            'Bộ số được tính trên thiết bị của bạn; không ghi vào sổ dự báo.</p>'
            f'<div class="vl-comparison-fields">{fields}</div><div class="vl-comparison-actions">'
            '<button class="vl-button" type="submit" data-vl-comparison-submit>Đối chiếu bộ số</button></div>'
            '<p class="vl-pick-status" data-vl-comparison-status role="status" aria-live="polite">'
            'Nhập cả hai bộ số để xem số trùng, tỷ lệ và hạng giải.</p>'
            '<div class="vl-comparison-output" data-vl-comparison-output aria-live="polite"></div>'
            '<noscript><p class="vl-muted">Bật JavaScript để đối chiếu bộ số vừa nhập.</p></noscript></form></section>')


def page(product: str, data: dict | None, analysis: dict | None) -> str:
    name, file, desc = PRODUCTS[product]
    latest = (data or {}).get("latest")
    draws = (data or {}).get("draws") or []
    chips = [f'<span class="vl-chip">{esc(desc)}</span>']
    if data and data.get("schedule"):
        chips.append(f'<span class="vl-chip">Lịch quay: {esc(data["schedule"])}</span>')
    if latest:
        chips.append(f'<span class="vl-chip">Kỳ mới nhất #{esc(latest["draw_id"])} · {day_label(latest.get("draw_date"))}</span>')
    feature = jackpot_card(product, data) if product in ("mega645", "power655") else (
        '<article class="vl-hero-summary"><span class="vl-kicker">KỲ QUAY MỚI NHẤT</span>'
        + (f'<strong>#{esc(latest["draw_id"])}</strong><p>{day_label(latest.get("draw_date"))}</p>'
           f'<div class="vl-result">{result_markup(product, latest)}</div>' if latest else '<p>Chưa có kết quả đã xác thực.</p>')
        + '</article>')
    hero = (f'<section class="vl-hero"><div class="vl-hero-copy"><span class="vl-kicker">VIETLOTT · KẾT QUẢ</span><h1>{esc(name)}</h1>'
            '<p>Kết quả đã xác thực theo đúng mã kỳ, bảng giải của từng kỳ, dự báo ghi trước kỳ quay và đối chiếu '
            f'với kết quả thật.</p><div class="vl-chipline">{"".join(chips)}</div>'
            '<div class="vl-hero-actions"><a class="vl-button" href="#vl-latest">Xem kết quả <span aria-hidden="true">↗</span></a>'
            '<a class="vl-button vl-button--secondary" href="vietlott.html#vl-frequency">Khám phá thống kê</a></div></div>'
            f'{feature}</section>')
    if not latest:
        body = '<div class="vl-empty" id="vl-latest">Chưa có kết quả đã xác thực cho sản phẩm này.</div>'
    else:
        body = (f'<section class="vl-section" aria-labelledby="vl-latest"><h2 id="vl-latest">Kỳ mới nhất</h2>'
                f'{draw_card(product, latest)}{prize_table(product, latest)}</section>'
                '<div class="vl-cols">'
                f'<section class="vl-section" aria-labelledby="vl-next"><h2 id="vl-next">Dự báo kỳ kế tiếp</h2>'
                f'{forecast_markup(product, data.get("next_forecast"))}</section>'
                f'<section class="vl-section" aria-labelledby="vl-analysis"><h2 id="vl-analysis">Mô hình tự học có '
                f'vượt ngẫu nhiên?</h2>{analysis_markup(analysis)}</section></div>'
                f'<section class="vl-section" aria-labelledby="vl-compare"><h2 id="vl-compare">Đối chiếu dự báo</h2>'
                f'{comparisons_markup(product, data.get("comparisons") or [])}</section>'
                f'<section class="vl-section" aria-labelledby="vl-history"><h2 id="vl-history">{len(draws)} kỳ gần nhất</h2>'
                '<div class="vl-toolbar"><label>Tìm ngày / kỳ quay<input id="vl-search" type="search" '
                'placeholder="VD: 2026-10-05 hoặc 1571"></label></div>'
                f'<div class="vl-grid" id="vl-grid">{"".join(draw_card(product, d) for d in draws)}</div></section>'
                f'<section class="vl-section" aria-labelledby="vl-catalogue"><h2 id="vl-catalogue">Cơ cấu giải</h2>'
                f'{catalogue_table(data.get("prize_catalogue") or [])}</section>')
    script = '<script src="assets/vietlott-picks.js" defer></script>' if product in ("mega645", "power655") else ""
    script += COMPARISON_SCRIPT
    return (_head(f"{name} · Vietlott") + app_shell_open(file, wide=True) + hero + nav_products(product)
            + pick_board(product) + body + comparison_widget(product) + app_shell_close(file) + SEARCH_SCRIPT + script + "</body></html>")


def overview(dashboard: dict) -> str:
    from vietlott_navigation_content import overview_sections
    by_code = _by_code(dashboard)
    analysis = dashboard.get("analysis") or {}
    tiles = []
    for code, (name, file, desc) in PRODUCTS.items():
        data = by_code.get(code) or {}
        latest = data.get("latest")
        head = (f'Kỳ #{esc(latest["draw_id"])} · {day_label(latest.get("draw_date"))}' if latest else "Chưa có kết quả")
        result = f'<div class="vl-result">{result_markup(code, latest)}</div>' if latest else ""
        nxt = data.get("next_forecast")
        follow = ""
        if nxt:
            follow = (f'<p>Dự báo kỳ #{esc(nxt.get("target_id"))}: '
                      + ("đã đăng ký trước kỳ" if nxt.get("registered") else "tham khảo") + "</p>")
        ev = (analysis.get(code) or {}).get("evidence") or {}
        signal = " · có tín hiệu thống kê" if ev.get("found") else ""
        tiles.append(f'<a class="vl-tile" href="{file}"><div class="vl-tile-heading"><h2>{esc(name)}</h2>'
                     f'<span class="vl-tile-arrow" aria-hidden="true">↗</span></div>'
                     f'<p>{head} · {esc(data.get("schedule") or desc)}{signal}</p>{result}{follow}</a>')
    stats = dashboard.get("stats") or {}
    chips = (f'<span class="vl-chip">{esc(stats.get("results", 0))}/{esc(stats.get("products", len(PRODUCTS)))} sản phẩm có kết quả</span>'
             f'<span class="vl-chip">{esc(stats.get("registered_next", 0))} dự báo đã đăng ký cho kỳ tới</span>'
             f'<span class="vl-chip">{esc(stats.get("compared_draws", 0))} kỳ đã đối chiếu</span>')
    featured = next((c for c in ("power655", "mega645") if (by_code.get(c) or {}).get("latest")), "power655")
    hero = ('<section class="vl-hero"><div class="vl-hero-copy"><span class="vl-kicker">VIETLOTT · TỔNG QUAN</span>'
            '<h1>Kết quả <span>Vietlott</span></h1>'
            '<p>Khám phá bảy sản phẩm Vietlott. Theo dõi kết quả đã xác thực, bảng giải và dự báo ghi trước kỳ quay.</p>'
            f'<div class="vl-chipline">{chips}</div><details class="vl-hero-evidence">'
            '<summary>Kết luận kiểm định các kỳ quay</summary>'
            f'<p>{esc(randomness_summary(analysis, {c: v[0] for c, v in PRODUCTS.items()}))}</p></details>'
            '<div class="vl-hero-actions">'
            '<a class="vl-button" href="#vl-games">Khám phá sản phẩm <span aria-hidden="true">↗</span></a>'
            '<a class="vl-button vl-button--secondary" href="vietlott-mega-645.html#vl-picks">Chọn bộ số</a></div></div>'
            f'{jackpot_card(featured, by_code.get(featured))}</section>')
    return (_head("Vietlott · Kết quả") + app_shell_open("vietlott.html", wide=True) + hero + nav_products()
            + '<section class="vl-game-hub" id="vl-games" aria-labelledby="vl-games-title">'
            + '<div class="vl-section-heading"><div><span class="vl-kicker">KHÁM PHÁ</span>'
            + '<h2 id="vl-games-title">Một điểm đến. Bảy sản phẩm.</h2></div><span class="vl-muted">Kết quả theo đúng kỳ quay</span></div>'
            + f'<div class="vl-tiles">{"".join(tiles)}</div></section>' + overview_sections(dashboard)
            + app_shell_close("vietlott.html") + COMPARISON_SCRIPT + "</body></html>")


def build(root: Path = ROOT, *, dashboard: dict | None = None, cache_states: Path | None = None) -> list[Path]:
    """Dựng đủ 8 trang qua ``write_page``; ``dashboard`` truyền sẵn để kiểm thử."""
    if dashboard is None:
        dashboard = load(cache_states)
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    assets = docs / "assets"
    assets.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "src/assets/vietlott-picks.js", assets / "vietlott-picks.js")
    shutil.copyfile(ROOT / "src/assets/vietlott-comparison.js", assets / "vietlott-comparison.js")
    by_code = _by_code(dashboard)
    analysis = dashboard.get("analysis") or {}
    out = [docs / "vietlott.html"]
    write_page(out[0], overview(dashboard))
    for code, (_name, file, _desc) in PRODUCTS.items():
        target = docs / file
        write_page(target, page(code, by_code.get(code), analysis.get(code)))
        out.append(target)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache-states", type=Path, default=None,
                        help="Thư mục trạng thái bộ dự báo khôi phục từ cache của workflow engine.")
    parser.add_argument("--dump-json", type=Path, default=None, help="Ghi thêm bảng điều khiển ra tệp (gỡ lỗi).")
    args = parser.parse_args(argv)
    dashboard = load(args.cache_states)
    if args.dump_json:
        args.dump_json.write_text(json.dumps(dashboard, ensure_ascii=False), encoding="utf-8")
    for path in build(ROOT, dashboard=dashboard):
        print("đã ghi", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
