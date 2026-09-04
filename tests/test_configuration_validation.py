from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest

from cau_keo_ml import CauKeoConfig
from cau_position_evidence import PositionEvidenceConfig
from calibration import CalibParams
from ml_features import FeatureParams, build_ml_table
from ml_validation import ValidationConfig
from path_models import PathParams


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bootstrap_replicates": 0},
        {"bootstrap_replicates": 10.5},
        {"bootstrap_seed": -1},
        {"bootstrap_seed": True},
        {"confidence_level": "0.95"},
        {"confidence_level": float("nan")},
        {"minimum_oos_dates": 0},
        {"minimum_skill": True},
        {"minimum_skill": float("nan")},
    ],
)
def test_validation_config_fails_closed_for_invalid_values(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        ValidationConfig(**kwargs)


def test_feature_params_reject_invalid_values() -> None:
    for kwargs in ({"w1": 0}, {"w2": True}, {"lag_max_for_path_support": 1.5}):
        with pytest.raises(ValueError):
            FeatureParams(**kwargs)


def test_ml_feature_builder_rejects_unknown_mode_before_loading_data() -> None:
    with pytest.raises(ValueError, match="mode"):
        build_ml_table("unknown", FeatureParams())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CauKeoConfig(window_days=0),
        lambda: CauKeoConfig(top=101),
        lambda: CauKeoConfig(top=False),
        lambda: PathParams(lag_max=0),
        lambda: PathParams(alpha=np.nan),
        lambda: PathParams(beta="1"),
        lambda: PathParams(min_current_streak=-1),
        lambda: PositionEvidenceConfig(top_positions_per_number=0),
        lambda: PositionEvidenceConfig(scope="unknown"),
        lambda: CalibParams(mode="loto", temperature=True),
    ],
)
def test_research_configs_reject_invalid_values(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        factory()
