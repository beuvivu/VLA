"""Phục hồi lỗi tài nguyên/số học hữu hạn; lỗi đầu vào vẫn được báo rõ."""
from __future__ import annotations

from functools import wraps
from typing import Callable, ParamSpec, TypeVar

import numpy as np

P = ParamSpec('P')
R = TypeVar('R')


class NumericalModelError(FloatingPointError):
    """Model tạo loss, gradient, optimizer hoặc prediction không hữu hạn."""


def require_finite(value: np.ndarray | float, context: str) -> None:
    """Chặn trạng thái số học hỏng trước clipping hoặc commit."""
    if not np.isfinite(value).all():
        raise NumericalModelError(f'Nonfinite {context}')


def auto_patch_and_retry(
    *, on_error: Callable[[MemoryError | FloatingPointError, int], bool], max_retries: int = 1,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Thử lại khi callback đã giảm công việc/sửa trạng thái một cách rõ ràng.

    Args:
        on_error: Callback nhận lỗi và số lần retry (từ 1), trả True để thử lại.
        max_retries: Giới hạn từ 0 đến 3; không có vòng retry vô hạn.

    Returns:
        Decorator giữ signature của callable và không bắt lỗi đầu vào/lập trình.

    Raises:
        ValueError: Khi giới hạn retry không hợp lệ.
    """
    if type(max_retries) is not int or not 0 <= max_retries <= 3:
        raise ValueError('max_retries must be an integer in 0..3')
    def decorate(operation: Callable[P, R]) -> Callable[P, R]:
        @wraps(operation)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            attempts = 0
            while True:
                try:
                    return operation(*args, **kwargs)
                except (MemoryError, FloatingPointError) as error:
                    if attempts >= max_retries:
                        raise
                    attempts += 1
                    if not on_error(error, attempts):
                        raise
        return wrapped
    return decorate


class RecoveryLog:
    """Bộ đếm bền vững và tối đa 32 sự kiện phục hồi, không lưu thông báo lỗi thô."""

    def __init__(self) -> None:
        self.counts = {'prediction_fallback':0, 'training_skip':0, 'tree_retry':0}
        self.events: list[dict] = []

    def record(self, event: str, expert: str, draw_id: int, error: BaseException) -> None:
        reason = ('MemoryError' if isinstance(error, MemoryError) else
                  'NumericalModelError' if isinstance(error, NumericalModelError) else 'FloatingPointError')
        self.counts[event] += 1
        self.events = (self.events + [{'event':event, 'expert':expert, 'draw_id':draw_id,
                                      'reason':reason}])[-32:]

    def to_dict(self) -> dict:
        return {'counts':dict(self.counts), 'events':[dict(event) for event in self.events]}

    @classmethod
    def from_dict(cls, data: dict, *, names: list[str]) -> RecoveryLog:
        """Kiểm telemetry trước khi đưa lại vào checkpoint."""
        out = cls()
        if set(data['counts']) != set(out.counts) or any(type(v) is not int or v < 0 for v in data['counts'].values()):
            raise ValueError('Invalid recovery counters')
        events = data['events']
        if not isinstance(events, list) or len(events) > min(32, sum(data['counts'].values())):
            raise ValueError('Invalid recovery history')
        for event in events:
            if (not isinstance(event, dict) or set(event) != {'event', 'expert', 'draw_id', 'reason'}
                or event['event'] not in out.counts or event['expert'] not in names
                or type(event['draw_id']) is not int or event['draw_id'] < 1
                or event['reason'] not in ('MemoryError', 'FloatingPointError', 'NumericalModelError')):
                raise ValueError('Invalid recovery event')
        if any(sum(event['event'] == key for event in events) > value for key, value in data['counts'].items()):
            raise ValueError('Inconsistent recovery counters')
        out.counts, out.events = dict(data['counts']), [dict(event) for event in events]
        return out
