"use strict";

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

module.exports = {
    providerFailure,
    verificationRetryDelaySeconds,
};
