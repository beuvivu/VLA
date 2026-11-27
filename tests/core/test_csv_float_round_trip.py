from __future__ import annotations

import io

import numpy as np
import pandas as pd


def test_the_default_csv_reader_restores_every_float_bit_for_bit():
    rng = np.random.default_rng(20261101)
    values = np.concatenate([rng.random(100_000), rng.random(20_000) * 1e-12,
                             rng.standard_normal(20_000) * 1e6, 1 / np.arange(1, 20_001)])
    text = pd.DataFrame({"prob": values}).to_csv(index=False)
    assert np.array_equal(pd.read_csv(io.StringIO(text))["prob"].to_numpy(), values)
