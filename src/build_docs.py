from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from path_models import index_to_label
from ui_locale import mode_label, path_kind_label


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


def _latest_anchor_date(path_ui_dir: Path, mode: str) -> str:
    # files: ui_{mode}_{kind}_{YYYY-MM-DD}_{Nd}d.csv
    pat = re.compile(rf"ui_{re.escape(mode)}_(?:active|stable)_(\d{{4}}-\d{{2}}-\d{{2}})_(\d+)d\.csv$")
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


def _load_ui_csv(path_ui_dir: Path, mode: str, kind: str, anchor_date: str, display_days: int) -> pd.DataFrame:
    p = path_ui_dir / f"ui_{mode}_{kind}_{anchor_date}_{display_days}d.csv"
    if not p.exists():
        raise FileNotFoundError(f"Thiếu tệp giao diện: {p}")
    return pd.read_csv(p)


def _load_picks_csv(path_ui_dir: Path, mode: str, kind: str, anchor_date: str) -> pd.DataFrame:
    p = path_ui_dir / f"predict_next_{mode}_{kind}_{anchor_date}.csv"
    if not p.exists():
        raise FileNotFoundError(f"Thiếu tệp gợi ý: {p}")
    return pd.read_csv(p)


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
) -> None:
    tpl = env.get_template("path_ui_page.html.j2")

    # Identify day columns: *_num, *_hit, *_is_de
    # run_path_ui exports daily cols as YYYY-MM-DD_num, etc.
    day_nums = [c for c in ui_df.columns if c.endswith("_num")]
    days = [c[:-4] for c in day_nums]  # remove _num

    # Prepare picks
    picks: list[PickRow] = []
    for _, r in picks_df.head(20).iterrows():
        picks.append(PickRow(number=int(r["number"]), prob=float(r["prob"]), support_paths_count=int(r["support_paths_count"])))

    # Rows
    rows: list[UiRow] = []
    for idx, r in ui_df.iterrows():
        lag = int(r.get("lag", 0))
        i = int(r.get("i", 0))
        j = int(r.get("j", 0))

        i_label = str(r.get("i_label", "")) or index_to_label(i)
        j_label = str(r.get("j_label", "")) or index_to_label(j)

        p_mean = float(r.get("p_mean", 0.0))
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

        rows.append(UiRow(path_id=path_id, lag=lag, i=i, j=j, i_label=i_label, j_label=j_label, p_mean=p_mean, streak=streak, cells=cells))

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
        days=days,
        rows=rows,
        picks=picks,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


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
        "<title>Bảng điều khiển soi cầu</title>"
        "<style>body{font-family:system-ui,Segoe UI,Roboto,Arial;margin:0;background:#0b0f17;color:#e5e7eb}"
        ".wrap{max-width:980px;margin:0 auto;padding:20px}"
        ".card{background:#0f172a;border:1px solid #1f2937;border-radius:14px;padding:14px;margin-top:12px}"
        "a{color:#93c5fd;text-decoration:none}a:hover{text-decoration:underline}"
        ".small{color:#94a3b8;font-size:12px}"
        "</style></head><body><div class='wrap'>"
        "<h1 style='margin:0;font-size:20px'>Bảng điều khiển soi cầu</h1>"
        "<div class='small'>Biên ngày / số ngày cầu chạy theo cách trình bày của trang soi cầu. "
        "Màu đỏ: về ĐB · Màu cam: loto đã về.</div>"
    ]
    for it in index_items:
        idx_html.append(
            f"<div class='card'><a href='{it['href']}'><b>{it['title']}</b></a>"
            f"<div class='small'>Ngày neo: {it['anchor_date']} · "
            f"Số ngày: {it['display_days']}</div></div>"
        )
    idx_html.append("</div></body></html>")
    (docs_dir / "index.html").write_text("\n".join(idx_html), encoding="utf-8")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--display-days", type=int, default=10)
    ap.add_argument("--repo-root", type=str, default=".")
    args = ap.parse_args()

    build_docs(repo_root=Path(args.repo_root).resolve(), display_days=args.display_days)


if __name__ == "__main__":
    main()
