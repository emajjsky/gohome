(function () {
    const DEFAULT_EDGE_BASE = "http://127.0.0.1:8711";
    const EDGE_KEY = "gohome.edgeApiBase";

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

    async function request(path, options = {}) {
        const base = GoHomeEdge.apiBase;
        const response = await fetch(`${base}${path}`, {
            headers: { "Content-Type": "application/json", ...(options.headers || {}) },
            ...options,
        });
        const text = await response.text();
        const data = text ? JSON.parse(text) : null;
        if (!response.ok) {
            throw new Error(data?.detail || `HTTP ${response.status}`);
        }
        return data;
    }

    async function connect() {
        const candidates = [];
        const requested = requestedBase();
        if (requested) candidates.push(requested);
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
                    GoHomeEdge.apiBase = base;
                    if (base) localStorage.setItem(EDGE_KEY, base);
                    return response.json();
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
        fmtTime,
        fmtDateTime,
        eventIcon,
        eventLabel,
        device: () => request("/api/device"),
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
        latestSnapshot: (cameraId) => request(`/api/cameras/${cameraId}/snapshot/latest`),
        latestEvaluation: (cameraId) => request(`/api/cameras/${cameraId}/evaluation/latest`),
        capture: (cameraId) => request(`/api/cameras/${cameraId}/capture`, { method: "POST" }),
        events: (params = "limit=30") => request(`/api/events?${params}`),
        event: (eventId) => request(`/api/events/${eventId}`),
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
        summary: () => request("/api/summary/today"),
    };

    window.GoHomeEdge = GoHomeEdge;
})();
