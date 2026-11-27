from __future__ import annotations

import numpy as np
import pandas as pd

FULL_TABLE_CUTS: dict[str, str] = {
    "research/crosslag_positional/crosslag_rules.csv":
        "research/crosslag_positional/crosslag_rules_top.csv",
    "stats/conditional/loto_nextday_given_special_long.csv":
        "stats/conditional/current_special_next_loto.csv",
    "research/research_firewall_loto.csv": "research/research_firewall_loto_top.csv",
    "research/research_firewall_de.csv": "research/research_firewall_de_top.csv",
    "research/path_timelines/path_timeline_loto.csv":
        "research/path_timelines/path_timeline_loto_top.csv",
    "research/path_timelines/path_timeline_de.csv":
        "research/path_timelines/path_timeline_de_top.csv",
    "research/legacy_extensions/pair_recency_loto.csv":
        "research/legacy_extensions/pair_recency_loto_top.csv",
}


def cut_ranked(
    table: pd.DataFrame,
    *,
    rows: int,
    keep: str | None = None,
    smallest: str | None = None,
) -> pd.DataFrame:
    if table.empty:
        return table.copy()
    ordered = table.reset_index(drop=True)
    mask = np.zeros(len(ordered), dtype=bool)
    mask[:rows] = True
    if keep is not None:
        mask |= ordered[keep].astype(bool).to_numpy()
    if smallest is not None:
        values = pd.to_numeric(ordered[smallest], errors="coerce")
        mask[values.sort_values(kind="stable").index[:rows]] = True
    return ordered[mask].reset_index(drop=True)
