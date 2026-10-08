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
        out += f'<span class="vl-plus">+</span><span class="vl-ball vl-ball--bonus">{esc(_two(bonus))}</span>'
    return out


def result_markup(product: str, draw: dict) -> str:
    """Bộ số của một kỳ, đúng hình dạng từng sản phẩm."""
    if product in MAX:
        groups = [p for p in draw.get("prizes") or [] if isinstance(p, dict) and "numbers" in p]
        return '<div class="vl-3d">' + "".join(
            f'<div><small>{esc(g["label"])}</small><span>{" · ".join(esc(x) for x in g["numbers"])}</span></div>'
            for g in groups) + "</div>"
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
            f' — "—" là chưa có số liệu công bố</caption><thead><tr><th scope="col">Giải</th>'
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
    """Bộ số engine đề xuất cho kỳ kế tiếp, kèm trạng thái đăng ký và hệ số so với ngẫu nhiên."""
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
    for comp in forecast.get("components") or []:
        rows = []
        for t in (comp.get("top") or [])[:5]:
            lift = (t["p_model"] / t["p_fair"]) if t.get("p_model") and t.get("p_fair") else None
            rows.append(f'<li><span class="vl-ticket">{esc(_symbol(product, t["numbers"]))}</span>'
                        + (f'<small>×{lift:.4f} so với ngẫu nhiên</small>' if lift else "") + "</li>")
        name = "" if comp.get("name") in ("main", "digits") else f'<h4>{esc(comp["name"])}</h4>'
        parts.append(f'{name}<ol class="vl-tickets">{"".join(rows)}</ol>')
    return "".join(parts)


