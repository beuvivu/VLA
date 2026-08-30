from __future__ import annotations

import numpy as np

from significance_stats import _bh_fdr


def test_bh_fdr_is_bounded_and_monotone_in_rank() -> None:
    p = np.array([0.20, 0.001, 0.04, 0.01, 0.70], dtype=float)
    q = _bh_fdr(p)
    assert np.all((0.0 <= q) & (q <= 1.0))
    order = np.argsort(p)
    assert np.all(np.diff(q[order]) >= -1e-12)
    assert q[np.argmin(p)] <= 0.01


def test_bh_fdr_never_smaller_than_raw_p_for_valid_vector() -> None:
    p = np.array([0.001, 0.02, 0.03, 0.4, 0.9], dtype=float)
    q = _bh_fdr(p)
    assert np.all(q + 1e-12 >= p)
