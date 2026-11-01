"""Bộ đọc CSV mặc định phải khôi phục float đúng từng bit (01-11-2026).

`online_learning._prediction_frame` và `daily_forecast` từng đọc dự báo đã công bố bằng
`float_precision="round_trip"`: so `np.array_equal` giữa vector đã ghi và vector đọc lại quyết định
có ghi lại tệp hay không, nên lệch một ULP là đổi tệp công bố. pandas 3.1 bỏ tham số ấy (Pandas4Warning)
vì bộ đọc mặc định đã chính xác — pandas 3.0.5 thì CHƯA: đo trên 350 000 giá trị, mặc định của 3.0.5
lệch, của 3.1.0 trùng từng bit. Hai nơi đọc nay dựa vào mặc định; phép kiểm này đỏ nếu một bản pandas
khác lại đọc lệch.
"""
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
