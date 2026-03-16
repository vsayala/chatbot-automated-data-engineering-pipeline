"""Timing and resource instrumentation helpers."""

from __future__ import annotations

import resource
import time
from contextlib import contextmanager
from dataclasses import dataclass
from logging import Logger


@dataclass(slots=True)
class TimingResult:
    """Stores execution timing metrics."""

    start_epoch: float
    end_epoch: float

    @property
    def duration_seconds(self) -> float:
        """Return duration in seconds."""
        return self.end_epoch - self.start_epoch


@contextmanager
def timed_operation(logger: Logger, operation_name: str):
    """Context manager that logs duration and resource usage."""
    start = time.perf_counter()
    logger.info("operation_started name=%s", operation_name)
    try:
        yield
    finally:
        end = time.perf_counter()
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss_kb = usage.ru_maxrss
        logger.info(
            "operation_finished name=%s duration_seconds=%.3f cpu_user_seconds=%.3f cpu_system_seconds=%.3f max_rss_kb=%s",
            operation_name,
            end - start,
            usage.ru_utime,
            usage.ru_stime,
            rss_kb,
        )
