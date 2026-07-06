(function () {
    const $ = (id) => document.getElementById(id);
    const state = {
        cameras: [],
        selectedCameraId: null,
        streamController: null,
        streamControllers: new Map(),
        streamImage: null,
        streamState: "idle",
    };

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function cameraDomId(prefix, camera) {
        return `${prefix}-${String(camera?.id || "unknown").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    }

    function cameraLabel(camera) {
        return [camera?.room, camera?.name]
            .filter(Boolean)
            .filter((value, itemIndex, values) => values.indexOf(value) === itemIndex)
            .join(" · ") || "摄像头";
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function pageHref(path) {
        return window.GoHomeEdge?.pageHref?.(path) || path;
    }

    function cameraSuffix(camera) {
        return camera?.id ? `?camera_id=${encodeURIComponent(camera.id)}` : "";
    }

    function statusLabel(status) {
        if (status === "online") return "在线";
        if (status === "offline") return "离线";
        if (status === "disabled") return "未启用";
        return "待同步";
    }

    function statusTone(status) {
        if (status === "online") return "good";
        if (status === "offline") return "warn";
        return "muted";
    }

    function statusText(camera) {
        if (!camera) return "等待接入摄像头";
        if (camera.status === "online") return "盒子在线，等待 App API 返回画面帧";
        if (camera.status === "offline") return camera.last_error || "家庭盒子暂未回传画面";
        if (!camera.has_stream_config) return "还缺少 RTSP / 摄像头接入信息";
        return "等待家庭盒子同步配置并完成本地接入";
    }

    function snapshotMessage(snapshot) {
        const tags = snapshot.tags || [];
        if (tags.includes("black_screen")) return "画面疑似黑屏或遮挡，建议打开详情确认一下";
        if (tags.includes("fall_candidate")) return "检测到疑似跌倒姿态，建议立即确认";
        if (snapshot.person_count !== null && snapshot.person_count !== undefined) {
            return snapshot.person_count > 0
                ? `当前画面检测到 ${snapshot.person_count} 个人，未发现高优先级异常`
                : "当前画面暂未检测到人，持续观察中";
        }
        return "家庭盒子正在检测画面变化";
    }

    function statusTitle(snapshot) {
        const tags = snapshot.tags || [];
        if (tags.includes("black_screen") || tags.includes("fall_candidate")) return "需要确认";
        return "暂无异常";
    }

    function applyStreamState(camera, nextState) {
        state.streamState = nextState;
        if (nextState === "playing") {
            setText("edgeStatusTitle", "实时画面已返回");
            setText("edgeStatusText", "App API 已经从家庭盒子拿到实时画面帧。");
            setText("edgeUpdateTime", "实时画面");
            setText("edgeStreamLabel", "实时画面已返回");
            setText("edgeMainMessage", "实时画面已返回。");
            setText("edgeFact", "画面在线");
            setText("edgeFeeling", "继续观察");
            setText("edgeNext", "看事件");
            setText("edgeBrightness", "实时帧");
            setPillTone("edgeFeeling", "good");
            setPillTone("edgeNext", "muted");
            return;
        }
        if (nextState === "waiting") {
            setText("edgeStatusTitle", "等待画面帧");
            setText("edgeStatusText", "盒子在线，但 App API 暂未收到第一帧。");
            setText("edgeUpdateTime", "等待第一帧");
            setText("edgeStreamLabel", "等待第一帧");
            setText("edgeMainMessage", "盒子在线，但 App API 暂未收到第一帧。");
            return;
        }
        if (nextState === "loading") {
            setText("edgeStatusTitle", "正在连接画面");
            setText("edgeStatusText", "正在通过 App API 请求家庭盒子实时画面。");
            setText("edgeUpdateTime", "连接中");
            setText("edgeStreamLabel", "连接中");
            setText("edgeMainMessage", "正在请求实时画面...");
            return;
        }
        if (nextState === "error") {
            setText("edgeStatusTitle", camera?.status === "online" ? "画面暂时断开" : "摄像头离线");
            setText("edgeStatusText", camera?.status === "online" ? "画面请求失败，正在重试。" : "摄像头当前不在线。");
            setText("edgeUpdateTime", "重连中");
            setText("edgeStreamLabel", "重连中");
            setText("edgeMainMessage", "画面请求失败，正在重试。");
        }
    }

    function setPillTone(id, tone) {
        const node = $(id);
        if (!node) return;
        node.className = `app-mini-pill ${tone}`;
    }

    function preferredCamera(cameras) {
        return [...cameras].sort((a, b) => {
            const score = (camera) => (
                (camera.enabled !== false ? 100 : 0) +
                (camera.status === "online" ? 30 : 0)
            );
            return score(b) - score(a) || Number(b.id) - Number(a.id);
        })[0] || null;
    }

    function requestedCameraId() {
        const value = new URLSearchParams(window.location.search).get("camera_id");
        return value ? Number(value) : null;
    }

    function selectedCamera() {
        return state.cameras.find((camera) => Number(camera.id) === Number(state.selectedCameraId)) || null;
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
        const camera = selectedCamera();
        const suffix = camera?.id ? `?camera_id=${encodeURIComponent(camera.id)}` : "";
        const watchHref = pageHref(`watch.html${suffix}`);
        const detectionHref = pageHref(`detection.html${suffix}`);
        const eventsHref = pageHref(`events.html${suffix}`);
        const camerasHref = pageHref("cameras.html");
        const watchTop = $("edgeMonitorWatchTopLink");
        const watchPreview = $("edgeMonitorWatchPreviewLink");
        const detectionLink = $("edgeMonitorDetectionLink");
        const eventsLink = $("edgeMonitorEventsLink");
        const eventsNavLink = $("edgeMonitorNavEventsLink");
        const deviceLink = $("edgeMonitorDeviceLink");
        if (watchTop) watchTop.href = watchHref;
        if (watchPreview) watchPreview.href = watchHref;
        if (detectionLink) detectionLink.href = detectionHref;
        if (eventsLink) eventsLink.href = eventsHref;
        if (eventsNavLink) eventsNavLink.href = eventsHref;
        if (deviceLink) deviceLink.href = camerasHref;
    }

    function emptyCameraGrid() {
        return `
            <div class="bg-surface-container-lowest rounded-xl ambient-shadow p-5 md:col-span-2">
                <div class="flex items-start gap-4">
                    <div class="w-12 h-12 rounded-full bg-primary-fixed flex items-center justify-center shrink-0">
                        <span class="material-symbols-outlined text-on-primary-fixed-variant">linked_camera</span>
                    </div>
                    <div class="min-w-0 flex-1">
                        <h4 id="edgeCameraRoom" class="font-headline-md text-headline-md text-on-background">还没有接入摄像头</h4>
                        <p id="edgeUpdateTime" class="font-body-md text-sm text-on-surface-variant mt-1">App 提交配置后，家庭盒子会自动同步。</p>
                        <p id="edgeMainMessage" class="font-body-md text-body-md text-on-surface mt-3">先在设备管理里添加摄像头接入信息。</p>
                        <div class="flex flex-wrap gap-2 mt-4">
                            <span id="edgeFact" class="app-mini-pill muted">未接入</span>
                            <span id="edgeFeeling" class="app-mini-pill muted">待接入</span>
                            <span id="edgeNext" class="app-mini-pill warn">添加摄像头</span>
                            <span id="edgeBrightness" class="app-mini-pill muted">等待画面</span>
                        </div>
                        <div class="grid grid-cols-2 gap-2 mt-5">
                            <a class="min-h-11 inline-flex items-center justify-center rounded-full bg-primary text-on-primary font-label-md text-label-md" href="${pageHref("connect.html")}">添加摄像头</a>
                            <a class="min-h-11 inline-flex items-center justify-center rounded-full bg-surface-container-low text-on-surface font-label-md text-label-md" href="${pageHref("cameras.html")}">设备管理</a>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    function cameraCard(camera, index, active) {
        const suffix = cameraSuffix(camera);
        const watchHref = pageHref(`watch.html${suffix}`);
        const editHref = pageHref(`connect.html${suffix}`);
        const tone = statusTone(camera.status);
        const imageId = active ? "edgeSnapshotImage" : cameraDomId("edgeSnapshotImage", camera);
        const streamLabelId = active ? "edgeStreamLabel" : cameraDomId("edgeStreamLabel", camera);
        const cameraTitle = cameraLabel(camera);
        const activeAttrs = active
            ? {
                previewId: "edgeMonitorWatchPreviewLink",
                roomId: "edgeCameraRoom",
                updateId: "edgeUpdateTime",
                messageId: "edgeMainMessage",
                factId: "edgeFact",
                feelingId: "edgeFeeling",
                nextId: "edgeNext",
                brightnessId: "edgeBrightness",
            }
            : {};
        return `
            <article class="bg-surface-container-lowest rounded-xl overflow-hidden ambient-shadow relative">
                <a ${activeAttrs.previewId ? `id="${activeAttrs.previewId}"` : ""} href="${watchHref}" class="block aspect-video w-full bg-[#101820] relative overflow-hidden">
                    <img id="${imageId}" class="absolute inset-0 w-full h-full object-cover" alt="${escapeHtml(cameraTitle)}"/>
                    <div class="absolute inset-0 bg-gradient-to-t from-black/62 via-transparent to-black/22 pointer-events-none"></div>
                    <div class="absolute left-3 top-3 rounded-md bg-error text-on-error px-2 py-1 flex items-center gap-1">
                        <div class="w-2 h-2 rounded-full bg-on-error animate-pulse"></div>
                        <span class="font-label-md text-label-md text-xs">LIVE</span>
                    </div>
                    ${active ? `<div class="absolute right-3 top-3 rounded-md bg-primary text-on-primary px-2 py-1 font-label-md text-label-md text-xs">当前查看</div>` : ""}
                    <p id="${streamLabelId}" class="absolute left-3 right-3 bottom-3 text-white font-body-md text-sm">等待画面帧</p>
                </a>
                <div class="p-4 space-y-3">
                    <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0">
                            <h4 ${activeAttrs.roomId ? `id="${activeAttrs.roomId}"` : ""} class="font-headline-md text-headline-md text-on-background truncate">${escapeHtml(cameraTitle)}</h4>
                            <p ${activeAttrs.updateId ? `id="${activeAttrs.updateId}"` : ""} class="font-body-md text-sm text-on-surface-variant">${escapeHtml(statusText(camera))}</p>
                        </div>
                        <span class="app-mini-pill ${tone}">${statusLabel(camera.status)}</span>
                    </div>
                    <p ${activeAttrs.messageId ? `id="${activeAttrs.messageId}"` : ""} class="font-body-md text-[14px] leading-5 text-on-surface">${escapeHtml(statusText(camera))}</p>
                    <div class="flex flex-wrap gap-2">
                        <span ${activeAttrs.factId ? `id="${activeAttrs.factId}"` : ""} class="app-mini-pill muted">等待检测</span>
                        <span ${activeAttrs.feelingId ? `id="${activeAttrs.feelingId}"` : ""} class="app-mini-pill ${tone}">${statusLabel(camera.status)}</span>
                        <span ${activeAttrs.nextId ? `id="${activeAttrs.nextId}"` : ""} class="app-mini-pill muted">继续观察</span>
                        <span ${activeAttrs.brightnessId ? `id="${activeAttrs.brightnessId}"` : ""} class="app-mini-pill muted">等待亮度</span>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <a class="min-h-10 inline-flex items-center justify-center rounded-lg bg-primary-container text-on-primary-container font-label-md text-label-md" href="${editHref}">配置</a>
                        <a class="min-h-10 inline-flex items-center justify-center rounded-lg bg-surface-container-low text-on-surface font-label-md text-label-md" href="${watchHref}">看画面</a>
                    </div>
                </div>
            </article>
        `;
    }

    function renderCameraGrid(camera) {
        const grid = $("edgeMonitorCameraGrid");
        if (!grid) return;
        state.streamController?.dispose();
        state.streamController = null;
        state.streamControllers.forEach((controller) => controller.dispose());
        state.streamControllers.clear();
        if (!state.cameras.length) {
            grid.innerHTML = emptyCameraGrid();
            return;
        }
        grid.innerHTML = state.cameras
            .map((item, index) => cameraCard(item, index, Number(item.id) === Number(camera?.id)))
            .join("");
    }

    async function attachMonitorStream(camera) {
        const image = $("edgeSnapshotImage");
        if (!image || !camera) return;
        if (state.streamImage !== image) {
            state.streamController?.dispose();
            state.streamController = null;
            state.streamImage = image;
        }
        if (!state.streamController) {
            state.streamController = GoHomeEdge.createManagedVideoStream(image, {
                cameraId: camera.id,
                scene: "monitor",
                onStateChange(nextState) {
                    applyStreamState(camera, nextState);
                },
            });
        }
        applyStreamState(camera, "loading");
        state.streamController.setSource(camera.id, { scene: "monitor" });
        image.classList.remove("object-[center_38%]");
    }

    function updateCardStreamLabel(camera, nextState) {
        const label = $(cameraDomId("edgeStreamLabel", camera));
        if (!label) return;
        if (nextState === "playing") label.textContent = "实时画面已返回";
        else if (nextState === "waiting") label.textContent = "等待第一帧";
        else if (nextState === "error") label.textContent = "画面请求失败，正在重试";
        else if (nextState === "loading") label.textContent = "正在连接画面";
        else label.textContent = "等待画面帧";
    }

    function disposeRemovedStreams(activeCameraIds) {
        for (const [cameraId, controller] of state.streamControllers.entries()) {
            if (!activeCameraIds.has(Number(cameraId))) {
                controller.dispose();
                state.streamControllers.delete(cameraId);
            }
        }
    }

    function attachMonitorStreams(cameras, selected) {
        const activeIds = new Set(cameras.map((camera) => Number(camera.id)));
        disposeRemovedStreams(activeIds);
        cameras.forEach((camera) => {
            const imageId = Number(camera.id) === Number(selected?.id)
                ? "edgeSnapshotImage"
                : cameraDomId("edgeSnapshotImage", camera);
            const image = $(imageId);
            if (!image) return;
            const existing = state.streamControllers.get(Number(camera.id));
            if (existing) {
                existing.setSource(camera.id, { scene: "monitor" });
                return;
            }
            const controller = GoHomeEdge.createManagedVideoStream(image, {
                cameraId: camera.id,
                scene: "monitor",
                onStateChange(nextState) {
                    if (Number(camera.id) === Number(selected?.id)) {
                        applyStreamState(camera, nextState);
                    } else {
                        updateCardStreamLabel(camera, nextState);
                    }
                },
            });
            state.streamControllers.set(Number(camera.id), controller);
        });
    }

    async function render() {
        if (!window.GoHomeEdge) return;
        try {
            await GoHomeEdge.connect();
            const [device, cameras] = await Promise.all([GoHomeEdge.appDevice(), GoHomeEdge.appCameras()]);
            state.cameras = cameras.filter((item) => item.enabled !== false);
            const requested = requestedCameraId();
            state.selectedCameraId = state.cameras.some((item) => Number(item.id) === Number(requested))
                ? requested
                : (preferredCamera(state.cameras)?.id || null);
            syncSelectedCameraParam(state.selectedCameraId);
            const camera = selectedCamera();
            renderCameraGrid(camera);
            syncNavLinks();

            setText("edgeDeviceStatus", device.worker_running ? "服务在线" : "服务暂停");
            setText("edgeDetector", device.detector_backend === "yolo" ? "YOLO 检测中" : "基础检测中");

            if (!camera) {
                setText("edgeStatusTitle", "还没有摄像头");
                setText("edgeStatusText", "先在设备管理里添加摄像头接入信息。");
                setText("edgeMainMessage", "还没有接入摄像头");
                setText("edgeFact", "接入摄像头后查看检测细节。");
                setText("edgeFeeling", "待接入");
                setText("edgeNext", "添加摄像头");
                setText("edgeBrightness", "等待画面");
                setPillTone("edgeFeeling", "muted");
                setPillTone("edgeNext", "warn");
                return;
            }

            attachMonitorStreams(state.cameras, camera);
            const snapshot = await GoHomeEdge.appLatestSnapshot(camera.id, { allowMissing: true });
            if (snapshot?.available === false) {
                setText("edgeCameraRoom", cameraLabel(camera));
                if (state.streamState === "playing") {
                    applyStreamState(camera, "playing");
                } else {
                    applyStreamState(camera, camera.status === "online" ? "waiting" : "error");
                    setText("edgeFact", "等待检测摘要");
                    setText("edgeFeeling", "继续观察");
                    setText("edgeNext", "等待下一轮");
                    setText("edgeBrightness", "等待亮度");
                    setPillTone("edgeFeeling", "muted");
                    setPillTone("edgeNext", "muted");
                }
                return;
            }

            setText("edgeCameraRoom", cameraLabel(camera));
            setText("edgeUpdateTime", `${GoHomeEdge.fmtTime(snapshot.captured_at)} 更新`);
            setText("edgeMainMessage", snapshotMessage(snapshot));
            setText("edgeStatusTitle", statusTitle(snapshot));
            setText("edgeStatusText", camera.status === "online" ? "家庭盒子正在运行并回传状态。" : "摄像头当前不在线。");
            setText("edgeFact", snapshot.person_count === null || snapshot.person_count === undefined ? "画面正常" : `${snapshot.person_count} 人`);
            setText("edgeFeeling", (snapshot.tags || []).length ? "需要看一眼" : "家里平稳");
            setText("edgeNext", (snapshot.tags || []).includes("fall_candidate") ? "立即联系" : "继续观察");
            setText("edgeBrightness", `原始亮度 ${Number(snapshot.brightness || 0).toFixed(0)}`);
            setPillTone("edgeFeeling", (snapshot.tags || []).length ? "warn" : "good");
            setPillTone("edgeNext", (snapshot.tags || []).includes("fall_candidate") ? "warn" : "muted");

            const statusIcon = $("edgeStatusIcon");
            if (statusIcon) {
                const alertTone = (snapshot.tags || []).includes("black_screen") || (snapshot.tags || []).includes("fall_candidate");
                statusIcon.className = `app-story-icon ${alertTone ? "warn" : "good"} shrink-0`;
            }
        } catch (error) {
            syncNavLinks();
            if (error?.status === 401) {
                GoHomeEdge.clearAuthToken();
                window.location.href = GoHomeEdge.loginHref(GoHomeEdge.currentPagePath());
                return;
            }
            setText("edgeDeviceStatus", "未连接");
            setText("edgeDetector", "等待服务");
            setText("edgeStatusTitle", "App 服务未连接");
            setText("edgeStatusText", "启动 App API 后，这里会自动读取家庭盒子回传状态。");
            setText("edgeMainMessage", error.message || "App 服务未连接");
            setText("edgeFact", "连接服务后查看检测细节。");
            setText("edgeFeeling", "未连接");
            setText("edgeNext", "启动服务");
            setPillTone("edgeFeeling", "warn");
            setPillTone("edgeNext", "muted");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        render();
        setInterval(render, 8000);
    });

    window.addEventListener("beforeunload", () => {
        state.streamController?.dispose();
    });
})();
