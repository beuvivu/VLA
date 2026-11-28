from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from soi_cau.bridges.firewall import FirewallGate
from soi_cau.bridges.replication import (
    MIN_REPLICATION_DAYS,
    ReplicationGate,
    slice_tensor,
)
from soi_cau.bridges.scanner import BridgeScanner
from soi_cau.bridges.scanner import DigitTensor
from core.xsmb_domain import FIELD_WIDTHS

def _scanner() -> BridgeScanner:
    return BridgeScanner(max_span=1, shadows=("thuc",), transformations=("concat",))


def _raw_frame(specials: list[int], rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for offset, special in enumerate(specials):
        row: dict[str, object] = {
            "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=offset)
        }
        for field, width in FIELD_WIDTHS:
            row[field] = (
                int(special) if field == "special"
                else int(rng.integers(0, 10**width))
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _planted_specials(n: int, rng: np.random.Generator, *, plant_until: int) -> list[int]:
    specials = [int(rng.integers(10_000, 100_000))]
    for t in range(1, n):
        previous = specials[-1]
        head = previous // 1000
        if t < plant_until:
            specials.append(int(rng.integers(0, 1000)) * 100 + head)
        else:
            specials.append(int(rng.integers(10_000, 100_000)))
    return specials


def _tensor(n: int, *, plant_until: int, seed: int = 7) -> DigitTensor:
    rng = np.random.default_rng(seed)
    return DigitTensor.from_raw(_raw_frame(_planted_specials(n, rng, plant_until=plant_until), rng))


def _gate(**kwargs) -> ReplicationGate:
    kwargs.setdefault("firewall", FirewallGate(permutations=2))
    return ReplicationGate(**kwargs)


def test_a_signal_that_dies_after_the_split_is_rejected() -> None:
    n = 500
    tensor = _tensor(n, plant_until=int(n * 0.60))
    gate = _gate(holdout_fraction=0.40)
    verdict, found = gate.screen(tensor, _scanner(), target_type="de")

    assert verdict.conclusive
    assert found.survived > 0, "đoạn phát hiện phải thấy đường cầu đã cài"
    assert verdict.discovered > 0
    assert verdict.replicated == 0, (
        f"{verdict.replicated} đường tái lập, lẽ ra 0 — tín hiệu đã chết tại mốc cắt"
    )
    assert "KHÔNG đường nào tái lập" in verdict.describe()


def test_a_signal_present_throughout_does_replicate() -> None:
    n = 500
    tensor = _tensor(n, plant_until=n)
    verdict, found = _gate(holdout_fraction=0.40).screen(tensor, _scanner(), target_type="de")

    assert verdict.conclusive
    assert found.survived > 0
    assert verdict.replicated > 0, "tín hiệu có mặt ở cả hai đoạn phải tái lập được"

    assert (verdict.bridges["skill_replication"] > 0.0).all()
    assert (
        verdict.bridges["precision_replication"]
        > verdict.bridges["expected_rate_replication"]
    ).all()
    assert (verdict.bridges["q_value_replication"] <= verdict.alpha).all()


def test_pure_noise_yields_no_replicated_bridge() -> None:
    n = 500
    rng = np.random.default_rng(11)
    specials = [int(rng.integers(10_000, 100_000)) for _ in range(n)]
    tensor = DigitTensor.from_raw(_raw_frame(specials, rng))

    verdict, _found = _gate(holdout_fraction=0.40).screen(tensor, _scanner(), target_type="de")
    assert verdict.conclusive
    assert verdict.replicated == 0


def test_the_holdout_half_never_influences_selection() -> None:
    n = 500
    base = _tensor(n, plant_until=n, seed=3)
    gate = _gate(holdout_fraction=0.40)
    split = gate.split_index(base)

    rng = np.random.default_rng(99)
    mutated_values = base.values.copy()
    mutated_values[split:] = rng.integers(0, 10, size=mutated_values[split:].shape, dtype=np.uint8)
    mutated_de = base.de_index.copy()
    mutated_de[split:] = rng.integers(0, 100, size=mutated_de[split:].shape).astype(np.int16)
    mutated_counts = base.loto_counts.copy()
    mutated_counts[split:] = 0
    mutated = DigitTensor(
        values=mutated_values,
        dates=base.dates,
        position_labels=base.position_labels,
        loto_counts=mutated_counts,
        de_index=mutated_de,
    )

    _v1, found_base = gate.screen(base, _scanner(), target_type="de")
    _v2, found_mut = gate.screen(mutated, _scanner(), target_type="de")

    columns = ["position_a", "position_b", "lag_a", "lag_b", "shadow", "transformation"]
    left = found_base.bridges[columns].sort_values(columns).reset_index(drop=True)
    right = found_mut.bridges[columns].sort_values(columns).reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right)


def test_a_short_holdout_is_reported_inconclusive_not_passed() -> None:
    n = MIN_REPLICATION_DAYS + 40
    tensor = _tensor(n, plant_until=n)
    verdict, _found = _gate(holdout_fraction=0.10).screen(tensor, _scanner(), target_type="de")

    assert verdict.conclusive is False
    assert verdict.replicated == 0
    assert "KHÔNG kết luận được" in verdict.describe()


def test_slicing_keeps_the_column_axis_intact() -> None:
    tensor = _tensor(300, plant_until=300)
    piece = slice_tensor(tensor, 50, 200)

    assert piece.n_days == 150
    assert piece.position_labels == tensor.position_labels
    assert piece.n_positions == tensor.n_positions
    assert list(piece.dates) == list(tensor.dates[50:200])


@pytest.mark.parametrize("bounds", [(-1, 10), (10, 10), (0, 10_000)])
def test_an_invalid_slice_is_refused(bounds: tuple[int, int]) -> None:
    tensor = _tensor(300, plant_until=300)
    with pytest.raises(ValueError, match="không hợp lệ"):
        slice_tensor(tensor, *bounds)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [({"holdout_fraction": 0.95}, "holdout_fraction"), ({"alpha": 0.0}, "alpha")],
)
def test_invalid_configuration_is_refused(kwargs: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        ReplicationGate(**kwargs)
