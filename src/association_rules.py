from __future__ import annotations

"""Support/confidence/lift mining over canonical lottery draw sets."""

import math

import numpy as np
import pandas as pd

from conditional_matrices import (
    MatrixEvidence,
    build_cooccurrence_matrix,
    build_transition_matrix,
)


def _wilson_lower(successes: int, observations: int, z: float = 1.96) -> float:
    if observations <= 0:
        return 0.0
    probability = successes / observations
    denominator = 1.0 + z * z / observations
    center = probability + z * z / (2.0 * observations)
    margin = z * math.sqrt(
        probability * (1.0 - probability) / observations
        + z * z / (4.0 * observations * observations)
    )
    return float((center - margin) / denominator)


def _validate_threshold(name: str, value: float, *, upper: float | None = None) -> None:
    if not np.isfinite(value) or value < 0.0 or (upper is not None and value > upper):
        suffix = f" and <= {upper}" if upper is not None else ""
        raise ValueError(f"{name} must be finite, >= 0{suffix}")


def _select_evidence(
    history: pd.DataFrame,
    as_of_date: object,
    *,
    lag_days: int,
    alpha: float,
) -> MatrixEvidence:
    if lag_days == 0:
        return build_cooccurrence_matrix(history, as_of_date, alpha=alpha)
    if lag_days == 1:
        return build_transition_matrix(history, as_of_date, alpha=alpha)
    raise ValueError("lag_days currently supports 0 (same draw) or 1 (next calendar day)")


def mine_association_rules(
    history: pd.DataFrame,
    as_of_date: object,
    *,
    lag_days: int = 0,
    min_support: float = 0.01,
    min_confidence: float = 0.0,
    min_lift: float = 0.0,
    minimum_antecedent_observations: int = 10,
    alpha: float = 1.0,
    include_self: bool = False,
) -> pd.DataFrame:
    """Mine directed ``A -> B`` rules with raw evidence and smoothing.

    Definitions use all eligible observations: support is ``count(A and B)/N``;
    confidence is ``count(A and B)/count(A)``; and lift is confidence divided
    by the marginal probability of B.  Wilson's lower confidence bound is
    included so tiny perfect samples do not outrank well-supported rules solely
    because their raw confidence equals one.
    """
    _validate_threshold("min_support", min_support, upper=1.0)
    _validate_threshold("min_confidence", min_confidence, upper=1.0)
    _validate_threshold("min_lift", min_lift)
    if minimum_antecedent_observations < 1:
        raise ValueError("minimum_antecedent_observations must be >= 1")
    evidence = _select_evidence(
        history,
        as_of_date,
        lag_days=lag_days,
        alpha=alpha,
    )
    rows: list[dict[str, object]] = []
    for antecedent in range(100):
        antecedent_count = int(evidence.source_counts[antecedent])
        if antecedent_count < minimum_antecedent_observations:
            continue
        for consequent in range(100):
            if not include_self and antecedent == consequent:
                continue
            support = float(evidence.support[antecedent, consequent])
            confidence = float(evidence.confidence[antecedent, consequent])
            lift = float(evidence.lift[antecedent, consequent])
            if support < min_support or confidence < min_confidence or lift < min_lift:
                continue
            joint = int(evidence.counts[antecedent, consequent])
            rows.append(
                {
                    "antecedent": antecedent,
                    "antecedent_str": f"{antecedent:02d}",
                    "consequent": consequent,
                    "consequent_str": f"{consequent:02d}",
                    "lag_days": lag_days,
                    "relation": evidence.relation,
                    "eligible_observations": evidence.eligible_observations,
                    "antecedent_count": antecedent_count,
                    "consequent_count": int(evidence.target_counts[consequent]),
                    "joint_count": joint,
                    "support": support,
                    "confidence": confidence,
                    "smoothed_confidence": float(
                        evidence.smoothed_probability[antecedent, consequent]
                    ),
                    "confidence_wilson_lower": _wilson_lower(joint, antecedent_count),
                    "lift": lift,
                    "as_of_date": evidence.as_of_date,
                }
            )
    if not rows:
        return pd.DataFrame(
            columns=[
                "antecedent",
                "antecedent_str",
                "consequent",
                "consequent_str",
                "lag_days",
                "relation",
                "eligible_observations",
                "antecedent_count",
                "consequent_count",
                "joint_count",
                "support",
                "confidence",
                "smoothed_confidence",
                "confidence_wilson_lower",
                "lift",
                "as_of_date",
            ]
        )
    return pd.DataFrame(rows).sort_values(
        ["confidence_wilson_lower", "joint_count", "lift"],
        ascending=False,
        ignore_index=True,
    )
