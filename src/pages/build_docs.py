from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from core.safe_io import read_csv_or_empty, read_json_or_empty
from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.path_models import index_to_label
from web.ui_locale import mode_label, path_kind_label
from web.ui_theme import refresh_live_page
from core.xsmb_domain import baseline_rate
from web.web_security import security_meta_tags
from web.page_output import write_page


@dataclass
class PickRow:
    number: int
    prob: float
    support_paths_count: int


@dataclass
class Cell:
    num: int
    hit: bool
    hitde: bool
    tooltip: str


@dataclass
class UiRow:
    path_id: str
    lag: int
    i: int
    j: int
    i_label: str
    j_label: str
    p_mean: float
    streak: str
    cells: list[Cell]
    p_next: float | None = None


def _latest_anchor_date(path_ui_dir: Path, mode: str) -> str:
    # files: ui_{mode}_{kind}_{YYYY-MM-DD}_{Nd}d.csv
    pat = re.compile(
        rf"ui_{re.escape(mode)}_(?:active|stable)_(\d{{4}}-\d{{2}}-\d{{2}})_(\d+)d\.csv$"
    )
    dates: list[str] = []
    for p in path_ui_dir.glob(f"ui_{mode}_*_*.csv"):
        m = pat.search(p.name)
        if m:
            dates.append(m.group(1))
    if not dates:
        raise FileNotFoundError(
            f"Không tìm thấy tệp CSV giao diện trong {path_ui_dir} cho loại={mode}"
        )
    return sorted(dates)[-1]


def _load_ui_csv(
    path_ui_dir: Path, mode: str, kind: str, anchor_date: str, display_days: int
) -> pd.DataFrame:
    p = path_ui_dir / f"ui_{mode}_{kind}_{anchor_date}_{display_days}d.csv"
    if not p.exists():
        raise FileNotFoundError(f"Thiếu tệp giao diện: {p}")
    return pd.read_csv(p)


def _load_picks_csv(path_ui_dir: Path, mode: str, kind: str, anchor_date: str) -> pd.DataFrame:
    p = path_ui_dir / f"predict_next_{mode}_{kind}_{anchor_date}.csv"
    if not p.exists():
        raise FileNotFoundError(f"Thiếu tệp gợi ý: {p}")
    return pd.read_csv(p)


def _empty_reason(path_ui_dir: Path, *, mode: str, kind: str, rows: int) -> dict[str, Any]:
    """Vì sao trang này trống, và người đọc nên đi đâu tiếp.

    Trả về rỗng khi trang có dữ liệu, nên template chỉ cần kiểm tra một biến.
    """
    if rows:
        return {}

    sibling = "stable" if kind == "active" else "active"
    sibling_rows = len(read_csv_or_empty(path_ui_dir / f"paths_{mode}_{sibling}.csv"))

    threshold = 3
    payload = read_json_or_empty(path_ui_dir / f"path_manifest_{mode}.json")
    key = "min_current_streak" if kind == "active" else "min_max_streak"
    if isinstance(payload, dict) and key in payload:
        try:
            threshold = int(payload[key])
        except (TypeError, ValueError):
            pass

    rate = baseline_rate(mode)
    return {
        "threshold": threshold,
        "baseline_pct": round(rate * 100, 2),
        "chance_pct": rate**threshold * 100,
        "sibling_rows": sibling_rows,
        "sibling_link": f"soi-path-{mode}-{sibling}.html",
        "sibling_label": path_kind_label(sibling),
        "is_de": mode == "de",
    }


def _dec(value: float, digits: int = 2) -> str:
    """Số thập phân kiểu Việt Nam: dấu phẩy thập phân."""
    return f"{value:.{digits}f}".replace(".", ",")


def _pct(value: float, digits: int = 2) -> str:
    return _dec(value * 100, digits)


def _int(value: int) -> str:
    """Số nguyên kiểu Việt Nam: dấu chấm phân nghìn."""
    return f"{int(value):,}".replace(",", ".")


