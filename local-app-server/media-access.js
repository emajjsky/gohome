"use strict";

const crypto = require("crypto");

const MEDIA_TOKEN_VERSION = "gohome-media-v1";
const SAFE_PATH_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const PRIVACY_MODES = new Set(["original", "person_blur", "skeleton"]);

class MediaAccessError extends Error {
    constructor(message, statusCode = 403) {
        super(message);
        this.name = "MediaAccessError";
        this.statusCode = statusCode;
    }
}

function sha256(value) {
    return crypto.createHash("sha256").update(String(value || "")).digest("hex");
}

function safeEqual(left, right) {
    const first = Buffer.from(String(left || ""));
    const second = Buffer.from(String(right || ""));
    return first.length === second.length && crypto.timingSafeEqual(first, second);
}

function safePathSegment(value, label) {
    const segment = String(value || "").trim();
    if (!SAFE_PATH_SEGMENT.test(segment)) {
        throw new MediaAccessError(`${label} is invalid`, 400);
    }
    return segment;
}

function normalizeWhepBaseURL(value) {
    const raw = String(value || "").trim().replace(/\/+$/, "");
    if (!raw) return "";
    let parsed;
    try {
        parsed = new URL(raw);
    } catch (_error) {
        throw new MediaAccessError("media WHEP base URL is invalid", 503);
    }
    const loopback = ["127.0.0.1", "::1", "localhost"].includes(parsed.hostname);
    if (parsed.protocol !== "https:" && !(loopback && parsed.protocol === "http:")) {
        throw new MediaAccessError("media WHEP base URL must use HTTPS", 503);
    }
    if (parsed.username || parsed.password || parsed.search || parsed.hash) {
        throw new MediaAccessError("media WHEP base URL must not contain credentials, query, or fragment", 503);
    }
    return raw;
}

function mediaPath(deviceId, cameraId) {
    return `live/${safePathSegment(deviceId, "device ID")}/${safePathSegment(cameraId, "camera ID")}`;
}

function normalizePrivacyMode(value) {
    const mode = String(value || "").trim().toLowerCase();
    if (!PRIVACY_MODES.has(mode)) {
        throw new MediaAccessError("media privacy mode is invalid", 400);
    }
    return mode;
}

function parseMediaPath(value) {
    const match = String(value || "").match(/^live\/([^/]+)\/([^/]+)$/);
    if (!match) throw new MediaAccessError("media path is not allowed", 403);
    return {
        deviceId: safePathSegment(match[1], "device ID"),
        cameraId: safePathSegment(match[2], "camera ID"),
    };
}

class MediaAccessService {
    constructor({
        secret = process.env.GOHOME_MEDIA_AUTH_SECRET || "",
        whepBaseURL = process.env.GOHOME_MEDIA_WHEP_BASE_URL || "",
        readTTLSeconds = Number(process.env.GOHOME_MEDIA_READ_TTL_SECONDS || 120),
        clock = () => Date.now(),
        resolveDeviceTokens = () => [],
        resolveCamera = () => null,
        resolvePrivacyMode = () => "original",
        canUserAccessFamily = () => false,
    } = {}) {
        this.secret = String(secret || "");
        this.whepBaseURL = normalizeWhepBaseURL(whepBaseURL);
        this.readTTLSeconds = Math.max(30, Math.min(300, Number(readTTLSeconds) || 120));
        this.clock = clock;
        this.resolveDeviceTokens = resolveDeviceTokens;
        this.resolveCamera = resolveCamera;
        this.resolvePrivacyMode = resolvePrivacyMode;
        this.canUserAccessFamily = canUserAccessFamily;
    }

    status() {
        return {
            configured: this.secret.length >= 32 && Boolean(this.whepBaseURL),
            transport: "whep-h264-v1",
            composition_owner: "edge",
            read_ttl_seconds: this.readTTLSeconds,
            whep_base_url: this.whepBaseURL,
        };
    }

    issueReadSession({ userId, familyId, deviceId, cameraId, privacyMode: requestedPrivacyMode }) {
        this.assertConfigured();
        const path = mediaPath(deviceId, cameraId);
        const resolvedUserId = String(userId || "");
        const resolvedFamilyId = String(familyId || "");
        const resolvedDeviceId = String(deviceId || "");
        const resolvedCameraId = String(cameraId || "");
        const resolvedPrivacyMode = normalizePrivacyMode(requestedPrivacyMode);
        if (!resolvedUserId || !resolvedFamilyId) {
            throw new MediaAccessError("media session identity is incomplete", 400);
        }
        const camera = this.resolveCamera(resolvedCameraId);
        if (!camera || camera.enabled === false) {
            throw new MediaAccessError("media camera is unavailable", 403);
        }
        if (
            String(camera.device_id || "") !== resolvedDeviceId
            || String(camera.family_id || "") !== resolvedFamilyId
        ) {
            throw new MediaAccessError("media camera ownership does not match session", 403);
        }
        if (!this.canUserAccessFamily(resolvedUserId, resolvedFamilyId)) {
            throw new MediaAccessError("media family access is not allowed", 403);
        }
        if (normalizePrivacyMode(this.resolvePrivacyMode(resolvedFamilyId)) !== resolvedPrivacyMode) {
            throw new MediaAccessError("media privacy mode is not current", 409);
        }
        const nowSeconds = Math.floor(this.clock() / 1000);
        const expiresAtSeconds = nowSeconds + this.readTTLSeconds;
        const claims = {
            version: MEDIA_TOKEN_VERSION,
            token_id: crypto.randomUUID(),
            action: "read",
            path,
            user_id: resolvedUserId,
            family_id: resolvedFamilyId,
            device_id: resolvedDeviceId,
            camera_id: resolvedCameraId,
            privacy_mode: resolvedPrivacyMode,
            issued_at: nowSeconds,
            expires_at: expiresAtSeconds,
        };
        const token = this.sign(claims);
        const encodedPath = path.split("/").map(encodeURIComponent).join("/");
        return {
            session_id: claims.token_id,
            expires_at: new Date(expiresAtSeconds * 1000).toISOString(),
            display_transport: "whep-h264-v1",
            composition_owner: "edge",
            privacy_mode: claims.privacy_mode,
            media_path: path,
            whep_url: `${this.whepBaseURL}/${encodedPath}/whep`,
            authorization: { scheme: "Bearer", token },
        };
    }

