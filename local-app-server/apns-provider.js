"use strict";

const crypto = require("crypto");
const fs = require("fs");
const http2 = require("http2");

class ApnsError extends Error {
    constructor(message, { statusCode = 0, reason = "", retryable = false, apnsId = "" } = {}) {
        super(message);
        this.name = "ApnsError";
        this.statusCode = statusCode;
        this.reason = reason;
        this.retryable = retryable;
        this.apnsId = apnsId;
    }
}

function base64url(value) {
    return Buffer.from(value).toString("base64url");
}

function encryptionKey(value) {
    const raw = String(value || "").trim();
    if (/^[0-9a-f]{64}$/i.test(raw)) return Buffer.from(raw, "hex");
    try {
        const decoded = Buffer.from(raw, "base64");
        return decoded.length === 32 ? decoded : null;
    } catch (_error) {
        return null;
    }
}

function readPrivateKey(options) {
    const inline = String(options.authKey || process.env.GOHOME_APNS_AUTH_KEY || "").trim();
    if (inline) return inline.replace(/\\n/g, "\n");
    const keyPath = String(options.authKeyPath || process.env.GOHOME_APNS_AUTH_KEY_PATH || "").trim();
    return keyPath && fs.existsSync(keyPath) ? fs.readFileSync(keyPath, "utf8") : "";
}

function createPersistentHttp2Requester(options = {}) {
    const connect = options.connect || http2.connect;
    const sessions = new Map();

    function discard(authority, client) {
        if (sessions.get(authority) === client) sessions.delete(authority);
        if (!client.destroyed) client.destroy();
    }

    function session(authority) {
        const existing = sessions.get(authority);
        if (existing && !existing.closed && !existing.destroyed) return existing;
        const client = connect(authority);
        sessions.set(authority, client);
        const retire = () => {
            if (sessions.get(authority) === client) sessions.delete(authority);
        };
        client.once("close", retire);
        client.once("goaway", retire);
        client.on("error", retire);
        return client;
    }

    const request = ({ authority, headers, body, timeoutMs = 8000 }) => new Promise((resolve, reject) => {
        const client = session(authority);
        let stream;
        try {
            stream = client.request(headers);
        } catch (error) {
            discard(authority, client);
            reject(error);
            return;
        }
        const chunks = [];
        let responseHeaders = {};
        let settled = false;
        const timeout = setTimeout(() => {
            fail(new Error(`APNs request timed out after ${timeoutMs}ms`));
        }, Math.max(1000, Number(timeoutMs) || 8000));
        const fail = (error) => {
            if (settled) return;
            settled = true;
            clearTimeout(timeout);
            discard(authority, client);
            reject(error);
        };
        stream.setEncoding("utf8");
        stream.on("response", (value) => { responseHeaders = value; });
        stream.on("data", (chunk) => chunks.push(chunk));
        stream.on("end", () => {
            if (settled) return;
            settled = true;
            clearTimeout(timeout);
            resolve({ headers: responseHeaders, body: chunks.join("") });
        });
        stream.on("error", fail);
        stream.end(body);
    });

    request.close = () => {
        for (const client of sessions.values()) {
            if (!client.destroyed) client.close();
        }
        sessions.clear();
    };
    return request;
}