#: Phạm vi vị trí của ``path_models.get_scope_indices``, in đúng cấu hình đã sinh dự báo.
_SCOPE_TEXT = {
    "all": "mọi cặp vị trí",
    "near_special": "các cặp vị trí trong giải Đặc Biệt, giải nhất và giải nhì",
    "special_only": "các cặp vị trí trong giải Đặc Biệt",
}


def _bridge_experience(
    path_ui_dir: Path, *, mode: str, kind: str, anchor_date: str
) -> dict[str, Any]:
    """Kinh nghiệm học từ MỌI đường cầu (``path_prob.BridgeEvidence``) và câu kết luận.

    Câu kết luận suy TỪ số đo của ngày neo, không viết cứng: nếu một ngày các
    cầu thật sự khác nhau, trang sẽ nói thế và in phần chênh được giữ lại.
    Thiếu tệp (lượt dựng cũ) thì trả rỗng và trang bỏ khối này. Tệp là của MỘT
    ngày neo: khác ngày neo của trang (chạy lại ``--bien-ngay`` cho ngày cũ, hay
    lượt dựng hỏng giữa chừng) thì cũng bỏ khối, không ghép kinh nghiệm của
    ngày này với bảng cầu của ngày khác.
    """
    payload = read_json_or_empty(path_ui_dir / f"bridge_evidence_{mode}.json")
    if not isinstance(payload, dict) or "variance_ratio" not in payload:
        return {}
    if payload.get("anchor_date") != anchor_date:
        return {}
    base = float(payload["base_rate"])
    ratio = _dec(float(payload["variance_ratio"]))
    rules = _int(payload["rules"])
    if payload.get("rules_fully_pooled"):
        verdict = (
            f"Tỉ lệ trúng của {rules} đường cầu tản ra {ratio} lần mức mà dao động ngẫu "
            "nhiên tự sinh ra, không có phần vượt nào: không cầu nào tốt hơn cầu nào một "
            f"cách thật sự, nên mọi cầu co về tỉ lệ chung {_pct(base)}%. Tỉ lệ lịch sử cao "
            "của một cầu được chọn ra từ hàng nghìn cầu là may, không phải dấu hiệu."
        )
    else:
        keep = 1.0 - float(payload["rule_shrinkage"])
        verdict = (
            f"Tỉ lệ trúng của {rules} đường cầu tản ra {ratio} lần mức dao động ngẫu nhiên. "
            f"Phần vượt cho mỗi cầu giữ {_pct(keep, 1)}% chênh lệch riêng so với tỉ lệ chung "
            f"{_pct(base)}%; phần còn lại co về tỉ lệ chung."
        )

    hits = payload.get("streak_hits") or []
    tot = payload.get("streak_trials") or []
    post = payload.get("streak_posterior") or []
    buckets = len(tot)
    rows = [
        {
            "label": f"{s}+" if s == buckets - 1 else str(s),
            "trials": _int(n),
            "raw": _pct(int(h) / int(n)),
            "post": _pct(float(q)),
        }
        for s, (h, n, q) in enumerate(zip(hits, tot, post, strict=True))
        if n
    ]
    shown = [float(q) for q, n in zip(post, tot, strict=True) if n]
    spread = max(abs(q - base) for q in shown) if shown else 0.0
    if payload.get("streaks_fully_pooled"):
        streak_verdict = (
            "Chênh lệch giữa các độ dài chuỗi không vượt dao động ngẫu nhiên: cầu đang chạy "
            "dài hơn không trúng tiếp nhiều hơn, nên mọi độ dài co về tỉ lệ chung."
        )
    else:
        streak_verdict = (
            "Sau khi co theo Bayes thực nghiệm, độ dài chuỗi xê dịch xác suất kỳ tới nhiều nhất "
            f"{_pct(spread)} điểm phần trăm."
        )
    lag_max = int(payload.get("lag_max", 0))
    scope = _SCOPE_TEXT.get(str(payload.get("scope", "")), "các cặp vị trí đã quét")
    return {
        "anchor_date": payload.get("anchor_date"),
        "scope_text": f"{scope} × độ trễ 1–{lag_max}" if lag_max else scope,
        "rules": rules,
        "trials": _int(payload["trials"]),
        "base_pct": _pct(base),
        "verdict": verdict,
        "streak_rows": rows,
        "streak_verdict": streak_verdict,
        "uses_streak": kind == "active",
    }


