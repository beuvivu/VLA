"""Quét toàn bộ họ cầu ghép chéo ngày bằng phép toán ma trận.

Bố cục tính toán
----------------
Với mỗi bộ ba (độ trễ A, độ trễ B, bóng), khối ứng viên là một phép quảng bá duy
nhất cho ra mảng ``(số ngày, 107, 107)``: ``cand[t, i, j]`` là con số mà cặp vị
trí ``(i, j)`` dự đoán cho ngày ``t``. Ba phép biến đổi còn lại suy ra từ đó chứ
không tính lại — ``reverse_concat`` là một phép quảng bá đối xứng, và
``reverse_pair`` chỉ là phép hợp của hai ma trận trúng.

Không có vòng lặp Python nào chạy trên ngày hay trên cặp vị trí.

Điều lớp này cố tình KHÔNG làm
------------------------------
Nó không kết luận đường cầu nào đáng tin. Với 107 vị trí, chỉ riêng lag-1 đã có
11.449 cặp có hướng; mở tới biên độ 7 kèm bóng cho hơn 400.000 giả thuyết, và ở
quy mô đó hơn một trăm nghìn đường cầu sẽ "đang chạy 5 nhịp" thuần do ngẫu
nhiên. Việc sàng lọc thuộc về :mod:`bridges.firewall`, và ``scan`` trả về đối
tượng kết quả thô để chính con số "đã thử bao nhiêu giả thuyết" không bao giờ bị
đánh rơi trên đường đi.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd
from scipy import stats

from bridges.shadow import SHADOW_KINDS, shadow_table
from bridges.spec import (
    TARGET_DE,
    TARGET_LOTO,
    TARGET_LOTO_2_NHAY,
    TARGET_TYPES,
    TRANSFORM_BO,
    TRANSFORM_CONCAT,
    TRANSFORM_REVERSE_CONCAT,
    TRANSFORM_REVERSE_PAIR,
    TRANSFORMATIONS,
    default_lag_pairs,
)
from bridges.tensor import NUMBER_SPACE, DigitTensor
from number_reference import bo
from xsmb_domain import LOTO_DRAWS_PER_DAY, UNIFORM_TWO_DIGIT_RATE

_MAX_BO_MEMBERS: Final[int] = 8


def _bo_membership() -> np.ndarray:
    """Bảng ``(100, 8)``: các số cùng bộ, đệm bằng chính nó cho đủ chiều rộng.

    Đệm bằng chính số đó là an toàn vì phép kiểm trúng dùng ``any``: một thành
    viên lặp lại không thể biến một lần trượt thành lần trúng.
    """
    table = np.empty((NUMBER_SPACE, _MAX_BO_MEMBERS), dtype=np.int16)
    for number in range(NUMBER_SPACE):
        members = sorted(int(item) for item in bo(number))
        if not members:
            members = [number]
        repeats = -(-_MAX_BO_MEMBERS // len(members))
        table[number] = (members * repeats)[:_MAX_BO_MEMBERS]
    return table


_BO_TABLE: Final[np.ndarray] = _bo_membership()


_BO_SIZE: Final[np.ndarray] = np.array(
    [len({int(item) for item in bo(number)}) for number in range(NUMBER_SPACE)],
    dtype=np.int16,
)

_MAX_SET_SIZE: Final[int] = int(_BO_SIZE.max())


def _two_nhay_rate(set_size: int) -> float:
    """P(ít nhất một con trong bộ ``set_size`` con về từ hai nháy trở lên).

    Không có dạng đóng khi bộ có nhiều hơn một con, nhưng tính chính xác được:
    điều kiện theo số lần rơi vào bộ trong 27 lượt, rồi nhân với xác suất các
    lượt đó rơi vào những con khác nhau.
    """
    n, m = LOTO_DRAWS_PER_DAY, int(set_size)
    if m <= 0:
        return 0.0
    q = m * UNIFORM_TWO_DIGIT_RATE
    all_at_most_once = 0.0
    for j in range(0, min(n, m) + 1):
        distinct = 1.0
        for i in range(j):
            distinct *= (m - i) / m
        all_at_most_once += math.comb(n, j) * q**j * (1.0 - q) ** (n - j) * distinct
    return float(1.0 - all_at_most_once)


def target_baseline_rate(target_type: str, set_size: int = 1) -> float:
    """Tỉ lệ nền không thông tin cho một giả thuyết đặt cược ``set_size`` con.

    Số con đặt cược là tham số bắt buộc, không phải chi tiết phụ. Một đường cầu
    ``bo`` phát ra 8 con trúng thường xuyên hơn hẳn một đường phát ra 1 con, và
    chấm cả hai bằng cùng một tỉ lệ nền sẽ tuyên bố *mọi* cầu bộ số là có ý
    nghĩa — đo được trên dữ liệu thật: 100% cầu ``bo`` và 99% cầu ``reverse_pair``
    lọt ngưỡng p<0,05, trong khi cầu một con cho đúng 4,45% như nhiễu thuần.

    Dùng tỉ lệ lý thuyết chứ không ước lượng từ chính dữ liệu đang quét: một
    đường cơ sở học từ dữ liệu sẽ hấp thụ đúng phần tín hiệu đang đi tìm.
    """
    m = int(set_size)
    if m <= 0:
        return 0.0
    if target_type == TARGET_DE:
        return float(min(1.0, m * UNIFORM_TWO_DIGIT_RATE))
    if target_type == TARGET_LOTO_2_NHAY:
        return _two_nhay_rate(m)
    # Lô tô: xác suất ít nhất một con trong bộ xuất hiện ở 27 lượt.
    return float(1.0 - (1.0 - m * UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_DAY)


def baseline_rate_table(target_type: str) -> np.ndarray:
    """Tra cứu tỉ lệ nền theo số con đặt cược, chỉ số 0..8."""
    return np.array(
        [target_baseline_rate(target_type, m) for m in range(_MAX_SET_SIZE + 1)],
        dtype=np.float64,
    )


_RARE_EVENT_RATE: Final[float] = 0.1


def _tail_probability(
    successes: np.ndarray,
    expected: np.ndarray,
    variance: np.ndarray,
    day_rate: np.ndarray,
) -> np.ndarray:
    """P(số lần trúng >= quan sát) dưới giả thiết không có tín hiệu.

    Chọn xấp xỉ theo chế độ chứ không dùng một công thức cho mọi trường hợp.
    Với ĐB, kỳ vọng chỉ khoảng 3,9 lần trúng trên 386 ngày — vùng biến cố hiếm,
    nơi xấp xỉ chuẩn thổi phồng đuôi và biến dao động thường thành phát hiện.
    Poisson là xấp xỉ đúng cho tổng các Bernoulli hiếm và độc lập không đồng
    nhất; với lô tô (tỉ lệ nền 0,24) thì chuẩn có hiệu chỉnh liên tục mới đúng.
    """
    rare = float(np.max(day_rate)) <= _RARE_EVENT_RATE
    if rare:
        return np.asarray(stats.poisson.sf(successes - 1, expected), dtype=float)
    z = (successes - 0.5 - expected) / np.sqrt(variance)
    return np.asarray(stats.norm.sf(z), dtype=float)


@dataclass(frozen=True)
class BridgeScanResult:
    """Thống kê tóm tắt cho từng giả thuyết đã quét.

    Cố ý không giữ ma trận trúng đầy đủ: với hơn 400.000 giả thuyết trên 386
    ngày, riêng nó đã là 159 MB. Các cột nhận diện đủ để dựng lại đúng những giả
    thuyết sống sót, và chỉ những giả thuyết đó mới cần tới ma trận.
    """

    frame: pd.DataFrame
    target_type: str
    baseline: float
    n_days_evaluated: int

    @property
    def n_hypotheses(self) -> int:
        return int(len(self.frame))

    def running(self, min_streak: int = 5) -> pd.DataFrame:
        """Các đường cầu đang chạy ít nhất ``min_streak`` nhịp — CHƯA sàng lọc."""
        return self.frame[self.frame["current_streak"] >= min_streak]


class BridgeScanner:
    """Quét họ cầu ghép chéo ngày trên toàn bộ lịch sử."""

    def __init__(
        self,
        *,
        max_span: int = 3,
        shadows: tuple[str, ...] = SHADOW_KINDS,
        transformations: tuple[str, ...] = TRANSFORMATIONS,
    ) -> None:
        unknown_shadow = [s for s in shadows if s not in SHADOW_KINDS]
        if unknown_shadow:
            raise ValueError(f"loại bóng không hợp lệ: {unknown_shadow}")
        unknown_transform = [t for t in transformations if t not in TRANSFORMATIONS]
        if unknown_transform:
            raise ValueError(f"phép biến đổi không hợp lệ: {unknown_transform}")
        self.lag_pairs = default_lag_pairs(max_span)
        self.shadows = tuple(shadows)
        self.transformations = tuple(transformations)

    # -- lõi vector hóa ----------------------------------------------------

    @staticmethod
    def _aligned_sources(
        tensor: DigitTensor, lag_a: int, lag_b: int, start: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """Chữ số nguồn đã canh theo ngày mục tiêu ``start..n-1``."""
        n = tensor.n_days
        a = tensor.values[start - lag_a : n - lag_a]
        b = tensor.values[start - lag_b : n - lag_b]
        return a, b

    @staticmethod
    def _hits_for(candidates: np.ndarray, target: np.ndarray, target_type: str) -> np.ndarray:
        """Ma trận trúng ``(ngày, 107, 107)`` cho một khối ứng viên."""
        rows = np.arange(candidates.shape[0])[:, None, None]
        if target_type == TARGET_DE:
            return candidates == target[:, None, None]
        return target[rows, candidates]

    def _evaluate_block(
        self,
        candidates: np.ndarray,
        target: np.ndarray,
        target_type: str,
        *,
        expand_bo: bool,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Trả về (ma trận trúng, số con đặt cược) — hai thứ luôn đi cùng nhau.

        Tách rời chúng là cách sinh ra lỗi chấm điểm nguy hiểm nhất ở đây: một
        ma trận trúng không mang theo số con đặt cược sẽ bị chấm bằng tỉ lệ nền
        sai và biến mọi cầu bộ số thành phát hiện giả.
        """
        if not expand_bo:
            hits = self._hits_for(candidates, target, target_type)
            return hits, np.ones(candidates.shape, dtype=np.int16)

        # Bộ số biến một ứng viên thành 4 hoặc 8 con; trúng nếu bất kỳ con nào về.
        members = _BO_TABLE[candidates]
        sizes = _BO_SIZE[candidates]
        if target_type == TARGET_DE:
            return (members == target[:, None, None, None]).any(axis=-1), sizes
        rows = np.arange(candidates.shape[0])[:, None, None, None]
        return target[rows, members].any(axis=-1), sizes

    # -- API ---------------------------------------------------------------

    @property
    def start_index(self) -> int:
        """Ngày mục tiêu đầu tiên chấm được, quyết định bởi độ trễ lớn nhất."""
        return max(max(pair) for pair in self.lag_pairs)

    def _target_for(self, tensor: DigitTensor, target_type: str) -> np.ndarray:
        start = self.start_index
        if target_type == TARGET_DE:
            return tensor.de_index[start:]
        if target_type == TARGET_LOTO_2_NHAY:
            return tensor.loto_double_hits()[start:]
        return tensor.loto_hits()[start:]

    def _iter_blocks(self, tensor: DigitTensor, target: np.ndarray, target_type: str):
        """Sinh từng khối (ma trận trúng, số con đặt cược, mô tả) của họ giả thuyết.

        Cả ``scan`` lẫn phép kiểm chống data snooping đều đi qua đây, nên phân
        phối của giả thuyết rỗng chắc chắn được lấy trên ĐÚNG không gian tìm
        kiếm đã sinh ra giá trị quan sát. Hai đường duyệt riêng là cách phép kiểm
        max-statistic lặng lẽ mất hiệu lực.
        """
        start = self.start_index
        for lag_a, lag_b in self.lag_pairs:
            raw_a, raw_b = self._aligned_sources(tensor, lag_a, lag_b, start)
            for shadow in self.shadows:
                table = shadow_table(shadow)
                a, b = table[raw_a], table[raw_b]
                forward = (10 * a[:, :, None] + b[:, None, :]).astype(np.uint8)
                reverse = (10 * b[:, None, :] + a[:, :, None]).astype(np.uint8)
                pair_sizes = np.where(forward == reverse, 1, 2).astype(np.int16)

                cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
                for transformation in self.transformations:
                    if transformation == TRANSFORM_CONCAT:
                        hits, sizes = self._evaluate_block(
                            forward, target, target_type, expand_bo=False
                        )
                    elif transformation == TRANSFORM_REVERSE_CONCAT:
                        hits, sizes = self._evaluate_block(
                            reverse, target, target_type, expand_bo=False
                        )
                    elif transformation == TRANSFORM_REVERSE_PAIR:
                        first = cache.get(TRANSFORM_CONCAT) or self._evaluate_block(
                            forward, target, target_type, expand_bo=False
                        )
                        second = cache.get(TRANSFORM_REVERSE_CONCAT) or self._evaluate_block(
                            reverse, target, target_type, expand_bo=False
                        )
                        hits, sizes = first[0] | second[0], pair_sizes
                    elif transformation == TRANSFORM_BO:
                        hits, sizes = self._evaluate_block(
                            forward, target, target_type, expand_bo=True
                        )
                    else:  # pragma: no cover - đã chặn ở __init__
                        raise ValueError(transformation)

                    if transformation in (TRANSFORM_CONCAT, TRANSFORM_REVERSE_CONCAT):
                        cache[transformation] = (hits, sizes)
                    yield hits, sizes, (lag_a, lag_b, shadow, transformation)
                cache.clear()

    def scan(self, tensor: DigitTensor, *, target_type: str = TARGET_LOTO) -> BridgeScanResult:
        """Chấm điểm mọi giả thuyết trong họ và trả về thống kê tóm tắt."""
        if target_type not in TARGET_TYPES:
            raise ValueError(f"loại mục tiêu không hợp lệ: {target_type!r}")
        if tensor.n_days <= self.start_index:
            raise ValueError("lịch sử quá ngắn so với độ trễ lớn nhất")

        target = self._target_for(tensor, target_type)
        rate_table = baseline_rate_table(target_type)
        blocks = [
            self._summarise(
                hits,
                sizes,
                n_pos=tensor.n_positions,
                lag_a=meta[0],
                lag_b=meta[1],
                shadow=meta[2],
                transformation=meta[3],
                rate_table=rate_table,
            )
            for hits, sizes, meta in self._iter_blocks(tensor, target, target_type)
        ]
        return BridgeScanResult(
            frame=pd.concat(blocks, ignore_index=True),
            target_type=target_type,
            baseline=float(rate_table[1]),
            n_days_evaluated=tensor.n_days - self.start_index,
        )

    def family_max_skill(self, tensor: DigitTensor, target: np.ndarray, target_type: str) -> float:
        """Kỹ năng lớn nhất trên TOÀN họ với một chuỗi kết quả cho trước.

        Đây là thống kê mà phép kiểm chống data snooping cần. Lấy max trên tập
        đã sàng lọc thay vì trên toàn họ sẽ hạ thấp phân phối rỗng một cách giả
        tạo và biến phép kiểm thành hình thức.
        """
        rate_table = baseline_rate_table(target_type)
        best = -np.inf
        for hits, sizes, _ in self._iter_blocks(tensor, target, target_type):
            skill = hits.mean(axis=0) - rate_table[sizes].mean(axis=0)
            best = max(best, float(skill.max()))
        return best

    def rebuild_hits(
        self,
        tensor: DigitTensor,
        rows: pd.DataFrame,
        *,
        target_type: str,
    ) -> tuple[RebuiltBridges, np.ndarray]:
        """Dựng lại đúng các con đặt cược của một tập giả thuyết đã chọn.

        Bộ quét cố ý không giữ ma trận trúng đầy đủ của cả họ — với hơn 400.000
        giả thuyết đó là 159 MB. Chỉ phần sống sót mới cần dựng lại, và ở quy mô
        đó chi phí không đáng kể.
        """
        if target_type not in TARGET_TYPES:
            raise ValueError(f"loại mục tiêu không hợp lệ: {target_type!r}")
        start = max(max(pair) for pair in self.lag_pairs)
        n = tensor.n_days

        if target_type == TARGET_DE:
            target = tensor.de_index[start:]
        elif target_type == TARGET_LOTO_2_NHAY:
            target = tensor.loto_double_hits()[start:]
        else:
            target = tensor.loto_hits()[start:]

        members = np.empty((n - start, len(rows), _MAX_BO_MEMBERS), dtype=np.int16)
        sizes = np.empty((n - start, len(rows)), dtype=np.int16)

        for slot, (_, row) in enumerate(rows.iterrows()):
            table = shadow_table(str(row["shadow"]))
            lag_a, lag_b = int(row["lag_a"]), int(row["lag_b"])
            pos_a, pos_b = int(row["position_a"]), int(row["position_b"])
            a = table[tensor.values[start - lag_a : n - lag_a, pos_a]].astype(np.int16)
            b = table[tensor.values[start - lag_b : n - lag_b, pos_b]].astype(np.int16)
            forward = 10 * a + b
            reverse = 10 * b + a

            transformation = str(row["transformation"])
            if transformation == TRANSFORM_CONCAT:
                block, size = _pad_members(forward[:, None]), np.ones_like(forward)
            elif transformation == TRANSFORM_REVERSE_CONCAT:
                block, size = _pad_members(reverse[:, None]), np.ones_like(reverse)
            elif transformation == TRANSFORM_REVERSE_PAIR:
                block = _pad_members(forward[:, None], reverse[:, None])
                size = np.where(forward == reverse, 1, 2).astype(np.int16)
            elif transformation == TRANSFORM_BO:
                block = _BO_TABLE[forward][:, None, :]
                size = _BO_SIZE[forward]
            else:  # pragma: no cover - khung đã chặn từ __init__
                raise ValueError(transformation)

            members[:, slot, :] = block[:, 0, :]
            sizes[:, slot] = size

        return RebuiltBridges(members=members, sizes=sizes), target

    @staticmethod
    def _summarise(
        hits: np.ndarray,
        sizes: np.ndarray,
        *,
        n_pos: int,
        lag_a: int,
        lag_b: int,
        shadow: str,
        transformation: str,
        rate_table: np.ndarray,
    ) -> pd.DataFrame:
        n_days = hits.shape[0]
        successes = hits.sum(axis=0, dtype=np.int32).ravel()

        # Chuỗi đang chạy: đếm số True liên tiếp tính ngược từ ngày cuối. Phép
        # cumprod trên mảng đã đảo chiều tắt ngay tại lần trượt đầu tiên.
        reversed_hits = hits[::-1].astype(np.uint8)
        streak = np.cumprod(reversed_hits, axis=0).sum(axis=0, dtype=np.int32).ravel()

        # Kỳ vọng cộng dồn theo từng ngày, dùng đúng tỉ lệ nền của số con mà giả
        # thuyết đặt cược ngày đó. Cộng dồn chứ không nhân n_days với một tỉ lệ
        # duy nhất, vì reverse_pair đổi giữa 1 và 2 con tùy ngày.
        day_rate = rate_table[sizes]
        expected = day_rate.sum(axis=0).ravel()
        variance = np.maximum((day_rate * (1.0 - day_rate)).sum(axis=0).ravel(), 1e-9)
        p_value = _tail_probability(successes, expected, variance, day_rate)

        position_a, position_b = np.divmod(np.arange(n_pos * n_pos), n_pos)
        return pd.DataFrame(
            {
                "position_a": position_a.astype(np.int16),
                "position_b": position_b.astype(np.int16),
                "lag_a": np.int16(lag_a),
                "lag_b": np.int16(lag_b),
                "shadow": shadow,
                "transformation": transformation,
                "trials": np.int32(n_days),
                "successes": successes,
                "current_streak": streak,
                "precision": successes / n_days,
                "expected_rate": expected / n_days,
                "p_value": np.asarray(p_value, dtype=float),
            }
        )