    authorize(request = {}) {
        this.assertConfigured();
        const action = String(request.action || "").trim().toLowerCase();
        if (action === "publish") return this.authorizePublish(request);
        if (action === "read") return this.authorizeRead(request);
        throw new MediaAccessError("media action is not allowed", 403);
    }

    authorizePublish(request) {
        if (String(request.protocol || "").toLowerCase() !== "rtsp") {
            throw new MediaAccessError("publish protocol is not allowed", 403);
        }
        const { deviceId, cameraId } = parseMediaPath(request.path);
        const username = String(request.user || "");
        const password = String(request.password || "");
        if (!username || !password) throw new MediaAccessError("media credentials are required", 401);
        if (username !== deviceId) throw new MediaAccessError("media device identity does not match path", 403);

        const passwordHash = sha256(password);
        const token = (this.resolveDeviceTokens(deviceId) || []).find((record) => {
            if (String(record?.status || "") !== "active") return false;
            if (String(record?.device_id || "") !== deviceId) return false;
            const expectedHash = String(record?.token_hash || "") || sha256(record?.token || "");
            return expectedHash.length === passwordHash.length && safeEqual(expectedHash, passwordHash);
        });
        if (!token) throw new MediaAccessError("media device credentials are invalid", 401);

        const camera = this.resolveCamera(cameraId);
        if (!camera || camera.enabled === false) throw new MediaAccessError("media camera is unavailable", 403);
        if (String(camera.device_id || "") !== deviceId) {
            throw new MediaAccessError("media camera does not belong to device", 403);
        }
        if (String(camera.family_id || "") !== String(token.family_id || "")) {
            throw new MediaAccessError("media camera family does not match device binding", 403);
        }
        return { action: "publish", path: request.path, device_id: deviceId, camera_id: cameraId };
    }

    authorizeRead(request) {
        if (String(request.protocol || "").toLowerCase() !== "webrtc") {
            throw new MediaAccessError("read protocol is not allowed", 403);
        }
        const token = String(request.token || request.password || "").trim();
        if (!token) throw new MediaAccessError("media token is required", 401);
        const claims = this.verify(token);
        const { deviceId, cameraId } = parseMediaPath(request.path);
        if (claims.action !== "read" || claims.path !== request.path) {
            throw new MediaAccessError("media token does not allow this path", 403);
        }
        if (claims.device_id !== deviceId || claims.camera_id !== cameraId) {
            throw new MediaAccessError("media token identity does not match path", 403);
        }
        const camera = this.resolveCamera(cameraId);
        if (!camera || camera.enabled === false) throw new MediaAccessError("media camera is unavailable", 403);
        if (
            String(camera.device_id || "") !== claims.device_id
            || String(camera.family_id || "") !== claims.family_id
        ) {
            throw new MediaAccessError("media camera ownership changed", 403);
        }
        if (!this.canUserAccessFamily(claims.user_id, claims.family_id)) {
            throw new MediaAccessError("media family access was revoked", 403);
        }
        if (normalizePrivacyMode(this.resolvePrivacyMode(claims.family_id)) !== claims.privacy_mode) {
            throw new MediaAccessError("media privacy mode changed", 403);
        }
        return {
            action: "read",
            path: request.path,
            user_id: claims.user_id,
            family_id: claims.family_id,
            device_id: deviceId,
            camera_id: cameraId,
        };
    }

    sign(claims) {
        this.assertConfigured();
        const payload = Buffer.from(JSON.stringify(claims)).toString("base64url");
        const signature = crypto.createHmac("sha256", this.secret).update(payload).digest("base64url");
        return `m1.${payload}.${signature}`;
    }

    verify(token) {
        this.assertConfigured();
        const parts = String(token || "").split(".");
        if (parts.length !== 3 || parts[0] !== "m1" || parts[1].length > 4096) {
            throw new MediaAccessError("media token is invalid", 401);
        }
        const expected = crypto.createHmac("sha256", this.secret).update(parts[1]).digest("base64url");
        if (!safeEqual(parts[2], expected)) throw new MediaAccessError("media token is invalid", 401);
        let claims;
        try {
            claims = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
        } catch (_error) {
            throw new MediaAccessError("media token is invalid", 401);
        }
        const nowSeconds = Math.floor(this.clock() / 1000);
        if (
            claims.version !== MEDIA_TOKEN_VERSION
            || !claims.token_id
            || !Number.isInteger(claims.issued_at)
            || !Number.isInteger(claims.expires_at)
            || claims.issued_at > nowSeconds + 5
            || claims.expires_at <= nowSeconds
            || claims.expires_at - claims.issued_at > 300
        ) {
            throw new MediaAccessError("media token expired or malformed", 401);
        }
        return claims;
    }

    assertConfigured() {
        if (this.secret.length < 32 || !this.whepBaseURL) {
            throw new MediaAccessError("media access service is not configured", 503);
        }
    }
}

module.exports = {
    MEDIA_TOKEN_VERSION,
    MediaAccessError,
    MediaAccessService,
    mediaPath,
    normalizePrivacyMode,
    safeEqual,
};
