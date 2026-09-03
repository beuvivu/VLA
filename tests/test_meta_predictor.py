from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from meta_predictor import (
    COMPONENT_COLS,
    META_SCHEMA_VERSION,
    META_FEATURE_COLUMNS,
    blend_predictions,
    build_meta_features,
    current_component_frame,
    meta_feature_columns,
    predict_meta,
)


def _history_frame(days: int = 2) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    base = np.linspace(0.01, 0.20, 100)
    for i in range(days):
        rows.append(
            pd.DataFrame(
                {
                    "target_date": [f"2026-08-{20 + i:02d}"] * 100,
                    "number": np.arange(100),
                    "p_ml": base + 0.001 * i,
                    "p_cau": base[::-1] + 0.001 * i,
                    "p_stat": np.roll(base, i + 1),
                    "p_active": np.roll(base, i + 2),
                    "p_stable": np.roll(base, i + 3),
                    "y": np.zeros(100, dtype=int),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def test_meta_features_are_prediction_time_only_and_finite() -> None:
    raw = _history_frame()
    features = build_meta_features(raw, "loto")
    assert len(features) == 200
    assert "y" not in features.columns
    assert set(META_FEATURE_COLUMNS).issubset(features.columns)
    assert np.isfinite(features[META_FEATURE_COLUMNS].to_numpy(dtype=float)).all()


def test_de_components_are_normalized_per_day() -> None:
    features = build_meta_features(_history_frame(), "de")
    for col in COMPONENT_COLS:
        sums = features.groupby("target_date")[col].sum().to_numpy(dtype=float)
        assert np.allclose(sums, 1.0, atol=1e-10)


def test_current_frame_contains_exactly_one_00_to_99_universe() -> None:
    p = np.full(100, 0.01)
    frame = current_component_frame("2026-09-01", p, p, p, p, p)
    assert frame["number"].tolist() == list(range(100))
    assert frame["target_date"].nunique() == 1


def test_meta_blend_respects_trust_bounds_and_de_normalization() -> None:
    linear = np.linspace(0.001, 0.02, 100)
    meta = linear[::-1]
    p0 = blend_predictions("de", linear, meta, 0.0)
    p40 = blend_predictions("de", linear, meta, 0.40)
    p_over = blend_predictions("de", linear, meta, 2.0)
    assert np.isclose(p0.sum(), 1.0)
    assert np.isclose(p40.sum(), 1.0)
    assert np.allclose(p40, p_over)
    assert not np.allclose(p0, p40)


def test_loto_meta_blend_stays_in_probability_bounds() -> None:
    linear = np.linspace(0.05, 0.45, 100)
    meta = np.linspace(0.50, 0.10, 100)
    blended = blend_predictions("loto", linear, meta, 0.25)
    assert np.all((blended > 0.0) & (blended < 1.0))


def test_meta_blend_rejects_nonfinite_probabilities_and_trust() -> None:
    valid = np.full(100, 0.2)
    invalid = valid.copy()
    invalid[0] = np.nan

    with pytest.raises(ValueError, match="finite"):
        blend_predictions("loto", valid, invalid, 0.2)
    with pytest.raises(ValueError, match="meta_trust"):
        blend_predictions("loto", valid, valid, float("nan"))


def test_meta_pack_cannot_expand_the_production_feature_allowlist() -> None:
    class Model:
        def predict_proba(self, values: np.ndarray) -> np.ndarray:
            return np.column_stack(
                [np.full(len(values), 0.8), np.full(len(values), 0.2)]
            )

    components = ["p_ml", "p_active", "p_stable"]
    pack = {
        "schema_version": META_SCHEMA_VERSION,
        "mode": "loto",
        "component_cols": components,
        "features": [*meta_feature_columns(components), "rejected_experiment"],
        "model": Model(),
    }
    p = np.full(100, 0.2)

    with pytest.raises(ValueError, match="feature allowlist"):
        predict_meta(pack, "loto", "2026-09-01", p, p, p, p, p)

    pack["schema_version"] = float(META_SCHEMA_VERSION)
    pack["features"] = meta_feature_columns(components)
    with pytest.raises(ValueError, match="schema metadata"):
        predict_meta(pack, "loto", "2026-09-01", p, p, p, p, p)