@dataclass(frozen=True)
class RebuiltBridges:
    """Các con mà một nhóm giả thuyết đặt cược, dựng lại theo từng ngày.

    Mọi phép biến đổi được quy về cùng một dạng — danh sách con có đệm — nên
    phép kiểm chống data snooping chạy trên một đường duy nhất thay vì rẽ nhánh
    theo từng loại cầu. Rẽ nhánh ở đó là nơi rất dễ để một loại cầu lặng lẽ bỏ
    qua phép kiểm.
    """

    members: np.ndarray
    sizes: np.ndarray

    def hits_for(self, target: np.ndarray, target_type: str) -> np.ndarray:
        """Ma trận trúng ``(ngày, số giả thuyết)`` với một chuỗi kết quả bất kỳ."""
        if target_type == TARGET_DE:
            return (self.members == target[:, None, None]).any(axis=-1)
        rows = np.arange(self.members.shape[0])[:, None, None]
        return target[rows, self.members].any(axis=-1)


def _pad_members(*columns: np.ndarray) -> np.ndarray:
    """Xếp các con đặt cược thành mảng rộng cố định, đệm bằng chính chúng.

    Đệm bằng con đã có là an toàn vì phép kiểm trúng dùng ``any``: một con lặp
    lại không thể biến lần trượt thành lần trúng.
    """
    stacked = np.stack(columns, axis=-1).astype(np.int16)
    repeats = -(-_MAX_BO_MEMBERS // stacked.shape[-1])
    return np.tile(stacked, (1, 1, repeats))[:, :, :_MAX_BO_MEMBERS]
