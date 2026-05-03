"""
metrics.py
----------
Tiny in-process metrics collector.

Why not Prometheus? For a single-instance internal tool, exposing a
simple JSON snapshot is honest and proportionate — Prometheus would be
real overhead for less real value. The contract is also stable enough
that adding a Prometheus exporter later is mechanical (counters become
`Counter`, histograms become `Histogram`, the values come from here).

Usage:
    from .metrics import metrics
    with metrics.timer("chat"):
        ...
    metrics.snapshot()  # -> dict for /api/metrics
"""

from __future__ import annotations

import bisect
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Iterator


class _Histogram:
    """Keeps every observed latency for one route. Cheap for our scale."""

    __slots__ = ("samples",)

    def __init__(self) -> None:
        self.samples: list[float] = []

    def observe(self, value_ms: float) -> None:
        # Keep insertion sorted so percentiles are O(1) lookups.
        bisect.insort(self.samples, value_ms)

    def percentile(self, p: float) -> float:
        if not self.samples:
            return 0.0
        idx = max(0, min(len(self.samples) - 1, int(round(p * (len(self.samples) - 1)))))
        return self.samples[idx]

    def avg(self) -> float:
        return (sum(self.samples) / len(self.samples)) if self.samples else 0.0


class Metrics:
    """Thread-safe counters + per-route latency histograms."""

    def __init__(self) -> None:
        self._lock      = threading.Lock()
        self._started   = time.time()
        self._counters: dict[str, int]         = defaultdict(int)
        self._hist:     dict[str, _Histogram]  = defaultdict(_Histogram)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def incr(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._counters[name] += by

    def observe_ms(self, name: str, value_ms: float) -> None:
        with self._lock:
            self._hist[name].observe(value_ms)

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        """Context manager that records elapsed ms + bumps a counter."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe_ms(name, (time.perf_counter() - start) * 1000)
            self.incr(f"{name}.count")

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            histograms = {
                name: {
                    "count":  len(h.samples),
                    "avg_ms": round(h.avg(),           2),
                    "p50_ms": round(h.percentile(.50), 2),
                    "p95_ms": round(h.percentile(.95), 2),
                    "p99_ms": round(h.percentile(.99), 2),
                }
                for name, h in self._hist.items()
            }
            return {
                "uptime_seconds": round(time.time() - self._started, 1),
                "counters":       dict(self._counters),
                "latency_ms":     histograms,
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._hist.clear()
            self._started = time.time()


# Module-level singleton — there's only one Flask process per container.
metrics = Metrics()
