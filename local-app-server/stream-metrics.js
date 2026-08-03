"use strict";

function percentile(values, ratio) {
    if (!values.length) return 0;
    const sorted = [...values].sort((first, second) => first - second);
    const index = Math.min(sorted.length - 1, Math.max(0, Math.floor((sorted.length - 1) * ratio)));
    return sorted[index];
}

function intervalRate(timestamps) {
    if (timestamps.length < 2) return 0;
    const elapsedMs = timestamps[timestamps.length - 1] - timestamps[0];
    if (elapsedMs <= 0) return 0;
    return ((timestamps.length - 1) * 1000) / elapsedMs;
}

class RollingStreamMetrics {
    constructor({ retentionMs = 60000, windowMs = 10000 } = {}) {
        this.retentionMs = Math.max(1000, Number(retentionMs) || 60000);
        this.windowMs = Math.max(1000, Number(windowMs) || 10000);
        this.cameras = new Map();
    }

    record(cameraId, { accepted, capturedAt, receivedAtMs = Date.now() }) {
        const receivedAt = Number(receivedAtMs);
        if (!Number.isFinite(receivedAt)) throw new TypeError("receivedAtMs must be finite");
        const metric = this.#camera(cameraId);
        this.#prune(metric, receivedAt);
        if (!accepted) {
            metric.staleRejections += 1;
            return;
        }

        metric.acceptedAtMs.push(receivedAt);
        metric.lastReceivedAt = new Date(receivedAt).toISOString();
        const capturedAtMs = Date.parse(capturedAt || "");
        if (Number.isFinite(capturedAtMs)) {
            metric.transportLatency.push({
                at: receivedAt,
                value: Math.max(0, receivedAt - capturedAtMs),
            });
        }
    }

    snapshot(nowMs = Date.now()) {
        const now = Number(nowMs);
        if (!Number.isFinite(now)) throw new TypeError("nowMs must be finite");
        const result = {};
        for (const [cameraId, metric] of this.cameras.entries()) {
            this.#prune(metric, now);
            const cutoff = now - this.windowMs;
            const recent = metric.acceptedAtMs.filter((timestamp) => timestamp >= cutoff && timestamp <= now);
            const gaps = recent.slice(1).map((timestamp, index) => timestamp - recent[index]);
            const latencies = metric.transportLatency
                .filter((sample) => sample.at >= cutoff && sample.at <= now)
                .map((sample) => sample.value);
            const lastAcceptedAt = metric.acceptedAtMs.at(-1);
            result[cameraId] = {
                accepted_fps_10s: Number(intervalRate(recent).toFixed(2)),
                accepted_sample_count_10s: recent.length,
                frame_gap_ms_p95: Number(percentile(gaps, 0.95).toFixed(2)),
                frame_gap_ms_max: Number((gaps.length ? Math.max(...gaps) : 0).toFixed(2)),
                transport_latency_ms_p95: Number(percentile(latencies, 0.95).toFixed(2)),
                transport_latency_ms_max: Number((latencies.length ? Math.max(...latencies) : 0).toFixed(2)),
                last_frame_age_ms: Number((lastAcceptedAt === undefined ? 0 : Math.max(0, now - lastAcceptedAt)).toFixed(2)),
                stale_rejections: metric.staleRejections,
                last_received_at: metric.lastReceivedAt,
            };
        }
        return result;
    }

    #camera(cameraId) {
        const key = String(cameraId);
        if (!this.cameras.has(key)) {
            this.cameras.set(key, {
                acceptedAtMs: [],
                transportLatency: [],
                staleRejections: 0,
                lastReceivedAt: "",
            });
        }
        return this.cameras.get(key);
    }

    #prune(metric, now) {
        const cutoff = now - this.retentionMs;
        while (metric.acceptedAtMs.length && metric.acceptedAtMs[0] < cutoff) metric.acceptedAtMs.shift();
        while (metric.transportLatency.length && metric.transportLatency[0].at < cutoff) {
            metric.transportLatency.shift();
        }
    }
}

module.exports = {
    RollingStreamMetrics,
    intervalRate,
    percentile,
};