def _render_page(
    env: Environment,
    *,
    out_path: Path,
    title: str,
    mode: str,
    kind: str,
    other_link: str | None,
    other_kind_label: str,
    other_mode_label: str,
    index_link: str,
    anchor_date: str,
    display_days: int,
    ui_df: pd.DataFrame,
    picks_df: pd.DataFrame,
    empty_reason: dict[str, Any] | None = None,
    experience: dict[str, Any] | None = None,
) -> None:
    tpl = env.get_template("path_ui_page.html.j2")

    # Identify day columns: *_num, *_hit, *_is_de
    # run_path_ui exports daily cols as YYYY-MM-DD_num, etc.
    day_nums = [c for c in ui_df.columns if c.endswith("_num")]
    days = [c[:-4] for c in day_nums]  # remove _num

    # Prepare picks
    picks: list[PickRow] = []
    for _, r in picks_df.head(20).iterrows():
        picks.append(
            PickRow(
                number=int(r["number"]),
                prob=float(r["prob"]),
                support_paths_count=int(r["support_paths_count"]),
            )
        )

    # Rows
    rows: list[UiRow] = []
    for _, r in ui_df.iterrows():
        lag = int(r.get("lag", 0))
        i = int(r.get("i", 0))
        j = int(r.get("j", 0))

        i_label = str(r.get("i_label", "")) or index_to_label(i)
        j_label = str(r.get("j_label", "")) or index_to_label(j)

        p_mean = float(r.get("p_mean", 0.0))
        # ``p_next`` do ``path_prob.rule_next_probability`` tính ở bước dựng dữ
        # liệu: cùng thiên lệch và chặn biên với bước gợi ý.
        p_next = float(r["p_next"]) if pd.notna(r.get("p_next")) else None
        # show streaks
        if kind == "active":
            streak = (
                f"hiện tại={int(r.get('current_streak', 0))} / "
                f"dài nhất={int(r.get('max_streak', 0))}"
            )
        else:
            streak = (
                f"dài nhất={int(r.get('max_streak', 0))} / "
                f"hiện tại={int(r.get('current_streak', 0))}"
            )

        path_id = str(r.get("path_id", "")) or f"L{lag}-[{i},{j}]"

        cells: list[Cell] = []
        for d in days:
            num = int(r[f"{d}_num"])
            hit = bool(int(r[f"{d}_hit"])) if f"{d}_hit" in ui_df.columns else False
            is_de = bool(int(r[f"{d}_is_de"])) if f"{d}_is_de" in ui_df.columns else False
            tooltip = (
                f"{d} · trễ={lag} · vị trí A={i} ({i_label}) · "
                f"vị trí B={j} ({j_label}) · số={num:02d}"
            )
            cells.append(Cell(num=num, hit=hit, hitde=(hit and is_de), tooltip=tooltip))

        rows.append(
            UiRow(
                path_id=path_id,
                lag=lag,
                i=i,
                j=j,
                i_label=i_label,
                j_label=j_label,
                p_mean=p_mean,
                streak=streak,
                cells=cells,
                p_next=p_next,
            )
        )

    html = tpl.render(
        title=title,
        mode=mode,
        mode_label=mode_label(mode),
        kind=kind,
        kind_label=path_kind_label(kind),
        other_link=other_link,
        other_kind_label=other_kind_label,
        other_mode_label=other_mode_label,
        index_link=index_link,
        anchor_date=anchor_date,
        display_days=display_days,
        empty_reason=empty_reason or {},
        experience=experience or {},
        days=days,
        rows=rows,
        picks=picks,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_page(out_path, html)


def build_docs(*, repo_root: Path, display_days: int = 10) -> None:
    path_ui_dir = repo_root / "data" / "path_ui"
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str((repo_root / "src" / "templates").resolve())),
        autoescape=select_autoescape(["html", "xml"]),
    )

    index_items: list[dict[str, Any]] = []

    for mode in ["loto", "de"]:
        anchor_date = _latest_anchor_date(path_ui_dir, mode)

        for kind in ["active", "stable"]:
            ui_df = _load_ui_csv(path_ui_dir, mode, kind, anchor_date, display_days)
            picks_df = _load_picks_csv(path_ui_dir, mode, kind, anchor_date)

            # Một trang trống không kèm lời giải thích không phân biệt được với
            # một trang hỏng. Với Đặc Biệt, tỉ lệ nền là 1% nên xác suất một đường cầu
            # trúng ba kỳ liên tiếp là 1e-6: rỗng là trạng thái ĐÚNG và thường
            # gặp, không phải sự cố. Thông điệp cũ ("hãy chạy lại bước tạo dữ
            # liệu") hướng người đọc đi sửa một thứ không hỏng.
            empty_reason = _empty_reason(path_ui_dir, mode=mode, kind=kind, rows=len(ui_df))
            experience = _bridge_experience(
                path_ui_dir, mode=mode, kind=kind, anchor_date=anchor_date
            )

            out_name = f"soi-path-{mode}-{kind}.html"
            out_path = docs_dir / out_name

            other_kind = "stable" if kind == "active" else "active"
            other_link = f"soi-path-{mode}-{other_kind}.html"

            title = f"SOI CẦU {mode_label(mode).upper()} — {path_kind_label(kind).upper()}"
            _render_page(
                env,
                out_path=out_path,
                title=title,
                mode=mode,
                kind=kind,
                other_link=other_link,
                other_kind_label=path_kind_label(other_kind),
                other_mode_label=mode_label(mode),
                index_link="index.html",
                anchor_date=anchor_date,
                display_days=display_days,
                ui_df=ui_df,
                picks_df=picks_df,
                empty_reason=empty_reason,
                experience=experience,
            )

            index_items.append(
                {
                    "title": title,
                    "href": out_name,
                    "anchor_date": anchor_date,
                    "display_days": display_days,
                }
            )

    # Simple index
    idx_html = [
        "<!doctype html><html lang='vi'><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        f"{security_meta_tags()}"
        "<title>Bảng điều khiển soi cầu</title>"
        "<style>body{font-family:system-ui,Segoe UI,Roboto,Arial;margin:0;background:#0b0f17;color:#e5e7eb}"
        ".wrap{max-width:980px;margin:0 auto;padding:20px}"
        ".card{background:#0f172a;border:1px solid #1f2937;border-radius:14px;padding:14px;margin-top:12px}"
        "a{color:#93c5fd;text-decoration:none}a:hover{text-decoration:underline}"
        ".small{color:#94a3b8;font-size:12px}"
        "</style></head><body><div class='wrap'>"
        "<h1 style='margin:0;font-size:20px'>Bảng điều khiển soi cầu</h1>"
        "<div class='small'>Biên ngày / số ngày cầu chạy theo cách trình bày của trang soi cầu. "
        "Màu đỏ: về Đặc Biệt · Màu cam: loto đã về.</div>"
    ]
    for it in index_items:
        idx_html.append(
            f"<div class='card'><a href='{it['href']}'><b>{it['title']}</b></a>"
            f"<div class='small'>Ngày neo: {it['anchor_date']} · "
            f"Số ngày: {it['display_days']}</div></div>"
        )
    idx_html.append("</div></body></html>")
    write_page((docs_dir / "index.html"), "\n".join(idx_html))
    refresh_live_page(docs_dir)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--display-days", type=int, default=10)
    ap.add_argument("--repo-root", type=str, default=".")
    args = ap.parse_args()

    build_docs(repo_root=Path(args.repo_root).resolve(), display_days=args.display_days)


if __name__ == "__main__":
    main()
