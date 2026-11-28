from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_ATTEMPTS = 4
DEFAULT_BASE_DELAY = 2.0


@dataclass(frozen=True)
class RetryPolicy:

    attempts: int = DEFAULT_ATTEMPTS
    base_delay: float = DEFAULT_BASE_DELAY
    retry_on: tuple[type[BaseException], ...] = (OSError, TimeoutError)

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts phải ít nhất bằng 1")
        if self.base_delay < 0:
            raise ValueError("base_delay không được âm")

    def delay_for(self, attempt: int) -> float:
        return self.base_delay * (2**attempt)


def with_retry(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy | None = None,
    description: str = "thao tác",
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    policy = policy or RetryPolicy()
    last: BaseException | None = None
    for attempt in range(policy.attempts):
        try:
            return operation()
        except policy.retry_on as exc:
            last = exc
            if attempt == policy.attempts - 1:
                break
            wait = policy.delay_for(attempt)
            logger.warning(
                "%s hỏng lần %d/%d (%s); thử lại sau %.0fs",
                description,
                attempt + 1,
                policy.attempts,
                exc,
                wait,
            )
            sleep(wait)
    assert last is not None
    raise last


def first_available(
    sources: Sequence[tuple[str, Callable[[], T]]],
    *,
    description: str = "nguồn dữ liệu",
) -> tuple[str, T]:
    if not sources:
        raise ValueError("phải có ít nhất một nguồn")
    errors: list[str] = []
    for name, loader in sources:
        try:
            return name, loader()
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.warning("%s %r không dùng được: %s", description, name, exc)
    raise RuntimeError(f"mọi {description} đều hỏng:\n  " + "\n  ".join(errors))
