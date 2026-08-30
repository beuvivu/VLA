from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib import pyplot as plt
from matplotlib.colors import Normalize


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_heatmap(
    matrix: pd.DataFrame,
    *,
    title: str,
    out_path: Path,
    cmap: str = "YlOrRd",
    cbar_label: str = "Giá trị",
    value_fmt: str = "d",
) -> None:
    """Save a readable 10x10 matrix with a low→high color gradient.

    The function uses matplotlib directly to avoid seaborn/pandas compatibility
    edge cases in scheduled GitHub Actions runs.
    """
    data = matrix.copy()
    if data.empty:
        return

    data = data.sort_index(axis=0).sort_index(axis=1)
    values = data.to_numpy(dtype=float)
    finite_values = values[np.isfinite(values)]
    vmin = float(np.nanmin(finite_values)) if finite_values.size else 0.0
    vmax = float(np.nanmax(finite_values)) if finite_values.size else 1.0
    if np.isclose(vmin, vmax):
        vmax = vmin + 1.0

    fig, ax = plt.subplots(figsize=(11, 8), dpi=160)
    im = ax.imshow(values, cmap=cmap, vmin=vmin, vmax=vmax, aspect="equal")

    ax.set_title(title, fontsize=15, fontweight="bold", pad=14)
    ax.set_xlabel("Hàng đơn vị", fontsize=11)
    ax.set_ylabel("Hàng chục", fontsize=11)
    ax.set_xticks(np.arange(data.shape[1]), labels=[str(c) for c in data.columns])
    ax.set_yticks(np.arange(data.shape[0]), labels=[str(i) for i in data.index])

    # Gridlines make the matrix easier to scan.
    ax.set_xticks(np.arange(-0.5, data.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-0.5, data.shape[0], 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.4)
    ax.tick_params(which="minor", bottom=False, left=False)

    norm = Normalize(vmin=vmin, vmax=vmax)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            raw = values[i, j]
            label = "" if not np.isfinite(raw) else format(int(raw), value_fmt)
            text_color = "white" if norm(raw) >= 0.62 else "#111827"
            ax.text(j, i, label, ha="center", va="center", fontsize=10, fontweight="bold", color=text_color)

    cbar = fig.colorbar(im, ax=ax, shrink=0.84)
    cbar.set_label(cbar_label)

    fig.tight_layout()
    _ensure_dir(out_path)
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def save_ranked_bar(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    title: str,
    out_path: Path,
    top_n: int = 20,
    cmap: str = "YlGnBu",
    ylabel: str | None = None,
) -> None:
    """Save a ranked bar chart with value-based gradient colors."""
    if df.empty:
        return

    view = df.sort_values(y, ascending=False).head(top_n).copy()
    vals = view[y].astype(float).to_numpy()
    vmin = float(np.nanmin(vals)) if vals.size else 0.0
    vmax = float(np.nanmax(vals)) if vals.size else 1.0
    if np.isclose(vmin, vmax):
        vmax = vmin + 1.0

    norm = Normalize(vmin=vmin, vmax=vmax)
    cm = colormaps.get_cmap(cmap)
    colors = [cm(norm(v)) for v in vals]

    labels = view[x].astype(str).tolist()
    positions = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(12, 6), dpi=160)
    bars = ax.bar(positions, vals, color=colors)
    ax.set_xticks(positions, labels=labels)

    ax.set_title(title, fontsize=15, fontweight="bold", pad=12)
    ax.set_xlabel("Bộ số", fontsize=11)
    ax.set_ylabel(ylabel or y, fontsize=11)
    ax.grid(axis="y", linestyle="--", linewidth=0.7, alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)

    ymax = float(np.nanmax(vals)) if vals.size else 1.0
    offset = max(0.3, ymax * 0.015)
    for bar, value in zip(bars, vals, strict=False):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + offset,
            f"{value:.0f}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    ax.set_ylim(0, ymax * 1.14 + offset)
    fig.tight_layout()
    _ensure_dir(out_path)
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def save_distribution(
    values: Iterable[float],
    *,
    title: str,
    out_path: Path,
    mean: float | None = None,
    std: float | None = None,
    xlabel: str = "Tần suất",
) -> None:
    vals = np.asarray(list(values), dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return

    bins = max(8, int(vals.max() - vals.min() + 1))
    fig, ax = plt.subplots(figsize=(11, 6), dpi=160)
    counts, edges, patches = ax.hist(vals, bins=bins, edgecolor="white", linewidth=0.8)

    cm = colormaps.get_cmap("YlGnBu")
    norm = Normalize(vmin=float(counts.min()), vmax=float(counts.max()) if counts.size else 1.0)
    for c, patch in zip(counts, patches, strict=False):
        patch.set_facecolor(cm(norm(float(c))))

    if mean is not None:
        ax.axvline(float(mean), linestyle="-", linewidth=2, label=f"Mean={mean:.2f}")
    if mean is not None and std is not None:
        for k, style in [(1, "--"), (2, ":")]:
            ax.axvline(float(mean) - k * float(std), linestyle=style, linewidth=1.2, alpha=0.75)
            ax.axvline(float(mean) + k * float(std), linestyle=style, linewidth=1.2, alpha=0.75)

    ax.set_title(title, fontsize=15, fontweight="bold", pad=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Số lượng bộ số")
    ax.grid(axis="y", linestyle="--", linewidth=0.7, alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)
    if mean is not None:
        ax.legend()

    fig.tight_layout()
    _ensure_dir(out_path)
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def save_labeled_heatmap(
    matrix: pd.DataFrame,
    *,
    title: str,
    out_path: Path,
    cmap: str = "YlOrRd",
    cbar_label: str = "Giá trị",
    xlabel: str = "",
    ylabel: str = "",
    value_fmt: str = ".0f",
    annotate: bool = True,
    max_annotated_cells: int = 260,
    figsize: tuple[float, float] | None = None,
) -> None:
    """Save a generic labeled heatmap for period x number matrices.

    Unlike ``save_heatmap`` this function does not assume a 10x10 tens/ones
    layout. It is useful for weekly/monthly/yearly matrices where rows are
    periods and columns are numbers or groups.
    """
    if matrix.empty:
        return

    data = matrix.copy()
    values = data.to_numpy(dtype=float)
    finite_values = values[np.isfinite(values)]
    vmin = float(np.nanmin(finite_values)) if finite_values.size else 0.0
    vmax = float(np.nanmax(finite_values)) if finite_values.size else 1.0
    if np.isclose(vmin, vmax):
        vmax = vmin + 1.0

    n_rows, n_cols = values.shape
    if figsize is None:
        figsize = (max(10.0, min(24.0, n_cols * 0.34)), max(5.0, min(18.0, n_rows * 0.38)))

    fig, ax = plt.subplots(figsize=figsize, dpi=160)
    im = ax.imshow(values, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")

    ax.set_title(title, fontsize=15, fontweight="bold", pad=14)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xticks(np.arange(n_cols), labels=[str(c) for c in data.columns])
    ax.set_yticks(np.arange(n_rows), labels=[str(i) for i in data.index])

    if n_cols > 20:
        ax.tick_params(axis="x", labelrotation=90, labelsize=7)
    else:
        ax.tick_params(axis="x", labelrotation=0, labelsize=9)
    if n_rows > 28:
        ax.tick_params(axis="y", labelsize=7)
    else:
        ax.tick_params(axis="y", labelsize=9)

    ax.set_xticks(np.arange(-0.5, n_cols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_rows, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.65)
    ax.tick_params(which="minor", bottom=False, left=False)

    if annotate and (n_rows * n_cols <= max_annotated_cells):
        norm = Normalize(vmin=vmin, vmax=vmax)
        for i in range(n_rows):
            for j in range(n_cols):
                raw = values[i, j]
                if not np.isfinite(raw):
                    continue
                label = format(raw, value_fmt)
                text_color = "white" if norm(raw) >= 0.62 else "#111827"
                ax.text(j, i, label, ha="center", va="center", fontsize=8, fontweight="bold", color=text_color)

    cbar = fig.colorbar(im, ax=ax, shrink=0.86)
    cbar.set_label(cbar_label)

    fig.tight_layout()
    _ensure_dir(out_path)
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
