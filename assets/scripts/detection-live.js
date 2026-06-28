(function () {
    const state = {
        cameras: [],
        selectedCameraId: null,
        detectorBackend: "basic",
        latestSnapshot: null,
        refreshInFlight: false,
        toastTimer: null,
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

    function fmtNumber(value, digits = 1) {
        if (value === null || value === undefined || value === "") return "-";
        const number = Number(value);
        return Number.isFinite(number) ? number.toFixed(digits) : "-";
    }

    function fmtMotion(value) {
        if (value === null || value === undefined || value === "") return "-";
        const number = Number(value);
        if (!Number.isFinite(number)) return "-";
        return number < 0.01 ? number.toFixed(4) : number.toFixed(2);
    }

    function fmtDuration(seconds) {
        if (seconds === null || seconds === undefined) return "-";
        const value = Number(seconds);
        if (!Number.isFinite(value)) return "-";
        if (value < 60) return `${Math.max(0, Math.round(value))}秒`;
        if (value < 3600) return `${Math.floor(value / 60)}分`;
        return `${Math.floor(value / 3600)}小时`;
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function showToast(message) {
        const toast = $("detectionToast");
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add("show");
        clearTimeout(state.toastTimer);
        state.toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
    }

    function setBusy(button, busy) {
        if (!button) return;
        button.disabled = busy;
        button.dataset.originalText ??= button.innerHTML;
        button.innerHTML = busy
            ? '<span class="material-symbols-outlined text-[18px]">progress_activity</span>处理中'
            : button.dataset.originalText;
    }

    function isLocalCamera(camera) {
        const streamUrl = String(camera?.stream_url || "").toLowerCase();
        return /^(local|webcam|device|camera):/.test(streamUrl) || /^\d+$/.test(streamUrl);
    }

    function cameraScore(camera) {
        return (camera.enabled ? 100 : 0) + (camera.status === "online" ? 30 : 0) + (isLocalCamera(camera) ? 0 : 20);
    }

    function preferredCamera(cameras) {
        return [...cameras].sort((a, b) => cameraScore(b) - cameraScore(a) || Number(b.id) - Number(a.id))[0] || null;
    }

    function selectedCamera() {
        return state.cameras.find((camera) => Number(camera.id) === Number(state.selectedCameraId)) || null;
    }

    function statusLabel(status) {
        if (status === "online") return "在线";
        if (status === "offline") return "离线";
        if (status === "error") return "错误";
        return "未知";
    }

    function statusTone(status) {
        if (status === "online") return "good";
        if (status === "offline" || status === "error") return "warn";
        return "muted";
    }

    function tagLabel(tag) {
        const labels = {
            black_screen: "黑屏/遮挡",
            low_motion: "低变化",
            person_detected: "检测到人",
            no_person_detected: "暂未检测到人",
            fall_candidate: "疑似跌倒候选",
        };
        return labels[tag] || tag;
    }

    function snapshotPeople(snapshot) {
        const people = snapshot?.analysis?.people;
        return Array.isArray(people) ? people : [];
    }

    function imageFitRect(snapshot) {
        const stage = $("detectionStage");
        const image = $("detectionSnapshotImage");
        const stageWidth = stage.clientWidth;
        const stageHeight = stage.clientHeight;
        const imageWidth = Number(snapshot?.width || image.naturalWidth || snapshot?.analysis?.image_width || 0);
        const imageHeight = Number(snapshot?.height || image.naturalHeight || snapshot?.analysis?.image_height || 0);
        if (!stageWidth || !stageHeight || !imageWidth || !imageHeight) return null;

        const scale = Math.min(stageWidth / imageWidth, stageHeight / imageHeight);
        const width = imageWidth * scale;
        const height = imageHeight * scale;
        return {
            left: (stageWidth - width) / 2,
            top: (stageHeight - height) / 2,
            width,
            height,
            imageWidth,
            imageHeight,
        };
    }

    function renderDetectionOverlay(snapshot) {
        const overlay = $("detectionOverlay");
        const people = snapshotPeople(snapshot);
        const rect = imageFitRect(snapshot);
        if (!snapshot || !rect || !people.length) {
            overlay.innerHTML = "";
            overlay.removeAttribute("style");
            return;
        }

        overlay.style.left = `${rect.left}px`;
        overlay.style.top = `${rect.top}px`;
        overlay.style.width = `${rect.width}px`;
        overlay.style.height = `${rect.height}px`;
        overlay.innerHTML = people.map((person, index) => {
            const [x1, y1, x2, y2] = person.bbox || [0, 0, 0, 0];
            const left = clamp((Number(x1) / rect.imageWidth) * 100, 0, 100);
            const top = clamp((Number(y1) / rect.imageHeight) * 100, 0, 100);
            const right = clamp((Number(x2) / rect.imageWidth) * 100, 0, 100);
            const bottom = clamp((Number(y2) / rect.imageHeight) * 100, 0, 100);
            const width = clamp(right - left, 0, 100 - left);
            const height = clamp(bottom - top, 0, 100 - top);
            const confidence = person.confidence ? ` · ${Math.round(person.confidence * 100)}%` : "";
            const label = person.fall_candidate ? `人 ${index + 1}${confidence} · 疑似跌倒` : `人 ${index + 1}${confidence}`;
            return `
                <div class="app-detection-box ${person.fall_candidate ? "fall" : ""}" style="left:${left}%;top:${top}%;width:${width}%;height:${height}%">
                    <span>${escapeHtml(label)}</span>
                </div>
            `;
        }).join("");
    }

    function renderDevice(device) {
        state.detectorBackend = device.detector_backend || "basic";
        const yoloEnabled = state.detectorBackend === "yolo";
        setText("detectionStatusBadge", device.worker_running ? "服务在线" : "服务暂停");
        setText("detectionBackend", yoloEnabled ? "YOLO" : "basic");
        setText("detectionCapabilityBadge", yoloEnabled ? "YOLO 可用" : "基础检测");
        setText("detectionPersonCapability", yoloEnabled ? "当前由 YOLO 人数结果执行。" : "需要以 YOLO 模式启动。");
        setText("detectionFallCapability", yoloEnabled ? "当前由 YOLO 人框比例执行。" : "需要以 YOLO 模式启动。");
        $("detectionPersonBadge").textContent = yoloEnabled ? "可用" : "待启用";
        $("detectionPersonBadge").className = `app-mini-pill ${yoloEnabled ? "good" : "muted"} not-italic`;
        $("detectionFallBadge").textContent = yoloEnabled ? "可用" : "待启用";
        $("detectionFallBadge").className = `app-mini-pill ${yoloEnabled ? "good" : "muted"} not-italic`;
    }

    function renderCameraList() {
        const list = $("detectionCameraList");
        setText("detectionCameraCount", state.cameras.length ? `${state.cameras.length} 路` : "未接入");

        if (!state.cameras.length) {
            list.innerHTML = `
                <div class="rounded-2xl bg-[#fbfbff] px-4 py-4 border border-outline-variant/10 text-center">
                    <p class="font-sans text-[13px] font-semibold text-on-surface">还没有摄像头</p>
                    <p class="font-sans text-[12px] text-on-surface-variant mt-1">先接入 local:0 或 RTSP 摄像头。</p>
                </div>
            `;
            return;
        }

        list.innerHTML = state.cameras.map((camera) => {
            const active = Number(camera.id) === Number(state.selectedCameraId);
            const typeLabel = isLocalCamera(camera) ? "本机" : "局域网";
            return `
                <button class="app-camera-option ${active ? "active" : ""} ${camera.enabled ? "" : "disabled"}" type="button" data-camera-id="${camera.id}">
                    <span>
                        <strong>${escapeHtml(camera.name || "摄像头")} · ${escapeHtml(camera.room || "未设置")}</strong>
                        <span>${escapeHtml(typeLabel)} · ${escapeHtml(camera.stream_url || "-")}${camera.last_error ? ` · ${escapeHtml(camera.last_error)}` : ""}</span>
                    </span>
                    <em class="app-mini-pill ${statusTone(camera.status)} not-italic">${statusLabel(camera.status)}</em>
                </button>
            `;
        }).join("");
    }

    function renderSnapshot(snapshot) {
        state.latestSnapshot = snapshot;
        const camera = selectedCamera();
        const analysis = snapshot?.analysis || {};
        const people = snapshotPeople(snapshot);
        const personCount = snapshot?.person_count ?? analysis.person_count;
        const tags = Array.isArray(snapshot?.tags) ? snapshot.tags : [];
        const fallCandidate = Boolean(analysis.fall_candidate || tags.includes("fall_candidate") || people.some((person) => person.fall_candidate));
        const blackScreen = Boolean(analysis.black_screen || tags.includes("black_screen"));
        const backend = analysis.detector_backend || state.detectorBackend || "basic";
        const motion = analysis.motion_score ?? snapshot?.motion_score;
        const brightness = analysis.brightness ?? snapshot?.brightness;

        const image = $("detectionSnapshotImage");
        if (snapshot?.image_url) {
            image.onload = () => renderDetectionOverlay(state.latestSnapshot);
            image.src = `${GoHomeEdge.edgeUrl(snapshot.image_url)}?t=${Date.now()}`;
            $("detectionEmpty").classList.add("hidden");
        } else {
            renderEmptySnapshot();
            return;
        }

        setText("detectionRoom", camera?.room || camera?.name || "摄像头");
        setText("detectionTime", `${GoHomeEdge.fmtTime(snapshot.captured_at)} 更新`);
        setText("detectionBackend", backend === "yolo" ? "YOLO" : backend);
        setText("detectionPeople", personCount === null || personCount === undefined ? "-" : personCount);
        setText("detectionBoxes", people.length ? people.length : "-");
        setText("detectionBrightness", fmtNumber(brightness, 0));
        setText("detectionMotion", fmtMotion(motion));

        if (fallCandidate) {
            setText("detectionTitle", "命中疑似跌倒候选");
            setText("detectionSubtitle", "检测框和规则同时需要人工确认，建议去事件页查看证据。");
            setText("detectionStatusBadge", "需要确认");
        } else if (blackScreen) {
            setText("detectionTitle", "画面疑似黑屏或遮挡");
            setText("detectionSubtitle", "亮度或画面质量异常，先确认摄像头位置和网络。");
            setText("detectionStatusBadge", "画面异常");
        } else if (backend === "yolo") {
            setText("detectionTitle", people.length ? "YOLO 检测框已叠加" : "YOLO 正在观察画面");
            setText("detectionSubtitle", tags.length ? `标签：${tags.map(tagLabel).join("、")}` : "当前画面未命中高优先级规则。");
            setText("detectionStatusBadge", "检测中");
        } else {
            setText("detectionTitle", "基础视觉检测运行中");
            setText("detectionSubtitle", "当前主要判断黑屏、画面变化和摄像头连通性。");
            setText("detectionStatusBadge", "基础检测");
        }

        renderDetectionOverlay(snapshot);
    }

    function renderEmptySnapshot() {
        state.latestSnapshot = null;
        $("detectionOverlay").innerHTML = "";
        $("detectionOverlay").removeAttribute("style");
        $("detectionEmpty").classList.remove("hidden");
        setText("detectionTime", "等待截图");
        setText("detectionPeople", "-");
        setText("detectionBoxes", "-");
        setText("detectionBrightness", "-");
        setText("detectionMotion", "-");
    }

    function renderEvaluation(evaluation) {
        const candidates = Array.isArray(evaluation?.candidates) ? evaluation.candidates : [];
        const evalState = evaluation?.state || {};
        const hasCandidates = candidates.length > 0;
        const badge = $("detectionRuleBadge");
        badge.textContent = hasCandidates ? `${candidates.length} 个候选` : "未命中规则";
        badge.className = `app-mini-pill ${hasCandidates ? "warn" : "good"}`;
        setText(
            "detectionRuleSummary",
            hasCandidates
                ? candidates.map((candidate) => candidate.summary).join("；")
                : "当前检测结果没有生成告警候选。"
        );
        setText("detectionNoPerson", fmtDuration(evalState.no_person_seconds));
        setText("detectionNoMotion", fmtDuration(evalState.no_motion_seconds));
        setText("detectionEvalTime", GoHomeEdge.fmtTime(evaluation?.evaluated_at));
    }

    function renderEmptyEvaluation() {
        const badge = $("detectionRuleBadge");
        badge.textContent = "等待规则";
        badge.className = "app-mini-pill muted";
        setText("detectionRuleSummary", "后台 worker 还没有给这个摄像头生成规则评估，抓帧或等待下一轮抽帧。");
        setText("detectionNoPerson", "-");
        setText("detectionNoMotion", "-");
        setText("detectionEvalTime", "-");
    }

    async function loadEvaluation(cameraId) {
        const evaluation = await GoHomeEdge.latestEvaluation(cameraId);
        renderEvaluation(evaluation);
    }

    async function loadCurrentSnapshot() {
        if (!state.selectedCameraId || state.refreshInFlight) return;
        state.refreshInFlight = true;
        try {
            const snapshot = await GoHomeEdge.latestSnapshot(state.selectedCameraId);
            renderSnapshot(snapshot);
            await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
        } catch (error) {
            renderEmptySnapshot();
            renderEmptyEvaluation();
            if (error?.message) setText("detectionSubtitle", error.message);
        } finally {
            state.refreshInFlight = false;
        }
    }

    async function refreshAll() {
        if (!window.GoHomeEdge) return;
        try {
            await GoHomeEdge.connect();
            const [device, cameras] = await Promise.all([GoHomeEdge.device(), GoHomeEdge.cameras()]);
            renderDevice(device);
            state.cameras = cameras;
            const current = selectedCamera();
            if (!current) {
                state.selectedCameraId = preferredCamera(cameras)?.id || null;
            }
            renderCameraList();

            if (state.selectedCameraId) {
                await loadCurrentSnapshot();
            } else {
                setText("detectionTitle", "还没有摄像头");
                setText("detectionSubtitle", "先接入摄像头，再查看检测框和规则命中情况。");
                setText("detectionStatusBadge", "未接入");
                renderEmptySnapshot();
                renderEmptyEvaluation();
            }
        } catch (error) {
            setText("detectionTitle", "本机服务未连接");
            setText("detectionSubtitle", "启动 edge-agent 后，这里会显示真实检测结果。");
            setText("detectionStatusBadge", "未连接");
            renderEmptySnapshot();
            renderEmptyEvaluation();
            showToast(error.message || "本机守护服务未连接");
        }
    }

    async function captureSelected(button) {
        if (!state.selectedCameraId) {
            showToast("请先选择摄像头");
            return;
        }
        setBusy(button, true);
        try {
            const result = await GoHomeEdge.capture(state.selectedCameraId);
            renderSnapshot(result.snapshot || result);
            await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
            showToast("已抓取最新画面");
        } finally {
            setBusy(button, false);
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        $("detectionCameraList").addEventListener("click", async (event) => {
            const button = event.target.closest("button[data-camera-id]");
            if (!button) return;
            state.selectedCameraId = Number(button.dataset.cameraId);
            renderCameraList();
            await loadCurrentSnapshot();
        });

        $("detectionRefreshButton").addEventListener("click", () => {
            refreshAll().catch((error) => showToast(error.message));
        });

        $("detectionCaptureButton").addEventListener("click", (event) => {
            captureSelected(event.currentTarget).catch((error) => showToast(error.message));
        });

        window.addEventListener("resize", () => renderDetectionOverlay(state.latestSnapshot));
        refreshAll();
        setInterval(loadCurrentSnapshot, 8000);
    });
})();
