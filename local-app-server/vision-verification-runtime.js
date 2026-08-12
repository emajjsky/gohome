"use strict";

const DEFAULT_VERIFICATION_DEADLINE_SECONDS = 90;

function safeProviderCode(value) {
    const code = String(value || "").trim().toUpperCase();
    return /^[A-Z0-9_]{2,64}$/.test(code) ? code : "TRANSPORT_ERROR";
}

function compactProviderDetail(value) {
    return String(value || "")
        .replace(/https?:\/\/\S+/gi, "[url]")
        .replace(/sk-[A-Za-z0-9_-]+/g, "[credential]")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 180);
}

function providerFailure(error, response = null) {
    if (response && Number.isFinite(Number(response.status))) {
        const status = Number(response.status);
        const detail = compactProviderDetail(response.detail) || "provider request rejected";
        const failure = new Error(`vision verification failed: ${status} ${detail}`);
        failure.retryable = status === 408 || status === 409 || status === 425 || status === 429 || status >= 500;
        failure.provider_status = status;
        failure.provider_code = "";
        return failure;
    }
    const code = safeProviderCode(error?.cause?.code || error?.code || error?.cause?.name);
    const failure = new Error(`vision verification transport failed [${code}]`);
    failure.retryable = true;
    failure.provider_status = null;
    failure.provider_code = code;
    return failure;
}

function verificationRetryDelaySeconds(attempt) {
    return [5, 15, 30, 60][Math.min(Math.max(1, Number(attempt) || 1) - 1, 3)];
}

function verificationDeadlineAt(startedAt, deadlineSeconds = DEFAULT_VERIFICATION_DEADLINE_SECONDS) {
    const startedMs = Date.parse(String(startedAt || ""));
    const seconds = Number(deadlineSeconds);
    if (!Number.isFinite(startedMs) || !Number.isFinite(seconds) || seconds <= 0) return "";
    return new Date(startedMs + seconds * 1000).toISOString();
}

function verificationDeadlineReached(deadlineAt, nowMs = Date.now()) {
    const deadlineMs = Date.parse(String(deadlineAt || ""));
    return Number.isFinite(deadlineMs) && Number(nowMs) >= deadlineMs;
}

function verificationNextAttemptAt({ attempt, deadlineAt, nowMs = Date.now() }) {
    const deadlineMs = Date.parse(String(deadlineAt || ""));
    const retryMs = Number(nowMs) + verificationRetryDelaySeconds(attempt) * 1000;
    if (!Number.isFinite(deadlineMs) || retryMs >= deadlineMs) return "";
    return new Date(retryMs).toISOString();
}

module.exports = {
    DEFAULT_VERIFICATION_DEADLINE_SECONDS,
    providerFailure,
    verificationDeadlineAt,
    verificationDeadlineReached,
    verificationNextAttemptAt,
    verificationRetryDelaySeconds,
};
