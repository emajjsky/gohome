const assert = require("node:assert/strict");
const test = require("node:test");
const { RollingStreamMetrics, intervalRate } = require("../stream-metrics");

test("intervalRate measures accepted frame intervals instead of startup window age", () => {
    assert.equal(intervalRate([]), 0);
    assert.equal(intervalRate([1000]), 0);
    assert.equal(intervalRate([1000, 1100, 1200, 1300]), 10);
});

test("rolling stream metrics report throughput, jitter, transport, freshness, and rejects", () => {
    const metrics = new RollingStreamMetrics();
    const received = [10000, 10100, 10200, 10400];
    const transport = [40, 50, 60, 80];
    received.forEach((receivedAtMs, index) => {
        metrics.record("camera-2", {
            accepted: true,
            capturedAt: new Date(receivedAtMs - transport[index]).toISOString(),
            receivedAtMs,
        });
    });
    metrics.record("camera-2", { accepted: false, receivedAtMs: 10410 });

    const camera = metrics.snapshot(10450)["camera-2"];
    assert.equal(camera.accepted_fps_10s, 7.5);
    assert.equal(camera.accepted_sample_count_10s, 4);
    assert.equal(camera.frame_gap_ms_p95, 100);
    assert.equal(camera.frame_gap_ms_max, 200);
    assert.equal(camera.transport_latency_ms_p95, 60);
    assert.equal(camera.transport_latency_ms_max, 80);
    assert.equal(camera.last_frame_age_ms, 50);
    assert.equal(camera.stale_rejections, 1);
    assert.equal(camera.last_received_at, new Date(10400).toISOString());
});

test("rolling stream metrics exclude samples outside the reporting window", () => {
    const metrics = new RollingStreamMetrics({ windowMs: 10000 });
    metrics.record(7, { accepted: true, receivedAtMs: 1000 });
    metrics.record(7, { accepted: true, receivedAtMs: 11000 });
    metrics.record(7, { accepted: true, receivedAtMs: 11500 });

    const camera = metrics.snapshot(11500)["7"];
    assert.equal(camera.accepted_sample_count_10s, 2);
    assert.equal(camera.accepted_fps_10s, 2);
    assert.equal(camera.frame_gap_ms_p95, 500);
});

test("rolling stream metrics preserve frame age when the reporting window is empty", () => {
    const metrics = new RollingStreamMetrics();
    metrics.record(9, { accepted: true, receivedAtMs: 1000 });

    const camera = metrics.snapshot(12000)["9"];
    assert.equal(camera.accepted_sample_count_10s, 0);
    assert.equal(camera.accepted_fps_10s, 0);
    assert.equal(camera.last_frame_age_ms, 11000);
});