def comparisons_markup(product: str, comparisons: list[dict]) -> str:
    """Dự báo đã đăng ký đối chiếu với kết quả đúng kỳ, đúng ngày."""
    if not comparisons:
        return '<p class="vl-muted">Chưa có dự báo đăng ký trước kỳ nào để đối chiếu.</p>'
    rows = []
    for c in comparisons[:COMPARISONS_SHOWN]:
        # Engine ghi ``date_mismatch`` khi mã kỳ khớp mà ngày quay khác ngày đã đăng ký:
        # lỗi ghép dữ liệu, không phải "chờ kết quả".
        status = {"matched": "Đã chấm", "pending": "Chờ kết quả", "date_mismatch": "Lệch ngày"}.get(
            c.get("status"), "Chờ kết quả")
        tickets = c.get("tickets") or []
        if c.get("status") == "matched" and tickets:
            best = max((int(t.get("hits") or 0) for t in tickets), default=0)
            detail = " · ".join(
                esc(t.get("symbol") or _symbol(product, t.get("numbers") or []))
                + (f" + {esc(_two(t['special']))}" if t.get("special") is not None else "")
                + (f' <b>({int(t.get("hits") or 0)})</b>' if product not in MAX else
                   (f' <b>({", ".join(esc(x) for x in t.get("tiers") or [])})</b>' if t.get("tiers") else ""))
                for t in tickets[:5])
            result = c.get("result") or {}
            drawn = (" · ".join(esc(x) for x in result.get("numbers") or []) if product in MAX
                     else " ".join(esc(_two(x)) for x in result.get("numbers") or []))
            if product in MATRIX and result.get("bonus") is not None:
                drawn += f" + {esc(_two(result['bonus']))}"
            rows.append(f'<tr><th scope="row">#{esc(c.get("target_id"))}</th><td>{day_label(c.get("target_date"))}</td>'
                        f'<td>{status}</td><td>{detail}</td><td>{drawn}</td><td class="vl-num">{best}</td></tr>')
        else:
            rows.append(f'<tr><th scope="row">#{esc(c.get("target_id"))}</th><td>{day_label(c.get("target_date"))}</td>'
                        f'<td>{status}</td><td colspan="3" class="vl-muted">—</td></tr>')
    return ('<div class="vl-table-wrap"><table class="vl-table"><caption>Dự báo ghi TRƯỚC kỳ quay, chấm với kết quả '
            'đúng mã kỳ và ngày; số trong ngoặc là số trùng (Max: hạng giải trùng)</caption><thead><tr>'
            '<th scope="col">Kỳ</th><th scope="col">Ngày</th><th scope="col">Trạng thái</th>'
            '<th scope="col">Bộ số đã đăng ký</th><th scope="col">Kết quả</th><th scope="col">Trùng nhiều nhất</th>'
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


STYLE = """
.vl-hero{padding:24px 28px;border:1px solid var(--ui-border);border-radius:24px;background:linear-gradient(135deg,var(--ui-surface),var(--ui-brand-soft));box-shadow:var(--ui-sh-sm);margin-bottom:16px}.vl-kicker{font-size:12px;font-weight:800;letter-spacing:.1em;color:var(--ui-brand-ink)}.vl-hero h1{font-size:clamp(28px,5vw,46px);margin:6px 0 8px}.vl-hero p{max-width:760px;color:var(--ui-ink-soft);margin:0}.vl-chipline{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.vl-chip{display:inline-flex;padding:6px 10px;border:1px solid var(--ui-border);border-radius:999px;font-size:12px;background:var(--ui-surface)}
.vl-products{display:flex;gap:8px;overflow-x:auto;margin:0 0 16px;padding:2px 0 6px;scrollbar-width:thin}.vl-product{flex:0 0 auto;padding:9px 14px;border:1px solid var(--ui-border);border-radius:999px;background:var(--ui-surface);text-decoration:none;color:inherit;font-size:14px;font-weight:700;white-space:nowrap}.vl-product[aria-current="page"]{background:var(--ui-brand);color:var(--ui-on-brand);border-color:var(--ui-brand)}
.vl-section{margin:0 0 16px;padding:18px;border:1px solid var(--ui-border);border-radius:18px;background:var(--ui-surface);box-shadow:var(--ui-sh-sm)}.vl-section h2{margin:0 0 12px;font-size:20px}.vl-section h4{margin:12px 0 6px}.vl-cols{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.vl-toolbar{display:flex;gap:10px;align-items:end;margin:0 0 12px}.vl-toolbar label{display:grid;gap:4px;font-size:12px;font-weight:700}.vl-toolbar input{min-height:40px;border:1px solid var(--ui-border);border-radius:10px;background:var(--ui-surface);color:var(--ui-ink);padding:0 10px}
.vl-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.vl-draw{min-width:0;padding:16px;border:1px solid var(--ui-border);border-radius:16px;background:var(--ui-surface)}.vl-draw-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px}.vl-draw-head div{display:flex;gap:8px;align-items:baseline}.vl-draw-head small{font-size:10px;color:var(--ui-ink-soft)}.vl-draw-head time{font-size:12px;color:var(--ui-ink-soft)}
.vl-result{display:flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:0}.vl-ball{display:inline-grid;place-items:center;min-width:38px;height:38px;padding:0 6px;border-radius:999px;background:var(--ui-brand);color:var(--ui-on-brand);font:800 16px var(--ui-mono)}.vl-ball--bonus{background:var(--ui-special-ink)}.vl-plus{font-weight:900;color:var(--ui-ink-soft)}.vl-meta{flex-basis:100%;color:var(--ui-ink-soft);font-size:13px}.vl-jackpots{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;color:var(--ui-ink-soft);font-size:12px}.vl-jackpots b{color:var(--ui-ink)}
.vl-3d{width:100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.vl-3d div{min-width:0;padding:9px;border-radius:10px;background:var(--ui-surface-2)}.vl-3d small{display:block;color:var(--ui-ink-soft);font-size:10px}.vl-3d span{display:block;overflow-wrap:anywhere;font:700 14px/1.6 var(--ui-mono)}
.vl-table-wrap{overflow-x:auto;margin:8px 0}.vl-table{width:100%;border-collapse:collapse;font-size:14px}.vl-table caption{text-align:left;color:var(--ui-ink-soft);font-size:12px;padding:0 0 6px}.vl-table th,.vl-table td{padding:8px 10px;border-bottom:1px solid var(--ui-border);text-align:left;vertical-align:top}.vl-num{text-align:right!important;font-variant-numeric:tabular-nums;white-space:nowrap}
.vl-badge{display:inline-flex;padding:3px 9px;border-radius:999px;border:1px solid var(--ui-border);font-size:12px;font-weight:700}.vl-badge--ok{border-color:var(--ui-brand);color:var(--ui-brand-ink)}.vl-badge--warn{border-color:var(--ui-special-ink);color:var(--ui-special-ink)}.vl-muted{color:var(--ui-ink-soft)}.vl-tickets{margin:6px 0;padding-left:22px}.vl-tickets li{margin:4px 0}.vl-ticket{font:700 15px var(--ui-mono);margin-right:8px}.vl-tickets small{color:var(--ui-ink-soft)}.vl-forecast-head{margin:0 0 6px}
.vl-tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.vl-tile{display:block;min-width:0;padding:16px;border:1px solid var(--ui-border);border-radius:16px;background:var(--ui-surface);color:inherit;text-decoration:none}.vl-tile:hover{box-shadow:var(--ui-sh-sm)}.vl-tile h2{font-size:18px;margin:0}.vl-tile p{margin:4px 0 10px;color:var(--ui-ink-soft);font-size:13px}.vl-empty{padding:24px;border:1px dashed var(--ui-border);border-radius:16px;text-align:center}
@media(max-width:860px){.vl-grid,.vl-cols,.vl-tiles{grid-template-columns:1fr}.vl-hero{padding:18px}.vl-toolbar{display:grid}.vl-ball{min-width:34px;height:34px;font-size:15px}}
"""

SEARCH_SCRIPT = (
    "<script>(()=>{const q=document.getElementById('vl-search');if(!q)return;q.addEventListener('input',()=>{"
    "const s=q.value.trim().toLowerCase();document.querySelectorAll('#vl-grid .vl-draw').forEach(x=>"
    "x.hidden=!!s&&!((x.dataset.date+' '+x.dataset.id).toLowerCase().includes(s)));});})();</script>"
)


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


def page(product: str, data: dict | None, analysis: dict | None) -> str:
    name, file, desc = PRODUCTS[product]
    latest = (data or {}).get("latest")
    draws = (data or {}).get("draws") or []
    chips = [f'<span class="vl-chip">{esc(desc)}</span>']
    if data and data.get("schedule"):
        chips.append(f'<span class="vl-chip">Lịch quay: {esc(data["schedule"])}</span>')
    if latest:
        chips.append(f'<span class="vl-chip">Kỳ mới nhất #{esc(latest["draw_id"])} · {day_label(latest.get("draw_date"))}</span>')
    hero = (f'<section class="vl-hero"><span class="vl-kicker">VIETLOTT · KẾT QUẢ</span><h1>{esc(name)}</h1>'
            '<p>Kết quả đã xác thực theo đúng mã kỳ, bảng giải của từng kỳ, dự báo ghi trước kỳ quay và đối chiếu '
            f'với kết quả thật.</p><div class="vl-chipline">{"".join(chips)}</div></section>')
    if not latest:
        body = '<div class="vl-empty">Chưa có kết quả đã xác thực cho sản phẩm này.</div>'
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
    return (_head(f"{name} · Vietlott") + app_shell_open(file, wide=True) + hero + nav_products(product) + body
            + app_shell_close(file) + SEARCH_SCRIPT + "</body></html>")


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
        tiles.append(f'<a class="vl-tile" href="{file}"><h2>{esc(name)}</h2><p>{head} · {esc(data.get("schedule") or desc)}'
                     f'{signal}</p>{result}{follow}</a>')
    stats = dashboard.get("stats") or {}
    chips = (f'<span class="vl-chip">{esc(stats.get("results", 0))}/{esc(stats.get("products", len(PRODUCTS)))} sản phẩm có kết quả</span>'
             f'<span class="vl-chip">{esc(stats.get("registered_next", 0))} dự báo đã đăng ký cho kỳ tới</span>'
             f'<span class="vl-chip">{esc(stats.get("compared_draws", 0))} kỳ đã đối chiếu</span>')
    hero = ('<section class="vl-hero"><span class="vl-kicker">VIETLOTT · TỔNG QUAN</span><h1>Kết quả Vietlott</h1>'
            '<p>Bảy sản phẩm đang phát hành: Mega 6/45, Power 6/55, Lotto 5/35, Max 3D / Max 3D+, Max 3D Pro, Keno '
            'và Bingo18. Kết quả đã xác thực, bảng giải, dự báo ghi trước kỳ và đối chiếu. '
            f'{esc(randomness_summary(analysis, {c: v[0] for c, v in PRODUCTS.items()}))}</p>'
            f'<div class="vl-chipline">{chips}</div></section>')
    return (_head("Vietlott · Kết quả") + app_shell_open("vietlott.html", wide=True) + hero + nav_products()
            + f'<div class="vl-tiles">{"".join(tiles)}</div>' + overview_sections(dashboard)
            + app_shell_close("vietlott.html") + "</body></html>")


def build(root: Path = ROOT, *, dashboard: dict | None = None, cache_states: Path | None = None) -> list[Path]:
    """Dựng đủ 8 trang qua ``write_page``; ``dashboard`` truyền sẵn để kiểm thử."""
    if dashboard is None:
        dashboard = load(cache_states)
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
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
