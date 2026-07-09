(function () {
    const DEFAULT_EDGE_BASE = "http://127.0.0.1:8711";
    const EDGE_KEY = "gohome.edgeApiBase";
    const AUTH_TOKEN_KEY = "gohome.authToken";
    const APP_SHELL_KEY = "gohome.appShellMode";
    const playbackSessionCache = new Map();
    const nativeBridgeRequests = new Map();

    function normalizeBase(value) {
        return String(value || "").replace(/\/$/, "");
    }

    function requestedBase() {
        const params = new URLSearchParams(window.location.search);
        return normalizeBase(params.get("edge") || localStorage.getItem(EDGE_KEY));
    }

    function defaultBase() {
        if (window.location.protocol.startsWith("http") && window.location.port === "8711") {
            return "";
        }
        return DEFAULT_EDGE_BASE;
    }

    function getAuthToken() {
        return localStorage.getItem(AUTH_TOKEN_KEY) || "";
    }

    function setAuthToken(token) {
        if (!token) {
            localStorage.removeItem(AUTH_TOKEN_KEY);
            playbackSessionCache.clear();
            return "";
        }
        localStorage.setItem(AUTH_TOKEN_KEY, String(token));
        playbackSessionCache.clear();
        return String(token);
    }

    function clearAuthToken() {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        playbackSessionCache.clear();
    }

    function isDeviceAccessError(error) {
        const detail = String(error?.message || "").trim();
        return Number(error?.status || 0) === 403 && /do not have access to this device/i.test(detail);
    }

    async function withDeviceAccessFallback(primary, fallback) {
        try {
            return await primary();
        } catch (error) {
            if (!isDeviceAccessError(error) || typeof fallback !== "function") {
                throw error;
            }
            return fallback();
        }
    }

    function safeLocalPath(value, fallback = "") {
        const raw = String(value || "").trim();
        if (!raw) return fallback;
        if (/^(https?:)?\/\//i.test(raw) || /^[a-z]+:/i.test(raw)) return fallback;
        return raw.replace(/^\/+/, "");
    }

    function currentPagePath() {
        const page = window.location.pathname.split("/").pop() || "index.html";
        return `${page}${window.location.search}${window.location.hash}`;
    }

    function isAppShellMode() {
        const params = new URLSearchParams(window.location.search);
        const current = params.get("app");
        if (current === "1") {
            localStorage.setItem(APP_SHELL_KEY, "1");
            return true;
        }
        if (current === "0") {
            localStorage.removeItem(APP_SHELL_KEY);
            return false;
        }
        return localStorage.getItem(APP_SHELL_KEY) === "1";
    }

    function pageHref(path, options = {}) {
        const targetPath = safeLocalPath(path, "index.html");
        const url = new URL(targetPath, window.location.href);
        const appMode = options.app;
        const nextPath = safeLocalPath(options.next, "");
        if (appMode === true || (appMode !== false && isAppShellMode())) {
            url.searchParams.set("app", "1");
        } else {
            url.searchParams.delete("app");
        }
        if (nextPath) {
            url.searchParams.set("next", nextPath);
        } else if (options.clearNext) {
            url.searchParams.delete("next");
        }
        const page = url.pathname.split("/").pop() || targetPath;
        return `${page}${url.search}${url.hash}`;
    }

    function loginHref(next = currentPagePath()) {
        return pageHref("login.html", { next });
    }

    function redirectTarget(defaultPath = "index.html") {
        const params = new URLSearchParams(window.location.search);
        return safeLocalPath(params.get("next"), defaultPath);
    }

    function bootstrapLaunchState() {
        const url = new URL(window.location.href);
        const params = url.searchParams;
        const edge = normalizeBase(params.get("edge") || "");
        const authToken = params.get("auth_token") || params.get("authToken") || "";
        const app = params.get("app");
        let changed = false;

        if (edge) {
            localStorage.setItem(EDGE_KEY, edge);
            params.delete("edge");
            changed = true;
        }
        if (authToken) {
            setAuthToken(authToken);
            params.delete("auth_token");
            params.delete("authToken");
            changed = true;
        }
        if (app === "1") {
            localStorage.setItem(APP_SHELL_KEY, "1");
        } else if (app === "0") {
            localStorage.removeItem(APP_SHELL_KEY);
            changed = true;
        }

        if (changed) {
            const nextUrl = `${url.pathname}${params.toString() ? `?${params.toString()}` : ""}${url.hash}`;
            window.history.replaceState({}, "", nextUrl);
        }

        return {
            edge,
            authenticated: Boolean(getAuthToken()),
            app: isAppShellMode(),
            next: redirectTarget("index.html"),
        };
    }

    function buildHeaders(extraHeaders = {}) {
        const token = getAuthToken();
        return {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...extraHeaders,
        };
    }

    async function request(path, options = {}) {
        const base = GoHomeEdge.apiBase;
        const response = await fetch(`${base}${path}`, {
            headers: buildHeaders(options.headers || {}),
            ...options,
        });
        const text = await response.text();
        const data = text ? JSON.parse(text) : null;
        if (!response.ok) {
            const error = new Error(data?.detail || `HTTP ${response.status}`);
            error.status = response.status;
            throw error;
        }
        return data;
    }

    async function connect() {
        const candidates = [];
        const requested = requestedBase();
        const isLocalAppOrigin = window.location.protocol.startsWith("http")
            && ["127.0.0.1", "localhost", "::1"].includes(window.location.hostname)
            && window.location.port === "8788";
        if (isLocalAppOrigin) candidates.push("");
        if (requested) candidates.push(requested);
        if (window.location.protocol.startsWith("http")) candidates.push("");
        candidates.push(defaultBase());
        if (window.location.hostname && window.location.hostname !== "127.0.0.1") {
            candidates.push(`http://${window.location.hostname}:8711`);
        }

        const unique = [...new Set(candidates.map(normalizeBase))];
        for (const base of unique) {
            try {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 1800);
                const response = await fetch(`${base}/health`, { signal: controller.signal });
                clearTimeout(timer);
                if (response.ok) {
                    const payload = await response.json();
                    GoHomeEdge.apiBase = base;
                    if (base) localStorage.setItem(EDGE_KEY, base);
                    if (payload?.local_app_demo_token && getAuthToken() === payload.local_app_demo_token) {
                        clearAuthToken();
                    }
                    return payload;
                }
            } catch (_error) {
                // Try the next candidate.
            }
        }
        throw new Error("本机守护服务未连接");
    }

    function edgeUrl(path) {
        if (!path) return "";
        if (/^https?:\/\//.test(path)) return path;
        return `${GoHomeEdge.apiBase}${path.startsWith("/") ? path : `/${path}`}`;
    }

    function streamUrl(cameraId, options = {}) {
        return buildStreamUrl(cameraId, `/api/cameras/${cameraId}/stream.mjpg`, options);
    }

    function appStreamUrl(cameraId, options = {}) {
        return buildStreamUrl(cameraId, `/api/app/cameras/${cameraId}/stream.mjpg`, options);
    }

    function v1VideoStreamUrl(cameraId, options = {}) {
        return buildStreamUrl(cameraId, `/api/v1/video/cameras/${cameraId}/stream.mjpg`, options);
    }

    function buildStreamUrl(cameraId, path, options = {}) {
        if (!cameraId) return "";
        const token = getAuthToken();
        const profile = options.profile || "default";
        const config = { ...options };
        const params = new URLSearchParams();
        params.set("profile", profile);
        Object.entries(config).forEach(([key, value]) => {
            if (key !== "profile" && value !== null && value !== undefined && value !== "") {
                params.set(key, String(value));
            }
        });
        if (path.startsWith("/api/app/") && token) {
            params.set("access_token", token);
        }
        params.set("t", String(Date.now()));
        return edgeUrl(`${path}?${params.toString()}`);
    }

    function mediaUrl(path) {
        return edgeUrl(path);
    }

    function normalizeSnapshotPath(path) {
        const value = String(path || "").trim();
        if (!value) return "";
        if (value.startsWith("/api/app/media/snapshots/")) return value.slice("/api/app/media/snapshots/".length);
        if (value.startsWith("/api/v1/video/media/snapshots/")) return value.slice("/api/v1/video/media/snapshots/".length);
        if (value.startsWith("/snapshots/")) return value.slice("/snapshots/".length);
        return value.replace(/^\/+/, "");
    }

    function playbackSessionKey(payload) {
        return JSON.stringify({
            resource_type: payload.resource_type,
            camera_id: payload.camera_id || null,
            snapshot_path: payload.snapshot_path || "",
            asset_id: payload.asset_id || null,
        });
    }

    function playbackSessionValid(entry) {
        if (!entry?.expiresAt || !entry?.ticket) return false;
        return Date.parse(entry.expiresAt) - Date.now() > 15000;
    }

    async function createPlaybackSession(payload, { forceRefresh = false } = {}) {
        return createPlaybackSessionAt("/api/app/playback-sessions", payload, { forceRefresh });
    }

    async function createV1VideoSession(payload, { forceRefresh = false } = {}) {
        return createPlaybackSessionAt("/api/v1/video/sessions", payload, { forceRefresh });
    }

    async function createPlaybackSessionAt(path, payload, { forceRefresh = false } = {}) {
        const key = playbackSessionKey(payload);
        const cached = playbackSessionCache.get(key);
        if (!forceRefresh && playbackSessionValid(cached)) {
            return { ticket: cached.ticket, expires_at: cached.expiresAt };
        }
        const data = await request(path, {
            method: "POST",
            body: JSON.stringify(payload),
        });
        playbackSessionCache.set(key, {
            ticket: data.ticket,
            expiresAt: data.expires_at,
        });
        return data;
    }

    function appMediaUrl(path) {
        if (!path) return "";
        const token = getAuthToken();
        const withToken = (value) => {
            const url = new URL(edgeUrl(value), window.location.href);
            if (token) url.searchParams.set("access_token", token);
            return url.toString();
        };
        if (/^https?:\/\//.test(path)) return path;
        if (path.startsWith("/api/app/media/")) return withToken(path);
        if (path.startsWith("/snapshots/")) return withToken(`/api/app/media${path}`);
        return withToken(`/api/app/media/snapshots/${String(path).replace(/^\/+/, "")}`);
    }

    function latestSnapshotSuffix(options = {}) {
        const params = new URLSearchParams();
        if (options.allowMissing) params.set("allow_missing", "1");
        const query = params.toString();
        return query ? `?${query}` : "";
    }

    function appLatestSnapshot(cameraId, options = {}) {
        const suffix = latestSnapshotSuffix(options);
        return withDeviceAccessFallback(
            () => request(`/api/app/cameras/${cameraId}/snapshot/latest${suffix}`),
            () => request(`/api/cameras/${cameraId}/snapshot/latest${suffix}`)
        );
    }

    async function appStreamPlaybackUrl(cameraId, options = {}) {
        return videoStreamPlaybackUrl("/api/app/playback-sessions", `/api/app/cameras/${cameraId}/stream.mjpg`, cameraId, options);
    }

    async function v1VideoStreamPlaybackUrl(cameraId, options = {}) {
        return videoStreamPlaybackUrl("/api/v1/video/sessions", `/api/v1/video/cameras/${cameraId}/stream.mjpg`, cameraId, options);
    }

    function isNarrowViewport() {
        if (window.matchMedia) return window.matchMedia("(max-width: 768px)").matches;
        return window.innerWidth <= 768;
    }

    function preferredVideoProfile(options = {}) {
        if (options.profile) return String(options.profile);
        const scene = String(options.scene || "").trim();
        if (scene === "detection") return "detail";
        if (scene === "monitor") return "monitor";
        if (scene === "watch") return isNarrowViewport() ? "mobile" : "monitor";
        if (options.preferDetail) return "detail";
        if (options.preferMonitor) return "monitor";
        return isNarrowViewport() ? "mobile" : "monitor";
    }

    function managedVideoStreamOptions(options = {}) {
        return {
            profile: preferredVideoProfile(options),
            refreshMs: Math.max(30000, Number(options.refreshMs || 90000)),
            retryMs: Math.max(1500, Number(options.retryMs || 3000)),
        };
    }

    async function videoStreamPlaybackUrl(sessionPath, streamPath, cameraId, options = {}) {
        if (!cameraId) return "";
        const profile = options.profile || "default";
        const config = { ...options };
        const session = await createPlaybackSessionAt(sessionPath, {
            resource_type: "stream",
            camera_id: Number(cameraId),
            expires_in_seconds: 120,
        });
        const params = new URLSearchParams();
        params.set("profile", profile);
        Object.entries(config).forEach(([key, value]) => {
            if (key !== "profile" && value !== null && value !== undefined && value !== "") {
                params.set(key, String(value));
            }
        });
        params.set("playback_ticket", session.ticket);
        params.set("t", String(Date.now()));
        return edgeUrl(`${streamPath}?${params.toString()}`);
    }

    async function appMediaPlaybackUrl(path) {
        return videoMediaPlaybackUrl("/api/app/playback-sessions", "/api/app/media/snapshots", path);
    }

    async function v1VideoMediaPlaybackUrl(path) {
        return videoMediaPlaybackUrl("/api/v1/video/sessions", "/api/v1/video/media/snapshots", path);
    }

    async function v1VideoAssetPlaybackUrl(assetId) {
        if (!assetId) return "";
        const session = await createPlaybackSessionAt("/api/v1/video/sessions", {
            resource_type: "asset",
            asset_id: Number(assetId),
            expires_in_seconds: 120,
        });
        const url = new URL(edgeUrl(`/api/v1/video/assets/${assetId}`), window.location.href);
        url.searchParams.set("playback_ticket", session.ticket);
        url.searchParams.set("t", String(Date.now()));
        return url.toString();
    }

    function createManagedVideoStream(image, options = {}) {
        let cameraId = options.cameraId ? Number(options.cameraId) : null;
        let resolved = managedVideoStreamOptions(options);
        let profile = resolved.profile;
        let refreshMs = resolved.refreshMs;
        let retryMs = resolved.retryMs;
        let snapshotOnly = Boolean(options.snapshotOnly);
        let snapshotRefreshMs = Math.max(2500, Number(options.snapshotRefreshMs || 3000));
        let lastSnapshotPath = "";
        let lastSnapshotPayload = null;
        let disposed = false;
        let refreshTimer = null;
        let retryTimer = null;
        let frameCheckTimer = null;
        let onStateChange = typeof options.onStateChange === "function" ? options.onStateChange : () => {};

        function clearTimers() {
            if (refreshTimer) {
                clearTimeout(refreshTimer);
                refreshTimer = null;
            }
            if (retryTimer) {
                clearTimeout(retryTimer);
                retryTimer = null;
            }
            if (frameCheckTimer) {
                clearTimeout(frameCheckTimer);
                frameCheckTimer = null;
            }
        }

        function imageHasFrame() {
            return image && image.naturalWidth > 0 && image.naturalHeight > 0;
        }

        function loadImageWithoutBlanking(url) {
            return new Promise((resolve) => {
                const probe = new Image();
                probe.onload = () => {
                    if (!disposed && image) image.src = url;
                    resolve(true);
                };
                probe.onerror = () => resolve(false);
                probe.src = url;
            });
        }

        async function refreshSnapshotOnly() {
            clearTimers();
            if (disposed || !image || !cameraId) return;
            try {
                const snapshot = await appLatestSnapshot(cameraId, { allowMissing: true });
                if (disposed || !image || !cameraId) return;
                const snapshotPath = snapshot?.image_url || snapshot?.snapshot_path || "";
                if (snapshot?.available === false || !snapshotPath) {
                    if (!imageHasFrame()) onStateChange("waiting");
                    retryTimer = setTimeout(refreshSnapshotOnly, Math.max(Math.min(retryMs, 3000), 2500));
                    return;
                }
                const nextUrl = appMediaUrl(snapshotPath);
                const pathChanged = snapshotPath !== lastSnapshotPath;
                if (pathChanged) {
                    const loaded = await loadImageWithoutBlanking(nextUrl);
                    if (!loaded) {
                        if (!imageHasFrame()) onStateChange("waiting");
                        retryTimer = setTimeout(refreshSnapshotOnly, Math.max(Math.min(retryMs, 3000), 2500));
                        return;
                    }
                    lastSnapshotPath = snapshotPath;
                }
                lastSnapshotPayload = snapshot;
                onStateChange("snapshot", snapshot);
                refreshTimer = setTimeout(refreshSnapshotOnly, snapshotRefreshMs);
            } catch (error) {
                if (!imageHasFrame()) onStateChange("waiting", error);
                retryTimer = setTimeout(refreshSnapshotOnly, Math.max(Math.min(retryMs, 3000), 2500));
            }
        }

        async function refresh() {
            clearTimers();
            if (disposed || !image || !cameraId) return;
            if (snapshotOnly) {
                await refreshSnapshotOnly();
                return;
            }
            onStateChange("loading");
            try {
                image.src = await v1VideoStreamPlaybackUrl(cameraId, { profile });
                frameCheckTimer = setTimeout(() => {
                    if (disposed || !cameraId) return;
                    if (imageHasFrame()) {
                        onStateChange("playing");
                    } else {
                        showSnapshotFallback();
                    }
                }, 1500);
                refreshTimer = setTimeout(refresh, refreshMs);
            } catch (error) {
                onStateChange("error", error);
                retryTimer = setTimeout(refresh, retryMs);
            }
        }

        async function showSnapshotFallback() {
            if (disposed || !image || !cameraId) return;
            try {
                const snapshot = await appLatestSnapshot(cameraId, { allowMissing: true });
                if (disposed || !image || !cameraId) return;
                if (snapshot?.available === false || !(snapshot?.image_url || snapshot?.snapshot_path)) {
                    onStateChange("waiting");
                    retryTimer = setTimeout(refresh, Math.max(retryMs, 8000));
                    return;
                }
                image.src = appMediaUrl(snapshot.image_url || snapshot.snapshot_path);
                onStateChange("snapshot", snapshot);
                retryTimer = setTimeout(refresh, Math.max(retryMs, 10000));
            } catch (error) {
                onStateChange("waiting", error);
                retryTimer = setTimeout(refresh, Math.max(retryMs, 8000));
            }
        }

        function setSource(nextCameraId, nextOptions = {}) {
            cameraId = nextCameraId ? Number(nextCameraId) : null;
            const mergedOptions = { ...options, ...nextOptions };
            resolved = managedVideoStreamOptions(mergedOptions);
            profile = resolved.profile;
            refreshMs = resolved.refreshMs;
            retryMs = resolved.retryMs;
            snapshotOnly = Boolean(mergedOptions.snapshotOnly);
            snapshotRefreshMs = Math.max(2500, Number(mergedOptions.snapshotRefreshMs || 3000));
            lastSnapshotPath = "";
            lastSnapshotPayload = null;
            if (!cameraId) {
                clearTimers();
                image.removeAttribute("src");
                onStateChange("idle");
                return;
            }
            refresh();
        }

        function handleError() {
            if (disposed || !cameraId) return;
            onStateChange("error");
            clearTimers();
            retryTimer = setTimeout(refresh, retryMs);
        }

        function handleLoad() {
            if (disposed || !cameraId) return;
            if (snapshotOnly && imageHasFrame()) {
                onStateChange("snapshot", lastSnapshotPayload);
                return;
            }
            if (imageHasFrame()) {
                onStateChange("playing");
            }
        }

        function handleVisibilityChange() {
            if (!document.hidden && cameraId) {
                if (snapshotOnly) refreshSnapshotOnly();
                else refresh();
            }
        }

        image?.addEventListener("error", handleError);
        image?.addEventListener("load", handleLoad);
        document.addEventListener("visibilitychange", handleVisibilityChange);
        if (cameraId) {
            if (snapshotOnly) refreshSnapshotOnly();
            else refresh();
        }

        return {
            refresh,
            setSource,
            dispose() {
                disposed = true;
                clearTimers();
                image?.removeEventListener("error", handleError);
                image?.removeEventListener("load", handleLoad);
                document.removeEventListener("visibilitychange", handleVisibilityChange);
            },
        };
    }

    async function uploadWithSignedUrl(uploadUrl, blob, contentType = "") {
        const headers = {};
        if (contentType) headers["Content-Type"] = contentType;
        const res = await fetch(edgeUrl(uploadUrl), {
            method: "PUT",
            headers,
            body: blob,
        });
        const text = await res.text();
        if (!res.ok) {
            throw new Error(text || `Upload failed (${res.status})`);
        }
        try {
            return JSON.parse(text);
        } catch {
            return text;
        }
    }

    async function videoMediaPlaybackUrl(sessionPath, mediaBasePath, path) {
        const snapshotPath = normalizeSnapshotPath(path);
        if (!snapshotPath) return "";
        const session = await createPlaybackSessionAt(sessionPath, {
            resource_type: "snapshot",
            snapshot_path: snapshotPath,
            expires_in_seconds: 120,
        });
        const url = new URL(edgeUrl(`${mediaBasePath}/${snapshotPath}`), window.location.href);
        url.searchParams.set("playback_ticket", session.ticket);
        url.searchParams.set("t", String(Date.now()));
        return url.toString();
    }

    function cacheBustUrl(url) {
        if (!url) return "";
        const target = new URL(url, window.location.href);
        target.searchParams.set("t", String(Date.now()));
        return target.toString();
    }

    function nativeBridge() {
        return window.GoHomeNativeApp || window.gohomeNativeApp || null;
    }

    function nativeBridgeAvailable() {
        return Boolean(
            (nativeBridge() && (typeof nativeBridge().registerForPush === "function" || typeof nativeBridge().consumeLaunchPayload === "function"))
            || window.webkit?.messageHandlers?.gohomeNativeApp
        );
    }

    async function callNativeBridge(method, payload = {}) {
        const bridge = nativeBridge();
        if (bridge && typeof bridge[method] === "function") {
            return await bridge[method](payload);
        }
        const handler = window.webkit?.messageHandlers?.gohomeNativeApp;
        if (!handler) return null;
        const requestId = `native-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        return await new Promise((resolve, reject) => {
            const timer = window.setTimeout(() => {
                nativeBridgeRequests.delete(requestId);
                reject(new Error("Native bridge timeout"));
            }, 4000);
            nativeBridgeRequests.set(requestId, {
                resolve(result) {
                    window.clearTimeout(timer);
                    resolve(result);
                },
                reject(error) {
                    window.clearTimeout(timer);
                    reject(error instanceof Error ? error : new Error(String(error || "Native bridge error")));
                },
            });
            handler.postMessage({ method, payload, requestId });
        });
    }

    function resolveNativeBridgeResult(requestId, result, error = "") {
        const pending = nativeBridgeRequests.get(String(requestId || ""));
        if (!pending) return false;
        nativeBridgeRequests.delete(String(requestId || ""));
        if (error) {
            pending.reject(error);
            return true;
        }
        pending.resolve(result || null);
        return true;
    }

    function normalizeNativePushRegistration(raw) {
        if (!raw || typeof raw !== "object") return null;
        const pushToken = String(raw.push_token || raw.pushToken || "").trim();
        const appInstallId = String(raw.app_install_id || raw.appInstallId || "").trim();
        if (!pushToken || !appInstallId) return null;
        return {
            app_install_id: appInstallId,
            platform: String(raw.platform || "ios").trim().toLowerCase() || "ios",
            provider: String(raw.provider || "apns").trim().toLowerCase() || "apns",
            push_token: pushToken,
            device_name: String(raw.device_name || raw.deviceName || "").trim(),
            app_version: String(raw.app_version || raw.appVersion || "").trim(),
            environment: String(raw.environment || "production").trim().toLowerCase() || "production",
            metadata: raw.metadata && typeof raw.metadata === "object" ? raw.metadata : {},
        };
    }

    async function requestNativePushRegistration() {
        try {
            return normalizeNativePushRegistration(await callNativeBridge("registerForPush", { app: "gohome" }));
        } catch (_error) {
            return null;
        }
    }

    async function consumeNativeLaunchPayload() {
        try {
            const payload = await callNativeBridge("consumeLaunchPayload", { app: "gohome" });
            return payload && typeof payload === "object" ? payload : null;
        } catch (_error) {
            return null;
        }
    }

    function fmtTime(value) {
        if (!value) return "-";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "-";
        return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
    }

    function fmtDateTime(value) {
        if (!value) return "-";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "-";
        return date.toLocaleString("zh-CN", {
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        });
    }

    function eventIcon(type) {
        const icons = {
            black_screen: "visibility_off",
            camera_offline: "wifi_off",
            no_motion: "motion_sensor_idle",
            no_person: "person_off",
            fall_candidate: "personal_injury",
        };
        return icons[type] || "notifications_active";
    }

    function eventLabel(type) {
        const labels = {
            black_screen: "画面异常",
            camera_offline: "设备离线",
            no_motion: "长时间无变化",
            no_person: "长时间无人",
            fall_candidate: "疑似跌倒",
        };
        return labels[type] || "提醒";
    }

    const GoHomeEdge = {
        apiBase: defaultBase(),
        connect,
        request,
        edgeUrl,
        mediaUrl,
        appMediaUrl,
        appMediaPlaybackUrl,
        cacheBustUrl,
        streamUrl,
        appStreamUrl,
        v1VideoStreamUrl,
        appStreamPlaybackUrl,
        v1VideoStreamPlaybackUrl,
        v1VideoAssetPlaybackUrl,
        preferredVideoProfile,
        managedVideoStreamOptions,
        createManagedVideoStream,
        bootstrapLaunchState,
        currentPagePath,
        pageHref,
        loginHref,
        redirectTarget,
        isAppShellMode,
        getAuthToken,
        setAuthToken,
        clearAuthToken,
        isAuthenticated: () => Boolean(getAuthToken()),
        fmtTime,
        fmtDateTime,
        eventIcon,
        eventLabel,
        nativeBridgeAvailable,
        resolveNativeBridgeResult,
        requestNativePushRegistration,
        consumeNativeLaunchPayload,
        device: () => request("/api/device"),
        register: async (payload) => {
            const data = await request("/api/auth/register", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            if (data?.token) setAuthToken(data.token);
            return data;
        },
        login: async (payload) => {
            const data = await request("/api/auth/login", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            if (data?.token) setAuthToken(data.token);
            return data;
        },
        v1Register: async (payload) => {
            const data = await request("/api/v1/identity/register", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            if (data?.token) setAuthToken(data.token);
            return data;
        },
        v1Login: async (payload) => {
            const data = await request("/api/v1/identity/login", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            if (data?.token) setAuthToken(data.token);
            return data;
        },
        v1CurrentUser: () => request("/api/v1/identity/me"),
        currentUser: () => request("/api/users/me"),
        v1CurrentDevice: () => request("/api/v1/devices/current"),
        v1VideoProfiles: () => request("/api/v1/video/profiles"),
        v1Devices: (familyId) => request(`/api/v1/devices?family_id=${encodeURIComponent(familyId)}`),
        v1CurrentDeviceSyncState: () => request("/api/v1/devices/current/sync-state"),
        appDevice: () => withDeviceAccessFallback(
            () => request("/api/app/device"),
            () => request("/api/device")
        ),
        v1CreateHousehold: (payload) => request("/api/v1/households", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1Households: () => request("/api/v1/households/mine"),
        v1ElderProfile: (familyId, elderId = "elder_primary") =>
            request(`/api/v1/families/${encodeURIComponent(familyId)}/elders/${encodeURIComponent(elderId)}/profile`),
        v1UpsertElderProfile: (familyId, elderId = "elder_primary", payload = {}) =>
            request(`/api/v1/families/${encodeURIComponent(familyId)}/elders/${encodeURIComponent(elderId)}/profile`, {
                method: "PUT",
                body: JSON.stringify(payload),
            }),
        v1CalendarEvents: (familyId, elderId = "") => {
            const query = elderId ? `?elder_id=${encodeURIComponent(elderId)}` : "";
            return request(`/api/v1/families/${encodeURIComponent(familyId)}/calendar-events${query}`);
        },
        v1CreateCalendarEvent: (familyId, payload = {}) =>
            request(`/api/v1/families/${encodeURIComponent(familyId)}/calendar-events`, {
                method: "POST",
                body: JSON.stringify(payload),
            }),
        v1WeatherSignals: (familyId, params = {}) => {
            const query = new URLSearchParams();
            if (params.elder_id) query.set("elder_id", params.elder_id);
            if (params.city) query.set("city", params.city);
            const suffix = query.toString() ? `?${query.toString()}` : "";
            return request(`/api/v1/families/${encodeURIComponent(familyId)}/weather-signals${suffix}`);
        },
        v1ContentRecommendations: (familyId, params = {}) => {
            const query = new URLSearchParams();
            if (params.elder_id) query.set("elder_id", params.elder_id);
            if (params.city) query.set("city", params.city);
            if (params.district) query.set("district", params.district);
            const suffix = query.toString() ? `?${query.toString()}` : "";
            return request(`/api/v1/families/${encodeURIComponent(familyId)}/content-recommendations${suffix}`);
        },
        v1CareCardToday: (familyId = "") => {
            const suffix = familyId ? `?family_id=${encodeURIComponent(familyId)}` : "";
            return request(`/api/v1/app/care-cards/today${suffix}`);
        },
        v1CareCards: (params = {}) => {
            const query = new URLSearchParams();
            if (params.family_id) query.set("family_id", String(params.family_id));
            if (params.limit) query.set("limit", String(params.limit));
            const suffix = query.toString() ? `?${query.toString()}` : "";
            return request(`/api/v1/app/care-cards${suffix}`);
        },
        v1GenerateCareCard: (payload = {}) => request("/api/v1/internal/care-cards/generate", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1CarePreferences: (familyId) =>
            request(`/api/v1/families/${encodeURIComponent(familyId)}/care-preferences`),
        v1UpdateCarePreferences: (familyId, payload = {}) =>
            request(`/api/v1/families/${encodeURIComponent(familyId)}/care-preferences`, {
                method: "PUT",
                body: JSON.stringify(payload),
            }),
        v1OpsServiceConfig: () => request("/api/v1/ops/service-config"),
        v1GenerateMessages: (payload = {}) => request("/api/v1/internal/messages/generate", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1AppMessages: (params = {}) => {
            const query = new URLSearchParams();
            if (params.family_id) query.set("family_id", String(params.family_id));
            if (params.limit) query.set("limit", String(params.limit));
            if (params.status) query.set("status", String(params.status));
            const suffix = query.toString() ? `?${query.toString()}` : "";
            return request(`/api/v1/app/messages${suffix}`);
        },
        v1AppMessage: (messageId, familyId = "") =>
            request(`/api/v1/app/messages/${encodeURIComponent(messageId)}${familyId ? `?family_id=${encodeURIComponent(familyId)}` : ""}`),
        v1UpdateAppMessage: (messageId, patch = {}, familyId = "") =>
            request(`/api/v1/app/messages/${encodeURIComponent(messageId)}${familyId ? `?family_id=${encodeURIComponent(familyId)}` : ""}`, {
                method: "PATCH",
                body: JSON.stringify(patch),
            }),
        createFamily: (payload) => request("/api/families", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        joinFamily: (payload) => request("/api/families/join", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        myFamilies: () => request("/api/families/mine"),
        bindDevice: (payload) => request("/api/device-bindings", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        deviceBindings: (familyId) => request(`/api/device-bindings?family_id=${encodeURIComponent(familyId)}`),
        claimableDevices: () => request("/api/device-claims/available"),
        claimDevice: (payload) => request("/api/device-claims/claim", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        createDeviceBindingCode: (payload) => request("/api/device/binding-codes", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        deviceBindingCodes: (familyId) => request(`/api/device/binding-codes?family_id=${encodeURIComponent(familyId)}`),
        exchangeDeviceToken: (payload) => request("/api/device/token/exchange", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        deviceHeartbeatSelf: (payload) => request("/api/device/heartbeat/self", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        deviceAuthStatus: () => request("/api/device/auth-status"),
        createPlaybackSession,
        createV1VideoSession,
        v1CreateDeviceMediaAsset: (payload) => request("/api/v1/device/media-assets", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1CreateMediaUploadSession: (payload) => request("/api/v1/media/upload-sessions", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1UploadMediaContent: (uploadUrl, blob, contentType = "") => uploadWithSignedUrl(uploadUrl, blob, contentType),
        v1CompleteMediaUploadSession: (completeUrl, payload = {}) => request(completeUrl, {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1CreateMediaPublicLink: (assetId, payload = {}) => request(`/api/v1/media/assets/${encodeURIComponent(assetId)}/public-links`, {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1PackageReleases: (familyId, packageType = "", limit = 20) => {
            const query = new URLSearchParams({ family_id: String(familyId), limit: String(limit) });
            if (packageType) query.set("package_type", packageType);
            return request(`/api/v1/package-releases?${query.toString()}`);
        },
        v1CreatePackageRelease: (payload) => request("/api/v1/package-releases", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1PackageRelease: (releaseId) => request(`/api/v1/package-releases/${encodeURIComponent(releaseId)}`),
        v1CreatePackageDownloadLink: (releaseId, payload = {}) => request(`/api/v1/package-releases/${encodeURIComponent(releaseId)}/download-links`, {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1PackageExecutions: (familyId, deviceId = "", limit = 20) => {
            const query = new URLSearchParams({ family_id: String(familyId), limit: String(limit) });
            if (deviceId) query.set("device_id", deviceId);
            return request(`/api/v1/package-executions?${query.toString()}`);
        },
        v1RunCurrentDeviceUpgrade: (payload = {}) => request("/api/v1/devices/current/upgrade-run", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1RunDeviceUpgrade: (payload = {}, token = "") => request("/api/v1/device/upgrade-run", {
            method: "POST",
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            body: JSON.stringify(payload),
        }),
        v1NotificationDeliveries: (query = "") => request(`/api/v1/notifications/deliveries${query ? `?${query}` : ""}`),
        v1NotificationTest: (payload) => request("/api/v1/notifications/test", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1AppPushTokens: (familyId = "") => request(`/api/v1/app/push-tokens${familyId ? `?family_id=${encodeURIComponent(familyId)}` : ""}`),
        v1UpsertAppPushToken: (payload) => request("/api/v1/app/push-tokens", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1DeleteAppPushToken: (appInstallId) => request(`/api/v1/app/push-tokens/${encodeURIComponent(appInstallId)}`, {
            method: "DELETE",
        }),
        v1AppPushTest: (payload) => request("/api/v1/app/push-test", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1DeviceRollouts: (familyId, limit = 20) =>
            request(`/api/v1/device-rollouts?family_id=${encodeURIComponent(familyId)}&limit=${encodeURIComponent(limit)}`),
        v1CreateDeviceRollout: (payload) => request("/api/v1/device-rollouts", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1DeviceRollout: (rolloutId) => request(`/api/v1/device-rollouts/${encodeURIComponent(rolloutId)}`),
        v1PromoteDeviceRollout: (rolloutId, payload = {}) => request(`/api/v1/device-rollouts/${encodeURIComponent(rolloutId)}/promote`, {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1RollbackDeviceRollout: (rolloutId, payload = {}) => request(`/api/v1/device-rollouts/${encodeURIComponent(rolloutId)}/rollback`, {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        v1UpdateDeviceSyncTarget: (payload) => request("/api/v1/devices/current/sync-target", {
            method: "PATCH",
            body: JSON.stringify(payload),
        }),
        v1DeviceSync: (payload, token) => request("/api/v1/device/sync", {
            method: "POST",
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            body: JSON.stringify(payload),
        }),
        appCameras: () => withDeviceAccessFallback(
            () => request("/api/app/cameras"),
            () => request("/api/cameras")
        ),
        v1VideoMediaPlaybackUrl,
        cameras: () => request("/api/cameras"),
        createCamera: (payload) => request("/api/cameras", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        testCameraConnection: (payload) => request("/api/cameras/test-connection", {
            method: "POST",
            body: JSON.stringify(payload),
        }),
        updateCamera: (cameraId, patch) => request(`/api/cameras/${cameraId}`, {
            method: "PATCH",
            body: JSON.stringify(patch),
        }),
        deleteCamera: (cameraId) => request(`/api/cameras/${cameraId}`, { method: "DELETE" }),
        testCamera: (cameraId) => request(`/api/cameras/${cameraId}/test`, { method: "POST" }),
        latestSnapshot: (cameraId, options = {}) => {
            const params = new URLSearchParams();
            if (options.allowMissing) params.set("allow_missing", "1");
            const query = params.toString();
            return request(`/api/cameras/${cameraId}/snapshot/latest${query ? `?${query}` : ""}`);
        },
        appLatestSnapshot,
        latestEvaluation: (cameraId) => request(`/api/cameras/${cameraId}/evaluation/latest`),
        appLatestEvaluation: (cameraId) => withDeviceAccessFallback(
            () => request(`/api/app/cameras/${cameraId}/evaluation/latest`),
            () => request(`/api/cameras/${cameraId}/evaluation/latest`)
        ),
        capture: (cameraId) => request(`/api/cameras/${cameraId}/capture`, { method: "POST" }),
        appEvents: (params = "limit=30") => withDeviceAccessFallback(
            () => request(`/api/app/events?${params}`),
            () => request(`/api/events?${params}`)
        ),
        v1Events: (params = "limit=30") => request(`/api/v1/events?${params}`),
        events: (params = "limit=30") => request(`/api/events?${params}`),
        v1Event: (eventId) => request(`/api/v1/events/${eventId}`),
        appEvent: (eventId) => withDeviceAccessFallback(
            () => request(`/api/app/events/${eventId}`),
            () => request(`/api/events/${eventId}`)
        ),
        event: (eventId) => request(`/api/events/${eventId}`),
        v1UpdateEvent: (eventId, patch) => request(`/api/v1/events/${eventId}`, {
            method: "PATCH",
            body: JSON.stringify(patch),
        }),
        appUpdateEvent: (eventId, patch) => withDeviceAccessFallback(
            () => request(`/api/app/events/${eventId}`, {
                method: "PATCH",
                body: JSON.stringify(patch),
            }),
            () => request(`/api/events/${eventId}`, {
                method: "PATCH",
                body: JSON.stringify(patch),
            })
        ),
        updateEvent: (eventId, patch) => request(`/api/events/${eventId}`, {
            method: "PATCH",
            body: JSON.stringify(patch),
        }),
        rules: () => request("/api/rules"),
        rulesRuntime: () => request("/api/rules/runtime"),
        updateRules: (rules) => request("/api/rules", {
            method: "PUT",
            body: JSON.stringify(rules),
        }),
        v1Summary: () => request("/api/v1/summary/today"),
        appSummary: () => withDeviceAccessFallback(
            () => request("/api/app/summary/today"),
            () => request("/api/summary/today")
        ),
        summary: () => request("/api/summary/today"),
    };

    window.GoHomeEdge = GoHomeEdge;
})();
