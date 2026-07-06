(function () {
    const state = {
        device: null,
        cameras: [],
        profiles: [],
        selectedCameraId: null,
        selectedProfile: "mobile",
        latestEvent: null,
        streamController: null,
    };

    const $ = (id) => document.getElementById(id);

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function cameraLabel(camera) {
        return camera.room || camera.name || "摄像头";
    }

    function cameraMeta(camera) {
        const parts = [];
        if (camera.status === "online") parts.push("盒子在线");
        if (camera.status === "offline") parts.push("离线");
        if (!camera.has_stream_config) parts.push("缺接入信息");
        if (camera.enabled === false) parts.push("未启用");
        return parts.join(" · ") || "等待";
    }

    function preferredCamera(cameras) {
        return [...cameras].sort((a, b) => {
            const score = (camera) => (
                (camera.enabled ? 100 : 0) +
                (camera.status === "online" ? 30 : 0)
            );
            return score(b) - score(a) || Number(b.id) - Number(a.id);
        })[0] || null;
    }

    function activeCamera() {
        return state.cameras.find((item) => Number(item.id) === Number(state.selectedCameraId)) || null;
    }

    function requestedCameraId() {
        const value = new URLSearchParams(window.location.search).get("camera_id");
        return value ? Number(value) : null;
    }

    function syncSelectedCameraParam(cameraId) {
        const url = new URL(window.location.href);
        if (cameraId) {
            url.searchParams.set("camera_id", String(cameraId));
        } else {
            url.searchParams.delete("camera_id");
        }
        window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    }

    function syncNavLinks() {
        const camera = activeCamera();
        const suffix = camera?.id ? `?camera_id=${encodeURIComponent(camera.id)}` : "";
        const detectionHref = GoHomeEdge.pageHref(`detection.html${suffix}`) || `detection.html${suffix}`;
        const monitorHref = GoHomeEdge.pageHref(`monitor.html${suffix}`) || `monitor.html${suffix}`;
        const eventsHref = GoHomeEdge.pageHref(`events.html${suffix}`) || `events.html${suffix}`;
        const monitorTop = $("watchMonitorTopLink");
        const detectionTop = $("watchDetectionTopLink");
        const detectionAction = $("watchDetectionLink");
        const monitorLink = $("watchMonitorLink");
        const eventsLink = $("watchEventsLink");
        if (monitorTop) monitorTop.href = monitorHref;
        if (detectionTop) detectionTop.href = detectionHref;
        if (detectionAction) detectionAction.href = detectionHref;
        if (monitorLink) monitorLink.href = monitorHref;
        if (eventsLink) eventsLink.href = eventsHref;
    }

    function normalizeProfiles(payload) {
        if (Array.isArray(payload)) return payload;
        if (Array.isArray(payload?.profiles)) return payload.profiles;
        return [];
    }

    function applyStageState(kind, message = "") {
        const empty = $("watchEmptyState");
        if (!empty) return;
        if (kind === "empty" || kind === "error") {
            empty.classList.remove("hidden");
            setText("watchEmptyText", message || "当前没有可用画面");
            setText("watchStatusBadge", kind === "error" ? "连接失败" : "暂无画面");
            return;
        }
        if (kind === "loading" || kind === "waiting") {
            empty.classList.remove("hidden");
            setText("watchEmptyText", kind === "waiting"
                ? "盒子已在线，但 App API 还没有收到可显示的视频帧。"
                : "正在向家庭盒子请求实时画面。");
            setText("watchStatusBadge", kind === "waiting" ? "等待帧" : "连接中");
            return;
        }
        empty.classList.add("hidden");
        setText("watchStatusBadge", "有画面");
    }

    function renderCameraList() {
        const list = $("watchCameraList");
        setText("watchCameraCount", state.cameras.length ? `${state.cameras.length} 路` : "未接入");
        if (!list) return;
        if (!state.cameras.length) {
            list.innerHTML = "";
            return;
        }
        list.className = "source-list";
        list.innerHTML = state.cameras.map((camera) => {
            const active = Number(camera.id) === Number(state.selectedCameraId);
            return `
                <button type="button" data-camera-id="${camera.id}" class="watch-source-button ${active ? "active" : ""}">
                    <span>
                        <strong>${escapeHtml(cameraLabel(camera))}</strong>
                        <span>${escapeHtml(cameraMeta(camera))}</span>
                    </span>
                    <em class="pill ${camera.status === "online" ? "good" : "warn"}">${camera.status === "online" ? "在线" : "待处理"}</em>
                </button>
            `;
        }).join("");
        list.querySelectorAll("[data-camera-id]").forEach((button) => {
            button.addEventListener("click", () => {
                state.selectedCameraId = Number(button.dataset.cameraId);
                syncSelectedCameraParam(state.selectedCameraId);
                renderCameraList();
                attachStream();
                loadLatestEvent();
            });
        });
    }

    function renderProfileList() {
        const list = $("watchProfileList");
        if (!list) return;
        list.innerHTML = state.profiles.map((profile) => {
            const active = profile.id === state.selectedProfile;
            return `
                <button type="button" data-profile-id="${escapeHtml(profile.id)}" class="profile-button ${active ? "active" : ""}">
                    ${escapeHtml(profile.id)}
                </button>
            `;
        }).join("");
        list.querySelectorAll("[data-profile-id]").forEach((button) => {
            button.addEventListener("click", () => {
                state.selectedProfile = button.dataset.profileId || "mobile";
                renderProfileList();
                attachStream();
            });
        });
    }

    function renderHeader() {
        const camera = activeCamera();
        setText("watchHeaderSub", state.device?.worker_running ? "服务在线" : "服务暂停");
        setText("watchRoomBadge", camera ? cameraLabel(camera) : "未选择");
        setText("watchProfileBadge", state.selectedProfile);
        setText("watchDetectorBadge", state.device?.detector_backend === "yolo" ? "YOLO" : "basic");
        setText("watchFact", camera ? `${cameraLabel(camera)}实时画面` : "还没有接入摄像头");
        setText("watchMeta", camera
            ? `${cameraMeta(camera)}。如果这里没有画面，说明 App API 暂未收到第一帧。`
            : "等待摄像头");
        syncNavLinks();
    }

    async function attachStream() {
        const camera = activeCamera();
        const image = $("watchStageImage");
        if (!image) return;
        renderHeader();
        if (!camera) {
            state.streamController?.setSource(null);
            applyStageState("empty", "还没有可用的摄像头");
            return;
        }
        if (!state.streamController) {
            state.streamController = GoHomeEdge.createManagedVideoStream(image, {
                cameraId: camera.id,
                scene: "watch",
                profile: state.selectedProfile,
                onStateChange(nextState) {
                    if (nextState === "loading") applyStageState("loading");
                    if (nextState === "waiting") applyStageState("waiting");
                    if (nextState === "playing") applyStageState("playing");
                    if (nextState === "error") applyStageState("error", "画面暂时断开，正在重连");
                },
            });
        }
        state.streamController.setSource(camera.id, { scene: "watch", profile: state.selectedProfile });
        applyStageState("loading");
    }

    async function loadLatestEvent() {
        const camera = activeCamera();
        if (!camera) {
            setText("watchEventTitle", "等待事件");
            setText("watchEventMeta", "画面接通后自动刷新");
            return;
        }
        const events = await GoHomeEdge.appEvents("limit=8&acknowledged=false");
        const event = events.find((item) => Number(item.camera_id) === Number(camera.id)) || events[0] || null;
        state.latestEvent = event;
        if (!event) {
            setText("watchEventTitle", "当前没有未处理提醒");
            setText("watchEventMeta", `${cameraLabel(camera)} · 继续观察`);
            return;
        }
        setText("watchEventTitle", event.summary || GoHomeEdge.eventLabel(event.type));
        setText("watchEventMeta", `${GoHomeEdge.fmtDateTime(event.occurred_at)} · ${event.camera_name || cameraLabel(camera)}`);
    }

    function installFullscreen() {
        $("watchFullscreenButton")?.addEventListener("click", async () => {
            const stage = $("watchStage");
            if (!stage?.requestFullscreen) return;
            try {
                if (!document.fullscreenElement) {
                    await stage.requestFullscreen();
                } else {
                    await document.exitFullscreen();
                }
            } catch (_error) {
                // Ignore fullscreen failures on unsupported browsers.
            }
        });
    }

    async function render() {
        if (!window.GoHomeEdge) return;
        try {
            await GoHomeEdge.connect();
            const [user, families, device, cameras, profilesPayload] = await Promise.all([
                GoHomeEdge.currentUser(),
                GoHomeEdge.myFamilies(),
                GoHomeEdge.appDevice(),
                GoHomeEdge.appCameras(),
                GoHomeEdge.v1VideoProfiles(),
            ]);
            if (!user) throw new Error("请先登录");
            const family = families[0] || null;
            if (!family) throw new Error("请先创建家庭");
            state.device = device;
            state.cameras = cameras.filter((item) => item.enabled !== false);
            state.profiles = normalizeProfiles(profilesPayload).filter((item) => ["mobile", "monitor", "detail"].includes(item.id));
            state.selectedProfile = state.profiles.some((item) => item.id === GoHomeEdge.preferredVideoProfile({ scene: "watch" }))
                ? GoHomeEdge.preferredVideoProfile({ scene: "watch" })
                : (state.profiles[0]?.id || "mobile");
            const requested = requestedCameraId();
            state.selectedCameraId = state.cameras.some((item) => Number(item.id) === Number(requested))
                ? requested
                : (preferredCamera(state.cameras)?.id || null);
            syncSelectedCameraParam(state.selectedCameraId);
            renderCameraList();
            renderProfileList();
            renderHeader();
            await attachStream();
            await loadLatestEvent();
        } catch (error) {
            if (error?.status === 401) {
                GoHomeEdge.clearAuthToken();
                window.location.href = GoHomeEdge.loginHref(GoHomeEdge.currentPagePath());
                return;
            }
            state.cameras = [];
            renderCameraList();
            renderProfileList();
            applyStageState("error", error.message || "页面暂时无法连接");
            setText("watchFact", error.message || "页面暂时无法连接");
            setText("watchMeta", "请先确认登录态和本机服务");
            setText("watchEventTitle", "等待恢复");
            setText("watchEventMeta", "连接恢复后自动刷新");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        installFullscreen();
        render();
        setInterval(() => {
            loadLatestEvent().catch(() => {});
        }, 10000);
    });

    window.addEventListener("beforeunload", () => {
        state.streamController?.dispose();
    });
})();