function createApnsProvider(options = {}) {
    const providerName = String(options.provider || process.env.GOHOME_PUSH_PROVIDER || "").trim().toLowerCase();
    const teamId = String(options.teamId || process.env.GOHOME_APNS_TEAM_ID || "").trim();
    const keyId = String(options.keyId || process.env.GOHOME_APNS_KEY_ID || "").trim();
    const topic = String(options.topic || process.env.GOHOME_APNS_TOPIC || "com.gohome.family").trim();
    const privateKey = readPrivateKey(options);
    const tokenKey = encryptionKey(options.tokenEncryptionKey || process.env.GOHOME_PUSH_TOKEN_ENCRYPTION_KEY);
    const requestTimeoutMs = Math.max(1000, Number(options.requestTimeoutMs || process.env.GOHOME_APNS_REQUEST_TIMEOUT_MS || 8000));
    const request = options.request || createPersistentHttp2Requester();
    const configured = providerName === "apns" && Boolean(teamId && keyId && topic && privateKey && tokenKey);
    let cachedJwt = "";
    let cachedJwtAt = 0;

    function requireConfigured() {
        if (!configured) throw new Error("APNs provider is not fully configured");
    }

    function jwt() {
        requireConfigured();
        const issuedAt = Math.floor(Date.now() / 1000);
        if (cachedJwt && issuedAt - cachedJwtAt < 50 * 60) return cachedJwt;
        const header = base64url(JSON.stringify({ alg: "ES256", kid: keyId }));
        const claims = base64url(JSON.stringify({ iss: teamId, iat: issuedAt }));
        const signingInput = `${header}.${claims}`;
        const signature = crypto.sign("sha256", Buffer.from(signingInput), {
            key: privateKey,
            dsaEncoding: "ieee-p1363",
        });
        cachedJwt = `${signingInput}.${base64url(signature)}`;
        cachedJwtAt = issuedAt;
        return cachedJwt;
    }

    function encryptToken(token) {
        requireConfigured();
        const normalized = String(token || "").trim().toLowerCase();
        if (!/^[0-9a-f]{64,}$/.test(normalized)) throw new Error("invalid APNs device token");
        const iv = crypto.randomBytes(12);
        const cipher = crypto.createCipheriv("aes-256-gcm", tokenKey, iv);
        const ciphertext = Buffer.concat([cipher.update(normalized, "utf8"), cipher.final()]);
        return ["v1", iv.toString("base64url"), cipher.getAuthTag().toString("base64url"), ciphertext.toString("base64url")].join(":");
    }

    function decryptToken(value) {
        requireConfigured();
        const [version, rawIv, rawTag, rawCiphertext] = String(value || "").split(":");
        if (version !== "v1" || !rawIv || !rawTag || !rawCiphertext) throw new Error("invalid encrypted push token");
        const decipher = crypto.createDecipheriv("aes-256-gcm", tokenKey, Buffer.from(rawIv, "base64url"));
        decipher.setAuthTag(Buffer.from(rawTag, "base64url"));
        return Buffer.concat([
            decipher.update(Buffer.from(rawCiphertext, "base64url")),
            decipher.final(),
        ]).toString("utf8");
    }

    async function send({ tokenCiphertext, environment = "production", payload, apnsId = crypto.randomUUID(), priority = 10 }) {
        requireConfigured();
        const deviceToken = decryptToken(tokenCiphertext);
        const sandbox = String(environment).toLowerCase() === "sandbox";
        const authority = sandbox ? "https://api.sandbox.push.apple.com" : "https://api.push.apple.com";
        let response;
        try {
            response = await request({
                authority,
                headers: {
                    ":method": "POST",
                    ":path": `/3/device/${deviceToken}`,
                    authorization: `bearer ${jwt()}`,
                    "apns-id": apnsId,
                    "apns-topic": topic,
                    "apns-push-type": "alert",
                    "apns-priority": String(priority),
                },
                body: JSON.stringify(payload),
                timeoutMs: requestTimeoutMs,
            });
        } catch (error) {
            throw new ApnsError(error.message || "APNs network request failed", { retryable: true, apnsId });
        }
        const statusCode = Number(response.headers?.[":status"] || 0);
        let details = {};
        try { details = response.body ? JSON.parse(response.body) : {}; } catch (_error) {}
        if (statusCode === 200) {
            return { statusCode, apnsId: String(response.headers?.["apns-id"] || apnsId), reason: "" };
        }
        const reason = String(details.reason || "APNsRejected");
        throw new ApnsError(`APNs rejected notification: ${reason}`, {
            statusCode,
            reason,
            retryable: statusCode === 429 || statusCode >= 500,
            apnsId: String(response.headers?.["apns-id"] || apnsId),
        });
    }

    return { configured, encryptToken, decryptToken, send, close: () => request.close?.() };
}

module.exports = { ApnsError, createApnsProvider, createPersistentHttp2Requester };
