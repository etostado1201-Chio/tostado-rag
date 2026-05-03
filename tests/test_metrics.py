"""Tests for backend.metrics and the /api/metrics endpoint."""

from __future__ import annotations

import time

from backend.metrics import Metrics, metrics


# ---------------------------------------------------------------------------
# Metrics class unit tests
# ---------------------------------------------------------------------------

def test_counters_start_at_zero():
    m = Metrics()
    snap = m.snapshot()
    assert snap["counters"]    == {}
    assert snap["latency_ms"]  == {}
    assert snap["uptime_seconds"] >= 0


def test_incr():
    m = Metrics()
    m.incr("foo")
    m.incr("foo")
    m.incr("bar", by=5)
    snap = m.snapshot()
    assert snap["counters"] == {"foo": 2, "bar": 5}


def test_observe_records_a_histogram():
    m = Metrics()
    for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        m.observe_ms("op", v)
    h = m.snapshot()["latency_ms"]["op"]
    assert h["count"]  == 10
    assert h["avg_ms"] == 55.0
    assert h["p50_ms"] == 50.0
    assert h["p95_ms"] >= 90.0
    assert h["p99_ms"] >= 90.0


def test_timer_records_elapsed_and_increments_count():
    m = Metrics()
    with m.timer("slow"):
        time.sleep(0.01)
    snap = m.snapshot()
    assert snap["counters"]["slow.count"] == 1
    h = snap["latency_ms"]["slow"]
    assert h["count"] == 1
    assert h["avg_ms"] >= 5  # we slept ~10ms — be generous on CI


def test_reset_clears_state():
    m = Metrics()
    m.incr("x")
    m.observe_ms("y", 100)
    m.reset()
    snap = m.snapshot()
    assert snap["counters"]   == {}
    assert snap["latency_ms"] == {}


# ---------------------------------------------------------------------------
# Endpoint integration test
# ---------------------------------------------------------------------------

def test_metrics_endpoint_returns_snapshot(client):
    metrics.reset()

    # Drive a couple of requests through to populate the histograms.
    client.post("/api/chat", json={"message": "Who manages GOLDEN_CRISP-0001?"})
    client.post("/api/chat", json={"message": "And the address?"})

    res = client.get("/api/metrics")
    assert res.status_code == 200

    body = res.get_json()
    assert "uptime_seconds" in body
    assert "counters"       in body
    assert "latency_ms"     in body

    # Two chat calls should be visible
    assert body["counters"].get("chat.count", 0) >= 2
    assert "chat" in body["latency_ms"]
    assert body["latency_ms"]["chat"]["count"] >= 2
