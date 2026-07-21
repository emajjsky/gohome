"use strict";

const crypto = require("crypto");

class AuthPolicyError extends Error {
    constructor(message, statusCode = 401) {
        super(message);
        this.name = "AuthPolicyError";
        this.statusCode = statusCode;
    }
}

function normalizePhone(value) {
    const digits = String(value || "").replace(/\D/g, "");
    if (/^1\d{10}$/.test(digits)) return digits;
    if (/^861\d{10}$/.test(digits)) return digits.slice(2);
    return "";
}

function hashChallenge(secret, challengeId, phone, code) {
    return crypto
        .createHash("sha256")
        .update(`${secret}:${challengeId}:${phone}:${code}`)
        .digest("hex");
}

function safeEqual(left, right) {
    const a = Buffer.from(String(left || ""));
    const b = Buffer.from(String(right || ""));
    return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function randomCode() {
    return String(crypto.randomInt(0, 1000000)).padStart(6, "0");
}

class AuthService {
    constructor({
        mode = process.env.GOHOME_AUTH_MODE || "production",
        demoOtp = process.env.GOHOME_DEMO_OTP || "",
        secret = process.env.GOHOME_AUTH_SECRET || "",
        smsProvider = null,
        clock = () => Date.now(),
        challengeTtlMs = 5 * 60 * 1000,
        requestWindowMs = 60 * 1000,
        maxRequestsPerWindow = 3,
        maxAttempts = 5,
    } = {}) {
        this.mode = String(mode || "production").trim().toLowerCase();
        this.demoOtp = String(demoOtp || "");
        this.secret = String(secret || "");
        this.smsProvider = smsProvider;
        this.clock = clock;
        this.challengeTtlMs = challengeTtlMs;
        this.requestWindowMs = requestWindowMs;
        this.maxRequestsPerWindow = maxRequestsPerWindow;
        this.maxAttempts = maxAttempts;
        this.challenges = new Map();
        this.requests = new Map();
    }

    assertPhone(phone) {
        const normalized = normalizePhone(phone);
        if (!normalized) throw new AuthPolicyError("手机号格式不正确", 400);
        return normalized;
    }

    assertConfigured() {
        if (this.mode === "demo") {
            if (!/^\d{6}$/.test(this.demoOtp)) {
                throw new AuthPolicyError("演示验证码未配置", 503);
            }
            return;
        }
        if (!this.secret) throw new AuthPolicyError("短信验证服务未配置", 503);
        if (typeof this.smsProvider !== "function") throw new AuthPolicyError("短信验证服务未配置", 503);
    }

    enforceRequestRate(phone) {
        const now = this.clock();
        const recent = (this.requests.get(phone) || []).filter((timestamp) => now - timestamp < this.requestWindowMs);
        if (recent.length >= this.maxRequestsPerWindow) throw new AuthPolicyError("验证码请求过于频繁，请稍后再试", 429);
        recent.push(now);
        this.requests.set(phone, recent);
    }

    async requestCode(phone) {
        const normalized = this.assertPhone(phone);
        this.assertConfigured();
        this.clearExpired();
        this.enforceRequestRate(normalized);
        const challengeId = `otp_${crypto.randomBytes(18).toString("hex")}`;
        const code = this.mode === "demo" ? this.demoOtp : randomCode();
        const expiresAt = this.clock() + this.challengeTtlMs;
        this.challenges.set(challengeId, {
            challenge_id: challengeId,
            phone: normalized,
            code_hash: hashChallenge(this.secret || "demo", challengeId, normalized, code),
            expires_at: expiresAt,
            attempts: 0,
            consumed_at: null,
        });
        if (this.mode !== "demo") {
            try {
                await this.smsProvider({ phone: normalized, code, challengeId, expiresAt });
            } catch (error) {
                this.challenges.delete(challengeId);
                throw new AuthPolicyError("验证码发送失败，请稍后再试", Number(error?.statusCode) || 503);
            }
        }
        return {
            challenge_id: challengeId,
            expires_at: new Date(expiresAt).toISOString(),
            delivery: this.mode === "demo" ? "demo" : "sms",
        };
    }

    verifyCode(phone, code, challengeId = "") {
        const normalized = this.assertPhone(phone);
        const providedCode = String(code || "");
        if (this.mode === "demo") {
            if (!/^\d{6}$/.test(this.demoOtp) || !safeEqual(providedCode, this.demoOtp)) {
                throw new AuthPolicyError("验证码不正确", 401);
            }
            return { phone: normalized, mode: "demo" };
        }
        const challenge = this.challenges.get(String(challengeId || ""));
        const now = this.clock();
        if (!challenge || challenge.phone !== normalized || challenge.consumed_at || challenge.expires_at <= now) {
            throw new AuthPolicyError("验证码已失效，请重新获取", 401);
        }
        challenge.attempts += 1;
        const expectedHash = hashChallenge(this.secret, challenge.challenge_id, normalized, providedCode);
        if (!safeEqual(expectedHash, challenge.code_hash)) {
            if (challenge.attempts >= this.maxAttempts) {
                challenge.consumed_at = now;
                throw new AuthPolicyError("验证码尝试次数过多，请重新获取", 429);
            }
            throw new AuthPolicyError("验证码不正确", 401);
        }
        challenge.consumed_at = now;
        return { phone: normalized, mode: "production" };
    }

    clearExpired() {
        const now = this.clock();
        for (const [id, challenge] of this.challenges) {
            if (challenge.expires_at <= now || challenge.consumed_at) this.challenges.delete(id);
        }
    }
}

module.exports = { AuthPolicyError, AuthService, normalizePhone };
