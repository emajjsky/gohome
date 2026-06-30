(function () {
    const $ = (id) => document.getElementById(id);
    const state = {
        cameras: [],
        selectedCameraId: null,
        streamController: null,
    };

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
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
        return "本机守护服务正在检测画面变化";
    }

    function statusTitle(snapshot) {
        const tags = snapshot.tags || [];
        if (tags.includes("black_screen") || tags.includes("fall_candidate")) return "需要确认";
        return "暂无异常";
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
        const watchHref = GoHomeEdge.pageHref(`watch.html${suffix}`) || `watch.html${suffix}`;
        const detectionHref = GoHomeEdge.pageHref(`detection.html${suffix}`) || `detection.html${suffix}`;
        const eventsHref = GoHomeEdge.pageHref(`events.html${suffix}`) || `events.html${suffix}`;
        const watchTop = $("edgeMonitorWatchTopLink");
        const watchPreview = $("edgeMonitorWatchPreviewLink");
        const detectionLink = $("edgeMonitorDetectionLink");
        const eventsLink = $("edgeMonitorEventsLink");
        const eventsNavLink = $("edgeMonitorNavEventsLink");
        if (watchTop) watchTop.href = watchHref;
        if (watchPreview) watchPreview.href = watchHref;
        if (detectionLink) detectionLink.href = detectionHref;
        if (eventsLink) eventsLink.href = eventsHref;
        if (eventsNavLink) eventsNavLink.href = eventsHref;
    }

    async function attachMonitorStream(camera) {
        const image = $("edgeSnapshotImage");
        if (!image || !camera) return;
        if (!state.streamController) {
            state.streamController = GoHomeEdge.createManagedVideoStream(image, {
                cameraId: camera.id,
                scene: "monitor",
            });
        }
        state.streamController.setSource(camera.id, { scene: "monitor" });
        image.classList.remove("object-[center_38%]");
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
            syncNavLinks();
            const camera = selectedCamera();

            setText("edgeDeviceStatus", device.worker_running ? "服务在线" : "服务暂停");
            setText("edgeDetector", device.detector_backend === "yolo" ? "YOLO 检测中" : "基础检测中");

            if (!camera) {
                setText("edgeStatusTitle", "还没有摄像头");
                setText("edgeStatusText", "先在本机守护服务里添加 local:0 或 RTSP 摄像头。");
                setText("edgeMainMessage", "还没有接入摄像头");
                setText("edgeFact", "接入摄像头后查看检测细节。");
                setText("edgeFeeling", "待接入");
                setText("edgeNext", "添加摄像头");
                setPillTone("edgeFeeling", "muted");
                setPillTone("edgeNext", "warn");
                return;
            }

            await attachMonitorStream(camera);
            const snapshot = await GoHomeEdge.appLatestSnapshot(camera.id, { allowMissing: true });
            if (snapshot?.available === false) {
                setText("edgeCameraRoom", camera.room || camera.name || "摄像头");
                setText("edgeUpdateTime", "实时预览中");
                setText("edgeMainMessage", "实时画面已连接，等待后台生成最新检测摘要");
                setText("edgeStatusTitle", "实时预览已恢复");
                setText("edgeStatusText", camera.status === "online" ? "视频流正常，检测摘要会在下一轮抽帧后补上。" : "摄像头当前不在线。");
                setText("edgeFact", "等待检测摘要");
                setText("edgeFeeling", "继续观察");
                setText("edgeNext", "等待下一轮");
                setText("edgeBrightness", "等待亮度");
                setPillTone("edgeFeeling", "muted");
                setPillTone("edgeNext", "muted");
                return;
            }

            setText("edgeCameraRoom", camera.room || camera.name || "摄像头");
            setText("edgeUpdateTime", `${GoHomeEdge.fmtTime(snapshot.captured_at)} 更新`);
            setText("edgeMainMessage", snapshotMessage(snapshot));
            setText("edgeStatusTitle", statusTitle(snapshot));
            setText("edgeStatusText", camera.status === "online" ? "本机守护服务正在运行。" : "摄像头当前不在线。");
            setText("edgeFact", snapshot.person_count === null || snapshot.person_count === undefined ? "画面正常" : `${snapshot.person_count} 人`);
            setText("edgeFeeling", (snapshot.tags || []).length ? "需要看一眼" : "家里平稳");
            setText("edgeNext", (snapshot.tags || []).includes("fall_candidate") ? "立即联系" : "继续观察");
            setText("edgeBrightness", `原始亮度 ${Number(snapshot.brightness || 0).toFixed(0)}`);
            setPillTone("edgeFeeling", (snapshot.tags || []).length ? "warn" : "good");
            setPillTone("edgeNext", (snapshot.tags || []).includes("fall_candidate") ? "warn" : "muted");

            const statusIcon = $("edgeStatusIcon");
            if (statusIcon) {
                const alertTone = (snapshot.tags || []).includes("black_screen") || (snapshot.tags || []).includes("fall_candidate");
                statusIcon.className = `w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${alertTone ? "bg-[#fff4e8] text-[#c87b2a]" : "bg-[#edf6ee] text-[#2d7d5c]"}`;
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
            setText("edgeStatusTitle", "本机服务未连接");
            setText("edgeStatusText", "启动 edge-agent 后，这里会自动切换成真实画面。");
            setText("edgeMainMessage", error.message || "本机守护服务未连接");
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
