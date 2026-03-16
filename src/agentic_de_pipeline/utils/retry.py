"""Retry helpers for transient failures."""

from __future__ import annotations

import time
from dataclasses import dataclass
from logging import Logger
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class RetryPolicy:
    """Retry policy with exponential backoff controls."""

    attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 8.0
    backoff_multiplier: float = 2.0


def run_with_retry(
    operation_name: str,
    action: Callable[[], T],
    policy: RetryPolicy,
    logger: Logger,
) -> T:
    """Run action with retries and exponential backoff."""
    delay = policy.initial_delay_seconds
    last_error: Exception | None = None

    for attempt in range(1, policy.attempts + 1):
        try:
            return action()
        except Exception as exc:  # pylint: disable=broad-except
            last_error = exc
            logger.warning(
                "operation_retry_failed name=%s attempt=%s/%s error=%s",
                operation_name,
                attempt,
                policy.attempts,
                exc,
            )
            if attempt >= policy.attempts:
                break
            time.sleep(delay)
            delay = min(delay * policy.backoff_multiplier, policy.max_delay_seconds)

    assert last_error is not None
    raise last_error
