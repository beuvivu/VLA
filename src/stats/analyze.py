from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd

from core.paths import TEMPLATES
from ingest.lottery import RepoPaths, Lottery
from stats.plot_utils import save_distribution, save_heatmap, save_ranked_bar
from web.templates import Render


logger = logging.getLogger(__name__)


def _save_heatmap(matrix: pd.DataFrame, *, title: str, out_path: Path, cmap: str = "YlOrRd") -> None:
    save_heatmap(matrix, title=title, out_path=out_path, cmap=cmap, cbar_label="Số ngày / tần suất")


def _save_top10_bar(df: pd.DataFrame, *, x_col: str, y_col: str, title: str, out_path: Path, cmap: str = "YlOrRd") -> None:
    save_ranked_bar(df, x=x_col, y=y_col, title=title, out_path=out_path, top_n=len(df), cmap=cmap, ylabel=y_col)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    lottery = Lottery()
    lottery.load()

    results = lottery.get_raw_data()
    sparse_results = lottery.get_sparse_data()
    paths = RepoPaths.from_module()

    if results.empty:
        logger.warning("No data found. Run src/ingest/fetch.py first.")
        return

    last_date = results["date"].max()

    small_results = results[
        (last_date - pd.Timedelta(days=365) < results["date"]) & (results["date"] <= last_date)
    ]
    small_results = small_results.reset_index(drop=True)

    # Loto "Đầu/đuôi" table for the most recent draw
    recent_results = (small_results.iloc[-1].values[1:] % 100).astype(int)
    loto_result: list[str] = []
    for tens in range(10):
        category = sorted([d for d in recent_results if d // 10 == tens])
        loto_result.append(", ".join([f"{d % 10:d}" for d in category]) if category else "-")

    # One-year distribution for loto
    if sparse_results.empty:
        logger.warning("Sparse results are empty; cannot compute distribution charts.")
        return

    last_sparse_date = sparse_results["date"].max()
    sparse_1_year = sparse_results[
        (last_sparse_date - pd.Timedelta(days=365) < sparse_results["date"])
        & (sparse_results["date"] <= last_sparse_date)
    ]
    sparse_1_year = sparse_1_year.reset_index(drop=True)

    counts = sparse_1_year.drop(columns=["date"]).sum(axis=0)
    max_count = float(counts.max().round(2))
    min_count = float(counts.min().round(2))
    mean = float(counts.mean().round(2))
    std = float(counts.std().round(2))

    # Render README from template
    render = Render(template_dir=TEMPLATES)
    content = render(
        "README.j2",
        loto_result=loto_result,
        max_count=max_count,
        min_count=min_count,
        mean=mean,
        std=std,
        **small_results.iloc[-1].to_dict(),
    )
    (paths.root / "README.md").write_text(content, encoding="utf-8")

    # Detail plots
    detail = counts.reset_index()
    detail.columns = ["value", "freq"]
    detail = detail.astype({"value": int})
    detail = detail.sort_values("freq", ascending=False, kind="stable")

    heatmap_data = detail.copy()
    heatmap_data["tens"] = heatmap_data["value"] // 10
    heatmap_data["ones"] = heatmap_data["value"] % 10
    heatmap = (
        heatmap_data[["tens", "ones", "freq"]]
        .pivot(index="tens", columns="ones", values="freq")
        .fillna(0)
        .astype(int)
    )
    _save_heatmap(heatmap, title="Tần suất loto 1 năm", out_path=paths.images_dir / "heatmap.jpg", cmap="YlGnBu")

    # Top 10
    top10 = detail.head(10).copy()
    top10["value"] = top10["value"].apply(lambda r: f"{int(r):02d}")
    _save_top10_bar(top10, x_col="value", y_col="freq", title="Top 10 tần suất loto", out_path=paths.images_dir / "top-10.jpg", cmap="YlGnBu")

    # Distribution
    save_distribution(
        detail["freq"].to_numpy(),
        title="Phân bổ tần suất loto 1 năm",
        out_path=paths.images_dir / "distribution.jpg",
        mean=mean,
        std=std,
        xlabel="Số lần xuất hiện",
    )


if __name__ == "__main__":
    main()
