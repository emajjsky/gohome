(function () {
    const $ = (id) => document.getElementById(id);

    const state = {
        config: null,
        user: null,
        families: [],
        device: null,
        cameras: [],
    };

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function setHref(id, href) {
        const node = $(id);
        if (node) node.href = href;
    }

    function preferredCamera() {
        return [...state.cameras]
            .filter((item) => item.enabled !== false)
            .sort((a, b) => {
                const score = (camera) => (
                    (camera.enabled !== false ? 100 : 0) +
                    (camera.status === "online" ? 30 : 0)
                );
                return score(b) - score(a);
            })[0] || null;
    }

    function cameraScopedPath(path, cameraId = null) {
        if (!cameraId) return path;
        const url = new URL(path, window.location.href);
        url.searchParams.set("camera_id", String(cameraId));
        const page = url.pathname.split("/").pop() || path;
        return `${page}${url.search}${url.hash}`;
    }

    function isAuthError(error) {
        return Number(error?.status || 0) === 401;
    }

    async function loadConfig() {
        const response = await fetch("assets/data/app-shell-config.json", { cache: "no-store" });
        if (!response.ok) throw new Error("App 壳配置读取失败");
        state.config = await response.json();
        setText("appShellTitle", state.config.app_name || "回家");
        setText("appShellSubtitle", state.config.subtitle || "");
        setText("appShellBundleId", state.config.bundle_id || "-");
        setText("appShellScheme", state.config.scheme || "-");
        setHref("appShellPrivacyLink", window.GoHomeEdge?.pageHref?.(state.config.privacy_path || "privacy.html") || "privacy.html");
    }

    function actionHref(item) {
        const cameraId = preferredCamera()?.id || null;
        const rawTarget = item?.href || "index.html";
        const target = item?.id === "watch" ? cameraScopedPath(rawTarget, cameraId) : rawTarget;
        if (!window.GoHomeEdge?.isAuthenticated()) {
            return window.GoHomeEdge?.loginHref?.(window.GoHomeEdge?.pageHref?.(target) || target) || "login.html";
        }
        return window.GoHomeEdge?.pageHref?.(target) || target;
    }

    function syncQuickLinks() {
        const cameraId = preferredCamera()?.id || null;
        setHref("appShellHomeLink", window.GoHomeEdge?.pageHref?.("index.html") || "index.html");
        setHref("appShellWatchLink", window.GoHomeEdge?.pageHref?.(cameraScopedPath("watch.html", cameraId)) || cameraScopedPath("watch.html", cameraId));
        setHref("appShellEventsLink", window.GoHomeEdge?.pageHref?.(cameraScopedPath("events.html", cameraId)) || cameraScopedPath("events.html", cameraId));
    }

    function renderActions() {
        const list = $("appShellActionList");
        if (!list || !state.config?.tabs) return;
        list.innerHTML = state.config.tabs.map((item) => `
            <a href="${actionHref(item)}" class="app-soft-card bg-white p-4 flex items-center justify-between gap-3">
                <div class="min-w-0">
                    <p class="font-display text-[16px] font-bold text-on-surface">${item.label}</p>
                    <p class="font-sans text-[12px] text-on-surface-variant mt-1">${item.hint || ""}</p>
                </div>
                <div class="w-11 h-11 rounded-full bg-[#f4f6fb] text-on-surface flex items-center justify-center shrink-0">
                    <span class="material-symbols-outlined text-[21px]">${item.icon || "arrow_forward"}</span>
                </div>
            </a>
        `).join("");
    }

    function renderLoggedOut() {
        setText("appShellStatusBadge", "待登录");
        setText("appShellHeadline", "先登录，再进 App。");
        setText("appShellMeta", "登录成功后直接承接到实时观看、家庭空间和设备绑定。");
        setText("appShellAccountValue", "未登录");
        setText("appShellFamilyValue", "未创建");
        setText("appShellDeviceValue", "未连接");
        setText("appShellCameraValue", "-");
        setHref("appShellPrimaryAction", window.GoHomeEdge?.loginHref?.("app-shell.html") || "login.html");
        setText("appShellPrimaryText", "登录进入");
        setHref("appShellSecondaryAction", window.GoHomeEdge?.pageHref?.("index.html") || "index.html");
        syncQuickLinks();
        renderActions();
    }

    function renderLoggedIn() {
        const family = state.families[0] || null;
        const hasDevice = Boolean(state.device?.device_id);
        const cameraCount = state.cameras.filter((item) => item.enabled !== false).length;
        setText("appShellStatusBadge", "已接入");
        setText("appShellHeadline", family ? `${family.name || "家庭空间"} 已接住 App 壳` : "账号已进入 App 壳");
        setText("appShellMeta", hasDevice ? "登录态和本机守护服务已经打通，可继续进入实时观看。" : "先补家庭或设备绑定，再进入实时观看。");
        setText("appShellAccountValue", state.user?.display_name || state.user?.email || "已登录");
        setText("appShellFamilyValue", family?.name || "待创建");
        setText("appShellDeviceValue", state.device?.device_name || state.device?.device_id || "待接入");
        setText("appShellCameraValue", cameraCount ? `${cameraCount} 路` : "未接入");
        const cameraId = preferredCamera()?.id || null;
        const primaryTarget = family ? (hasDevice ? cameraScopedPath("watch.html", cameraId) : "device_binding.html") : "family.html";
        const primaryLabel = family ? (hasDevice ? "进入实时观看" : "先绑设备") : "先建家庭";
        setHref("appShellPrimaryAction", window.GoHomeEdge?.pageHref?.(primaryTarget) || primaryTarget);
        setText("appShellPrimaryText", primaryLabel);
        setHref("appShellSecondaryAction", window.GoHomeEdge?.pageHref?.("family.html") || "family.html");
        syncQuickLinks();
        renderActions();
    }

    function launchTarget(payload) {
        if (!payload || typeof payload !== "object") return "";
        if (payload.next) return String(payload.next || "").trim();
        if (payload.event_id) {
            const cameraSuffix = payload.camera_id ? `&camera_id=${encodeURIComponent(payload.camera_id)}` : "";
            return `event_detail.html?eventId=${encodeURIComponent(payload.event_id)}${cameraSuffix}`;
        }
        if (payload.camera_id) return `watch.html?camera_id=${encodeURIComponent(payload.camera_id)}`;
        return "";
    }

    async function syncNativePush() {
        const family = state.families[0] || null;
        if (!family?.id || !window.GoHomeEdge?.nativeBridgeAvailable?.()) return;
        const registration = await window.GoHomeEdge.requestNativePushRegistration?.();
        if (!registration?.push_token || !registration?.app_install_id) return;
        await window.GoHomeEdge.v1UpsertAppPushToken?.({
            family_id: family.id,
            app_install_id: registration.app_install_id,
            platform: registration.platform || "ios",
            provider: registration.provider || "apns",
            push_token: registration.push_token,
            device_name: registration.device_name || "",
            app_version: registration.app_version || "",
            environment: registration.environment || "production",
            metadata: registration.metadata || {},
        });
    }

    async function openNativeLaunchTarget() {
        if (!window.GoHomeEdge?.nativeBridgeAvailable?.()) return;
        const payload = await window.GoHomeEdge.consumeNativeLaunchPayload?.();
        const target = launchTarget(payload);
        if (!target) return;
        window.location.href = window.GoHomeEdge?.pageHref?.(target, { app: true }) || target;
    }

    async function loadSession() {
        if (!window.GoHomeEdge?.isAuthenticated()) {
            renderLoggedOut();
            return;
        }
        try {
            const [user, families] = await Promise.all([
                GoHomeEdge.currentUser(),
                GoHomeEdge.myFamilies(),
            ]);
            state.user = user;
            state.families = families;
            try {
                state.device = await GoHomeEdge.appDevice();
            } catch (error) {
                if (isAuthError(error)) throw error;
                state.device = null;
            }
            try {
                const cameras = await GoHomeEdge.appCameras();
                state.cameras = Array.isArray(cameras) ? cameras : [];
            } catch (error) {
                if (isAuthError(error)) throw error;
                state.cameras = [];
            }
            renderLoggedIn();
            try {
                await syncNativePush();
                await openNativeLaunchTarget();
            } catch (_nativeError) {
                // Native bridge or push registration should not invalidate the web login session.
            }
        } catch (_error) {
            GoHomeEdge.clearAuthToken();
            renderLoggedOut();
        }
    }

    async function bootstrap() {
        if (!window.GoHomeEdge) return;
        try {
            GoHomeEdge.bootstrapLaunchState?.();
            await loadConfig();
            await GoHomeEdge.connect();
            await loadSession();
        } catch (error) {
            setText("appShellStatusBadge", "未连接");
            setText("appShellHeadline", "App 壳已打开，但守护服务未连接。");
            setText("appShellMeta", error.message || "请先启动 edge-agent。");
            renderActions();
        }
    }

    document.addEventListener("DOMContentLoaded", bootstrap);
})();
