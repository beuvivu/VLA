"""Chọn chu kỳ bán rã bằng số đo thay vì đặt tay.

Giá trị cũ là 45 kỳ, chọn bằng cảm tính, và nó đặt thành phần nặng nhất của
tầng tín hiệu thống kê vào chỗ mù hoàn toàn. Đo walk-forward 300 kỳ cuối trên
dữ liệu thật, kèm tiêm tín hiệu +100 % vào một con:

    bán rã   ESS    Brier         ngụy tín hiệu   thu hồi tín hiệu
        45   130    0,18134089    0,00001          0,0 %
       180   519    0,18133923    0,00002         36,0 %
       365  1031    0,18133891    0,00003         63,9 %
         ∞  2398    0,18133866    0,00009         90,4 %

Brier tốt lên ĐƠN ĐIỆU theo chu kỳ dài hơn. Ngụy tín hiệu tăng chín lần nhưng
vẫn ở mức 0,009 điểm phần trăm trên nền 23,77 % — tức hai mặt của đánh đổi này
lệch nhau nhiều bậc độ lớn.

Phép kiểm ở đây khoá cả hai chiều: chọn dài khi dữ liệu đòi, giữ ngắn khi
không đo được khác biệt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statistical_signal import (
    HALF_LIFE_GRID,
    MIN_HALF_LIFE_SELECTION_DAYS,
    select_half_life,
)


def _stationary(days: int, rate: float = 0.2377, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.random((days, 100)) < rate).astype(float)


def test_stationary_heterogeneity_earns_a_longer_window() -> None:
    """Có khác biệt thật và không trôi thì dữ liệu càng nhiều càng tốt.

    Chu kỳ ngắn vứt bỏ phần lớn lịch sử; ở mức 45 kỳ trên 2 398 kỳ, cỡ mẫu
    hiệu dụng chỉ còn 130 — và ở mức ấy thành phần `ewm` thu hồi ĐÚNG 0 % của
    một tín hiệu gấp đôi tần suất nền.

    Phải có khác biệt THẬT giữa các con số thì phép so mới có gì để đo. Bản
    đầu tôi viết ca này với dữ liệu đồng nhất hoàn toàn, và ở ngưỡng 2 SE nó
    đúng là không chọn gì — vì quả thật không chu kỳ nào hơn được chu kỳ nào
    khi mọi con số giống hệt nhau.
    """
    rng = np.random.default_rng(7)
    rates = np.clip(rng.normal(0.2377, 0.06, size=100), 0.05, 0.6)
    hit = (rng.random((900, 100)) < rates[None, :]).astype(float)

    chosen, scores = select_half_life(hit)
    assert scores is not None
    assert chosen > HALF_LIFE_GRID[0], f"chọn {chosen}; lẽ ra phải dài hơn 45"


def test_homogeneous_noise_keeps_the_incumbent_window() -> None:
    """Không có gì để đo thì KHÔNG đổi — ngưỡng 2 SE phải chặn ở đây.

    Đây là nửa còn lại của cổng: mọi con số cùng tỉ lệ nên mọi chu kỳ đều
    tương đương, và một thay đổi kiến trúc không được thắng nhờ nhiễu.
    """
    chosen, scores = select_half_life(_stationary(900))
    assert scores is not None
    assert chosen == HALF_LIFE_GRID[0], f"chọn {chosen}; không gì hơn được 45"


def test_a_drifting_history_is_given_a_short_window() -> None:
    """Chiều ngược lại, và là chiều dễ mất nhất.

    Một bộ chọn luôn chọn chu kỳ dài nhất sẽ qua được phép kiểm trên kia mà
    hỏng hẳn khi dữ liệu thật sự trôi. Ca này đảo tỉ lệ ở giữa lịch sử.
    """
    rng = np.random.default_rng(1)
    days = 900
    hit = np.empty((days, 100))
    hit[: days // 2] = (rng.random((days // 2, 100)) < 0.35).astype(float)
    hit[days // 2 :] = (rng.random((days - days // 2, 100)) < 0.12).astype(float)

    chosen, scores = select_half_life(hit)
    assert scores is not None
    assert chosen <= 180, f"chọn {chosen}; dữ liệu trôi thì phải dùng cửa sổ ngắn"


def test_indistinguishable_candidates_keep_the_shorter_window() -> None:
    """Chênh lệch KHÔNG ĐO ĐƯỢC là hoà, và hoà thì bản linh hoạt hơn thắng.

    Câu hỏi đúng không phải "chênh bao nhiêu" mà "chênh ấy có đo được không".
    Bản đầu tôi dùng dung sai TƯƠNG ĐỐI và nó sụp đổ ở đúng ca này: với dữ liệu
    mà mọi con đều trúng, Brier bằng 0 nên ``|best| * 1e-6`` cũng bằng 0, không
    gì hoà, và bộ chọn quay lại quyết định theo chữ số cuối — nó chọn 1460.
    """
    # Mọi con số trúng mọi kỳ: mọi chu kỳ đều cho cùng kết quả, nên phải ra
    # chu kỳ ngắn nhất.
    chosen, scores = select_half_life(np.full((600, 100), 1.0))
    assert scores is not None
    assert chosen == HALF_LIFE_GRID[0], f"chọn {chosen} trên dữ liệu không phân biệt được"
    assert max(scores.values()) - min(scores.values()) < 1e-9


def test_a_short_history_refuses_to_choose_and_says_so() -> None:
    """Lịch sử ngắn thì giữ giá trị đầu lưới và báo KHÔNG chọn.

    Chọn trên vài chục kỳ là chọn theo nhiễu; im lặng chọn bừa còn tệ hơn giữ
    nguyên mặc định.
    """
    chosen, scores = select_half_life(_stationary(MIN_HALF_LIFE_SELECTION_DAYS - 1))
    assert scores is None
    assert chosen == HALF_LIFE_GRID[0]


def test_the_grid_starts_at_the_legacy_value() -> None:
    """Giá trị cũ phải nằm trong lưới, và ở đầu lưới.

    Nó là mặc định khi không chọn được, và là bản thắng khi hoà — nên mọi hành
    vi cũ đều tái lập được bằng cách để dữ liệu ngắn hoặc các ứng viên hoà nhau.
    """
    assert HALF_LIFE_GRID[0] == 45
    assert list(HALF_LIFE_GRID) == sorted(HALF_LIFE_GRID)
    assert len(set(HALF_LIFE_GRID)) == len(HALF_LIFE_GRID)


def test_the_signal_reports_which_half_life_it_chose_and_why() -> None:
    """Không báo cáo điểm từng ứng viên thì lựa chọn không kiểm chứng được."""
    import statistical_signal as ss

    days = 400
    dates = pd.date_range("2025-01-01", periods=days, freq="D")
    rng = np.random.default_rng(5)
    numbers = rng.integers(0, 100, size=(days, 27))
    two = pd.DataFrame({"date": dates, "special": numbers[:, 0]})
    for i in range(1, 27):
        two[f"p{i}"] = numbers[:, i]
    counts = np.zeros((days, 100), dtype=int)
    for t in range(days):
        np.add.at(counts[t], numbers[t], 1)
    sparse = pd.DataFrame(counts)
    sparse.insert(0, "date", dates)

    class _Fake:
        def load(self): return None
        def get_2_digits_data(self): return two.copy()
        def get_sparse_data(self): return sparse.copy()

    original = ss.Lottery
    try:
        ss.Lottery = lambda: _Fake()
        _df, diag = ss.build_statistical_signal("loto")
        _df2, forced = ss.build_statistical_signal("loto", half_life=45)
    finally:
        ss.Lottery = original

    assert diag["half_life_learned"] is True
    assert diag["half_life_days"] in HALF_LIFE_GRID
    assert set(diag["half_life_brier_by_candidate"]) == {str(v) for v in HALF_LIFE_GRID}

    # Ép một giá trị thì phải báo là KHÔNG học, và dùng đúng giá trị ấy.
    assert forced["half_life_learned"] is False
    assert forced["half_life_days"] == 45
    assert forced["half_life_brier_by_candidate"] is None


@pytest.mark.parametrize("days", [0, 1, 5])
def test_a_degenerate_history_does_not_crash(days: int) -> None:
    chosen, scores = select_half_life(np.zeros((days, 100)))
    assert chosen == HALF_LIFE_GRID[0]
    assert scores is None
