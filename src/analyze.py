from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd

from lottery import RepoPaths, Lottery
from plot_utils import save_distribution, save_heatmap, save_ranked_bar
from templates import Render


logger = logging.getLogger(__name__)


def _last_appearing_table(df: pd.DataFrame, value_columns: list[str]) -> pd.DataFrame:
    """Return a table indexed by number 00..99 with the last appearance delta."""
    numbers = df[value_columns].copy()
    numbers.reset_index(inplace=True)  # create numeric 'index'
    predict_index = int(numbers["index"].max()) + 1

    melted = numbers.melt(id_vars="index", var_name="prize", value_name="value")
    melted["value"] = (melted["value"].astype(int) % 100).astype(int)

    last_idx = melted.groupby("value")["index"].max().to_frame(name="last_index")
    last_idx["delta"] = predict_index - last_idx["last_index"].astype(int)
    return last_idx.drop(columns=["last_index"])


def _save_heatmap(matrix: pd.DataFrame, *, title: str, out_path: Path, cmap: str = "YlOrRd") -> None:
    save_heatmap(matrix, title=title, out_path=out_path, cmap=cmap, cbar_label="Số ngày / tần suất")


def _save_top10_bar(df: pd.DataFrame, *, x_col: str, y_col: str, title: str, out_path: Path, cmap: str = "YlOrRd") -> None:
    save_ranked_bar(df, x=x_col, y=y_col, title=title, out_path=out_path, top_n=len(df), cmap=cmap, ylabel=y_col)


def plot_last_appearing(
    df: pd.DataFrame,
    *,
    value_columns: list[str],
    output_prefix: str,
    paths: RepoPaths,
) -> None:
    table = _last_appearing_table(df, value_columns)

    heatmap_data = table.copy()
    heatmap_data["tens"] = heatmap_data.index // 10
    heatmap_data["ones"] = heatmap_data.index % 10
    heatmap = (
        heatmap_data[["tens", "ones", "delta"]]
        .pivot(index="tens", columns="ones", values="delta")
        .fillna(0)
        .astype(int)
    )

    top10 = table.sort_values("delta", ascending=False).head(10).reset_index(names="value")
    top10["value"] = top10["value"].apply(lambda r: f"{int(r):02d}")

    _save_heatmap(heatmap, title="Delta", out_path=paths.images_dir / f"{output_prefix}.jpg", cmap="YlOrRd")
    _save_top10_bar(
        top10,
        x_col="value",
        y_col="delta",
        title="Top 10",
        out_path=paths.images_dir / f"{output_prefix}_top_10.jpg",
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    lottery = Lottery()
    lottery.load()

    results = lottery.get_raw_data()
    sparse_results = lottery.get_sparse_data()
    paths = RepoPaths.from_module()

    if results.empty:
        logger.warning("No data found. Run src/fetch.py first.")
        return

    last_date = results["date"].max()

    results_2_year = results[
        (last_date - pd.Timedelta(days=365 * 2) < results["date"]) & (results["date"] <= last_date)
    ]
    results_2_year = results_2_year.reset_index(drop=True)

    small_results = results[
        (last_date - pd.Timedelta(days=365) < results["date"]) & (results["date"] <= last_date)
    ]
    small_results = small_results.reset_index(drop=True)

    # Special prize last-appearance delta (2 years)
    plot_last_appearing(results_2_year, value_columns=["special"], output_prefix="special_delta", paths=paths)

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
    render = Render(template_dir=paths.root / "src" / "templates")
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
    detail.sort_values("freq", ascending=False, inplace=True)

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

    # Last appearing Loto (1 year)
    value_columns = [c for c in small_results.columns if c != "date"]
    plot_last_appearing(small_results, value_columns=value_columns, output_prefix="delta", paths=paths)


if __name__ == "__main__":
    main()
