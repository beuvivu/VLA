from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
TEMPLATES = SRC / "web" / "templates"
ASSETS = SRC / "web" / "assets"

DATA_MOVES = {
    name: f"{group}/{name}"
    for group, names in {
        "stats": "advanced conditional cycle descriptive_ext hazard markov number_dynamics pairs "
                 "reference significance statistical_signal",
        "soi_cau": "path_ui position_bridges bridge_pages",
        "forecast": "predict online knowledge multi_hit agents feature_attribution",
        "evaluation": "history model_quality prob_eval confidence fun_draw prediction_board",
        "research": "hypotheses",
    }.items()
    for name in names.split()
}


def legacy_data_path(rel: str) -> str | None:
    group, _, rest = rel.partition("/")
    name, sep, tail = rest.partition("/")
    if DATA_MOVES.get(name) != f"{group}/{name}":
        return None
    return name + sep + tail
