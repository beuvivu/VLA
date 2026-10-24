"""Bốn chuyên gia thống kê nhân quả, co về nền khi chưa đủ quan sát."""
from __future__ import annotations

from numbers import Integral, Real

import numpy as np


class PatternExperts:
    """Học tần suất, chuyển trạng thái và hazard; không coi số vắng là đến hạn.

    Mỗi vector biểu diễn tỷ lệ xuất hiện của từng node, kể cả tỷ lệ phân số
    từ nhiều bộ số trong cùng kỳ. Chỉ điều kiện hiện diện dùng ``target > 0``.
    Trọng số prior và nhóm tuổi cố định, không chọn lại bằng kỳ đang chấm.
    """

    names = ('bayes_short', 'bayes_long', 'markov_repeat', 'gap_hazard')
    _half_lives = np.array([16., 128.])
    _frequency_prior = np.array([32., 128.])
    _markov_prior = 32.
    _gap_prior = 64.
    _gap_edges = np.array([1, 2, 3, 4, 6, 9, 13, 20, 32, 64])
    _arrays = ('frequency_success', 'frequency_mass', 'markov_success', 'markov_total',
               'previous_present', 'gap_success', 'gap_total', 'gap_age', 'gap_known')

    def __init__(self, nodes: int, base: float) -> None:
        if isinstance(nodes, (bool, np.bool_)) or not isinstance(nodes, Integral) or nodes < 1:
            raise ValueError('Số node phải là số nguyên dương.')
        if (isinstance(base, (bool, np.bool_)) or not isinstance(base, Real)
                or not np.isfinite(base) or not 0 < base < 1):
            raise ValueError('Xác suất nền phải hữu hạn và nằm giữa 0 và 1.')
        self.nodes, self.base = int(nodes), float(base)
        self.seen = 0
        self.last_id: int | None = None
        self.frequency_success = np.zeros((2, self.nodes))
        self.frequency_mass = np.zeros(2)
        self.markov_success = np.zeros((2, self.nodes))
        self.markov_total = np.zeros((2, self.nodes))
        self.previous_present = np.zeros(self.nodes, dtype=bool)
        bins = len(self._gap_edges) + 1
        self.gap_success = np.zeros((bins, self.nodes))
        self.gap_total = np.zeros((bins, self.nodes))
        self.gap_age = np.zeros(self.nodes, dtype=np.int64)
        self.gap_known = np.zeros(self.nodes, dtype=bool)

    def predict(self, next_id: int | None = None) -> np.ndarray:
        """Đọc posterior; target qua kỳ thiếu không dùng điều kiện một bước cũ."""
        if next_id is not None and (isinstance(next_id, (bool, np.bool_))
                or not isinstance(next_id, Integral) or next_id < 1
                or self.last_id is not None and next_id <= self.last_id):
            raise ValueError('Target phải có ID nguyên dương sau kỳ đã học.')
        horizon = int(next_id) - self.last_id if next_id is not None and self.last_id is not None else 1
        # Thời gian chưa có nhãn chỉ làm quên trọng số cũ, không thêm nhãn 0.
        decay = np.exp2(-min(horizon - 1, 1_000_000) / self._half_lives)
        frequency = ((self.frequency_success * decay[:, None] + self._frequency_prior[:, None] * self.base)
                     / (self.frequency_mass[:, None] * decay[:, None] + self._frequency_prior[:, None]))
        columns = np.arange(self.nodes)
        condition = self.previous_present.astype(int)
        markov = ((self.markov_success[condition, columns] + self._markov_prior * self.base)
                  / (self.markov_total[condition, columns] + self._markov_prior))
        bins = np.searchsorted(self._gap_edges, self.gap_age + 1)
        gap = ((self.gap_success[bins, columns] + self._gap_prior * self.base)
               / (self.gap_total[bins, columns] + self._gap_prior))
        gap = np.where(self.gap_known, gap, self.base)
        if horizon > 1:
            markov, gap = np.full(self.nodes, self.base), np.full(self.nodes, self.base)
        return np.vstack((frequency, markov, gap))

    def observe(self, target: np.ndarray, draw_id: int) -> None:
        """Xác thực trước khi ghi; kỳ thiếu không sinh nhãn hay chuyển trạng thái."""
        raw = np.asarray(target)
        if raw.dtype.kind not in 'biuf' or raw.shape != (self.nodes,):
            raise ValueError('Target phải là vector số đúng số node.')
        row = raw.astype(float)
        if not np.isfinite(row).all() or ((row < 0) | (row > 1)).any():
            raise ValueError('Target phải hữu hạn và nằm trong [0, 1].')
        if (isinstance(draw_id, (bool, np.bool_)) or not isinstance(draw_id, Integral)
                or draw_id < 1 or self.last_id is not None and draw_id <= self.last_id):
            raise ValueError('ID kỳ phải là số nguyên dương tăng nghiêm ngặt.')
        draw_id = int(draw_id)
        elapsed = draw_id - self.last_id if self.last_id is not None else 1
        decay = np.exp2(-min(elapsed, 1_000_000) / self._half_lives)
        success = self.frequency_success * decay[:, None] + row
        mass = self.frequency_mass * decay + 1
        present = row > 0
        # Các mảng candidate tách rời; nhãn đầu vào lỗi không ghi một phần state.
        markov_success, markov_total = self.markov_success.copy(), self.markov_total.copy()
        gap_success, gap_total = self.gap_success.copy(), self.gap_total.copy()
        known, age = self.gap_known.copy(), self.gap_age.copy()
        if self.last_id is not None and elapsed == 1:
            columns = np.arange(self.nodes)
            condition = self.previous_present.astype(int)
            markov_success[condition, columns] += row
            markov_total[condition, columns] += 1
            selected = columns[known]
            bins = np.searchsorted(self._gap_edges, age[selected] + 1)
            gap_success[bins, selected] += row[selected]
            gap_total[bins, selected] += 1
            age[known] = np.minimum(age[known] + 1, self._gap_edges[-1])
        else:
            known[:] = False
            age[:] = 0
        # Chỉ một lần hiện diện đã quan sát mới khôi phục tuổi sau kiểm duyệt.
        known[present] = True
        age[present] = 0
        self.frequency_success, self.frequency_mass = success, mass
        self.markov_success, self.markov_total = markov_success, markov_total
        self.gap_success, self.gap_total = gap_success, gap_total
        self.previous_present, self.gap_known, self.gap_age = present, known, age
        self.seen, self.last_id = self.seen + 1, draw_id

    def to_dict(self) -> dict:
        """Checkpoint chỉ gồm JSON dữ liệu và bản sao độc lập của các mảng."""
        return {'version': 1, 'nodes': self.nodes, 'base': self.base, 'seen': self.seen,
                'last_id': self.last_id, **{name: getattr(self, name).tolist() for name in self._arrays}}

    @classmethod
    def from_dict(cls, data: dict, *, nodes: int, base: float) -> PatternExperts:
        """Chỉ phục hồi sau kiểm cấu hình, hình dạng, miền giá trị và bộ đếm."""
        out = cls(nodes, base)
        keys = {'version', 'nodes', 'base', 'seen', 'last_id', *cls._arrays}
        if not isinstance(data, dict) or set(data) != keys:
            raise ValueError('Checkpoint mẫu hình thiếu hoặc thừa trường.')
        if (type(data['version']) is not int or data['version'] != 1
                or type(data['nodes']) is not int or data['nodes'] != out.nodes
                or isinstance(data['base'], bool) or not isinstance(data['base'], (int, float))
                or not np.isfinite(data['base']) or data['base'] != out.base):
            raise ValueError('Checkpoint mẫu hình khác cấu hình.')
        seen, last_id = data['seen'], data['last_id']
        if (type(seen) is not int or seen < 0
                or seen == 0 and last_id is not None
                or seen > 0 and (type(last_id) is not int or last_id < seen)):
            raise ValueError('Bộ đếm mẫu hình không hợp lệ.')
        for name in cls._arrays:
            previous = getattr(out, name)
            raw = np.asarray(data[name])
            if raw.shape != previous.shape:
                raise ValueError('Mảng checkpoint mẫu hình sai hình dạng.')
            if previous.dtype.kind == 'b':
                if raw.dtype.kind != 'b':
                    raise ValueError('Cờ checkpoint mẫu hình phải là boolean.')
            elif (raw.dtype.kind not in 'iuf' or not np.isfinite(raw).all()
                  or (raw < 0).any() or previous.dtype.kind == 'i' and (raw != np.floor(raw)).any()):
                raise ValueError('Mảng checkpoint mẫu hình sai miền giá trị.')
            if name == 'gap_age' and (raw > min(cls._gap_edges[-1], max(seen - 1, 0))).any():
                raise ValueError('Tuổi gap vượt nhóm cuối checkpoint.')
            setattr(out, name, raw.astype(previous.dtype))
        out.seen, out.last_id = seen, last_id
        tolerance = 1e-9
        if (np.any(out.frequency_mass > seen + tolerance)
                or np.any(out.frequency_mass > 1 / (1 - np.exp2(-1 / cls._half_lives)) + tolerance)
                or np.any(out.frequency_success > out.frequency_mass[:, None] + tolerance)
                or out.frequency_mass[0] > out.frequency_mass[1] + tolerance
                or seen > 0 and (out.frequency_mass < 1).any()):
            raise ValueError('Khối lượng tần suất checkpoint không hợp lệ.')
        for success_name, total_name in (('markov_success', 'markov_total'), ('gap_success', 'gap_total')):
            successes, totals = getattr(out, success_name), getattr(out, total_name)
            if ((totals != np.floor(totals)).any() or (totals > max(seen - 1, 0)).any()
                    or (successes > totals + tolerance).any()
                    or (totals.sum(axis=0) > max(seen - 1, 0)).any()):
                raise ValueError('Số lần thử hoặc thành công checkpoint không hợp lệ.')
        if (not np.all(out.markov_total.sum(axis=0) == out.markov_total[:, 0].sum())
                or (out.gap_age > cls._gap_edges[-1]).any()
                or (out.gap_age[~out.gap_known] != 0).any()
                or (out.previous_present & (~out.gap_known | (out.gap_age != 0))).any()
                or (out.gap_known & ~out.previous_present & (out.gap_age == 0)).any()
                or seen == 0 and any(getattr(out, name).any() for name in cls._arrays)):
            raise ValueError('Trạng thái điều kiện hoặc tuổi gap checkpoint không hợp lệ.')
        return out
