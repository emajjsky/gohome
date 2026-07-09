(function () {
    const state = {
        cameras: [],
        selectedCameraId: null,
        detectorBackend: "basic",
        capabilities: {},
        latestSnapshot: null,
        streamCameraId: null,
        streamController: null,
        refreshInFlight: false,
        toastTimer: null,
    };

    const $ = (id) => document.getElementById(id);

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function boolValue(value, fallback = false) {
        if (value === undefined || value === null || value === "") return fallback;
        if (typeof value === "string") {
            const normalized = value.trim().toLowerCase();
            if (!normalized) return fallback;
            return !["0", "false", "off", "no", "否"].includes(normalized);
        }
        return Boolean(value);
    }

    function backendLabel(backend) {
        if (backend === "yolo") return "人形检测";
        if (backend === "demo") return "基础视觉";
        if (backend === "rtmpose" || backend === "pose") return "姿态检测";
        if (backend === "basic") return "基础检测";
        return "盒子视觉";
    }

    function normalizeCapabilities(raw = {}, backend = "basic") {
        const normalizedBackend = String(raw.backend || backend || "basic").trim().toLowerCase();
        return {
            person_detection: boolValue(raw.person_detection),
            no_person_detection: boolValue(raw.no_person_detection),
            fall_candidate: boolValue(raw.fall_candidate),
            activity_candidate: boolValue(raw.activity_candidate, true),
            fire_candidate: boolValue(raw.fire_candidate, true),
            backend: normalizedBackend,
            backend_label: raw.backend_label || backendLabel(normalizedBackend),
        };
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

    function metricLabel(key) {
        const labels = {
            no_person_seconds: "连续无人",
            no_motion_seconds: "静止时长",
            motion_score: "运动分数",
            brightness: "亮度",
            contrast: "对比度",
            people: "人体框",
        };
        return labels[key] || key;
    }

    function metricValue(key, value) {
        if (value === null || value === undefined || value === "") return "-";
        if (key === "people" && Array.isArray(value)) return `${value.length} 个人体框`;
        if (key.endsWith("_seconds")) return fmtDuration(value);
        if (key === "motion_score") return fmtMotion(value);
        if (key === "brightness" || key === "contrast") return fmtNumber(value, 0);
        if (typeof value === "number") return Number.isInteger(value) ? String(value) : fmtNumber(value, 2);
        return String(value);
    }

    function summarizeMetrics(metrics) {
        const entries = Object.entries(metrics || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
        if (!entries.length) return "";
        return entries.map(([key, value]) => `${metricLabel(key)} ${metricValue(key, value)}`).join("，");
    }

    function matchedRules(evaluation) {
        if (Array.isArray(evaluation?.matched_rules) && evaluation.matched_rules.length) return evaluation.matched_rules;
        return (Array.isArray(evaluation?.candidates) ? evaluation.candidates : [])
            .map((candidate) => candidate?.payload?.rule)
            .filter(Boolean);
    }

    function evaluationSummary(evaluation) {
        const rules = matchedRules(evaluation);
        if (!rules.length) return evaluation?.explanation || "当前检测结果没有生成告警候选。";
        return rules.map((rule) => {
            const parts = [];
            if (rule.reason) parts.push(rule.reason);
            const observed = summarizeMetrics(rule.observed);
            const threshold = summarizeMetrics(rule.threshold);
            if (observed) parts.push(`当前观测：${observed}`);
            if (threshold) parts.push(`规则阈值：${threshold}`);
            return parts.join(" ");
        }).join("；");
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
        const camera = selectedCamera();
        const suffix = camera?.id ? `?camera_id=${encodeURIComponent(camera.id)}` : "";
        const monitorHref = GoHomeEdge.pageHref(`monitor.html${suffix}`) || `monitor.html${suffix}`;
        const watchHref = GoHomeEdge.pageHref(`watch.html${suffix}`) || `watch.html${suffix}`;
        const eventsHref = GoHomeEdge.pageHref(`events.html${suffix}`) || `events.html${suffix}`;
        const monitorNav = $("detectionNavMonitorLink");
        const watchBack = $("detectionBackWatchLink");
        const eventsPrimary = $("detectionPrimaryEventsLink");
        const eventsSecondary = $("detectionSecondaryEventsLink");
        const eventsNav = $("detectionNavEventsLink");
        if (monitorNav) monitorNav.href = monitorHref;
        if (watchBack) watchBack.href = monitorHref;
        if (eventsPrimary) eventsPrimary.href = eventsHref;
        if (eventsSecondary) eventsSecondary.href = eventsHref;
        if (eventsNav) eventsNav.href = eventsHref;
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
        state.capabilities = normalizeCapabilities(device.vision_capabilities || {}, state.detectorBackend);
        const personReady = state.capabilities.person_detection || state.capabilities.no_person_detection;
        const fallReady = state.capabilities.fall_candidate;
        const label = state.capabilities.backend_label || backendLabel(state.detectorBackend);
        setText("detectionStatusBadge", device.worker_running ? "盒子在线" : "盒子暂停");
        setText("detectionBackend", label);
        setText("detectionCapabilityBadge", label);
        setText("detectionPersonCapability", personReady ? "人形和长时间无人规则可用。" : "当前盒子未启用人形模型，人形和无人规则不会执行。");
        setText("detectionFallCapability", fallReady ? "疑似跌倒候选规则可用，命中后进入事件页确认。" : "需要人形或姿态模型后才会开放跌倒候选。");
        $("detectionPersonBadge").textContent = personReady ? "可用" : "需模型";
        $("detectionPersonBadge").className = `app-mini-pill ${personReady ? "good" : "muted"} not-italic`;
        $("detectionFallBadge").textContent = fallReady ? "可用" : "需模型";
        $("detectionFallBadge").className = `app-mini-pill ${fallReady ? "good" : "muted"} not-italic`;
    }

    function renderCameraList() {
        const list = $("detectionCameraList");
        setText("detectionCameraCount", state.cameras.length ? `${state.cameras.length} 路` : "未接入");
        syncNavLinks();

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

    async function renderSnapshot(snapshot) {
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
        if (snapshot?.image_url && state.streamCameraId !== Number(state.selectedCameraId)) {
            image.onload = () => renderDetectionOverlay(state.latestSnapshot);
            image.src = await GoHomeEdge.v1VideoMediaPlaybackUrl(snapshot.image_url);
        }
        $("detectionEmpty").classList.add("hidden");

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
        if (!state.streamCameraId) {
            $("detectionEmpty").classList.remove("hidden");
        }
        setText("detectionTime", "等待截图");
        setText("detectionPeople", "-");
        setText("detectionBoxes", "-");
        setText("detectionBrightness", "-");
        setText("detectionMotion", "-");
    }

    async function attachStream(cameraId) {
        if (!cameraId) return;
        const numericId = Number(cameraId);
        const image = $("detectionSnapshotImage");
        if (!image) return;
        if (!state.streamController) {
            state.streamController = GoHomeEdge.createManagedVideoStream(image, {
                cameraId: numericId,
                scene: "detection",
                onStateChange(nextState) {
                    if (nextState === "playing") {
                        state.streamCameraId = Number(state.selectedCameraId);
                        $("detectionEmpty").classList.add("hidden");
                        renderDetectionOverlay(state.latestSnapshot);
                        return;
                    }
                    if (nextState === "error") {
                        state.streamCameraId = null;
                        renderDetectionOverlay(state.latestSnapshot);
                        $("detectionEmpty").classList.remove("hidden");
                    }
                },
            });
        }
        if (state.streamCameraId === numericId) return;
        state.streamCameraId = numericId;
        $("detectionEmpty").classList.add("hidden");
        image.onload = () => renderDetectionOverlay(state.latestSnapshot);
        image.onerror = () => {
            if (state.streamCameraId === numericId) {
                state.streamCameraId = null;
                renderDetectionOverlay(state.latestSnapshot);
                $("detectionEmpty").classList.remove("hidden");
            }
        };
        state.streamController.setSource(numericId, { scene: "detection" });
    }

    function detachStream() {
        state.streamCameraId = null;
        state.streamController?.setSource(null);
    }

    function renderEvaluation(evaluation) {
        const candidates = Array.isArray(evaluation?.candidates) ? evaluation.candidates : [];
        const evalState = evaluation?.state || {};
        const hasCandidates = candidates.length > 0;
        const cameraState = String(evalState.camera_state || evalState.camera_status || "").toLowerCase();
        const badge = $("detectionRuleBadge");
        badge.textContent = hasCandidates ? `${candidates.length} 个候选` : (cameraState === "online" ? "未命中规则" : "等待规则");
        badge.className = `app-mini-pill ${hasCandidates ? "warn" : (cameraState === "online" ? "good" : "muted")}`;
        setText(
            "detectionRuleSummary",
            evaluationSummary(evaluation)
        );
        setText("detectionNoPerson", fmtDuration(evalState.no_person_seconds));
        setText("detectionNoMotion", fmtDuration(evalState.no_motion_seconds));
        setText("detectionEvalTime", GoHomeEdge.fmtTime(evaluation?.evaluated_at));
    }

    function renderEmptyEvaluation() {
        const badge = $("detectionRuleBadge");
        badge.textContent = "等待规则";
        badge.className = "app-mini-pill muted";
        setText("detectionRuleSummary", "等待家庭盒子回传这路摄像头的检测状态。");
        setText("detectionNoPerson", "-");
        setText("detectionNoMotion", "-");
        setText("detectionEvalTime", "-");
    }

    async function loadEvaluation(cameraId) {
        const evaluation = await GoHomeEdge.appLatestEvaluation(cameraId);
        renderEvaluation(evaluation);
        return evaluation;
    }

    function renderEvaluationHeader(evaluation) {
        const cameraState = String(evaluation?.state?.camera_state || evaluation?.state?.camera_status || "").toLowerCase();
        const candidates = Array.isArray(evaluation?.candidates) ? evaluation.candidates : [];
        if (candidates.length) {
            setText("detectionTitle", "命中需要确认的候选");
            setText("detectionSubtitle", evaluationSummary(evaluation));
            setText("detectionStatusBadge", "需要确认");
            return;
        }
        if (cameraState === "online") {
            setText("detectionTitle", "摄像头在线，暂无异常");
            setText("detectionSubtitle", evaluationSummary(evaluation));
            setText("detectionStatusBadge", "当前平稳");
            if (evaluation?.evaluated_at) setText("detectionTime", `${GoHomeEdge.fmtTime(evaluation.evaluated_at)} 同步`);
            return;
        }
        setText("detectionTitle", "等待检测状态");
        setText("detectionSubtitle", evaluationSummary(evaluation));
        setText("detectionStatusBadge", "等待同步");
    }

    async function loadCurrentSnapshot() {
        if (!state.selectedCameraId || state.refreshInFlight) return;
        state.refreshInFlight = true;
        try {
            await attachStream(state.selectedCameraId);
            const snapshot = await GoHomeEdge.appLatestSnapshot(state.selectedCameraId, { allowMissing: true });
            if (snapshot?.available === false) {
                renderEmptySnapshot();
                const evaluation = await loadEvaluation(state.selectedCameraId).catch(() => null);
                if (evaluation) {
                    renderEvaluationHeader(evaluation);
                } else {
                    renderEmptyEvaluation();
                    setText("detectionTitle", "等待检测状态");
                    setText("detectionSubtitle", "家庭盒子在线后会回传这路摄像头的检测状态。");
                    setText("detectionStatusBadge", "等待同步");
                }
            } else {
                await renderSnapshot(snapshot);
                await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
            }
        } catch (error) {
            detachStream();
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
            const [device, cameras] = await Promise.all([GoHomeEdge.appDevice(), GoHomeEdge.appCameras()]);
            renderDevice(device);
            state.cameras = cameras;
            const current = selectedCamera();
            if (!current) {
                const requested = requestedCameraId();
                state.selectedCameraId = state.cameras.some((item) => Number(item.id) === Number(requested))
                    ? requested
                    : (preferredCamera(cameras)?.id || null);
                syncSelectedCameraParam(state.selectedCameraId);
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
            if (error?.status === 401) {
                GoHomeEdge.clearAuthToken();
                window.location.href = GoHomeEdge.loginHref(GoHomeEdge.currentPagePath());
                return;
            }
            setText("detectionTitle", "本机服务未连接");
            setText("detectionSubtitle", "启动家庭盒子服务后，这里会显示真实检测结果。");
            setText("detectionStatusBadge", "未连接");
            detachStream();
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
            state.streamCameraId = null;
            await renderSnapshot(result.snapshot || result);
            await attachStream(state.selectedCameraId);
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
            syncSelectedCameraParam(state.selectedCameraId);
            state.streamCameraId = null;
            renderCameraList();
            await loadCurrentSnapshot();
        });

        $("detectionRefreshButton").addEventListener("click", () => {
            state.streamCameraId = null;
            refreshAll().catch((error) => showToast(error.message));
        });

        $("detectionCaptureButton").addEventListener("click", (event) => {
            captureSelected(event.currentTarget).catch((error) => showToast(error.message));
        });

        window.addEventListener("resize", () => renderDetectionOverlay(state.latestSnapshot));
        refreshAll();
        setInterval(loadCurrentSnapshot, 8000);
    });

    window.addEventListener("beforeunload", () => {
        state.streamController?.dispose();
    });
})();
