(function () {
    const $ = (id) => document.getElementById(id);
    const EVENT_UPDATES_KEY = "gohome.eventUpdates";

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
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

    function syncNavLinks(cameraId) {
        const suffix = cameraId ? `?camera_id=${encodeURIComponent(cameraId)}` : "";
        const monitorHref = GoHomeEdge.pageHref(`monitor.html${suffix}`) || `monitor.html${suffix}`;
        const watchHref = GoHomeEdge.pageHref(`watch.html${suffix}`) || `watch.html${suffix}`;
        const watchLink = $("edgeTimelineWatchLink");
        const monitorLink = $("edgeTimelineMonitorLink");
        const backLink = $("edgeEventsBackLink");
        const monitorNavLink = $("edgeEventsNavMonitorLink");
        if (watchLink) watchLink.href = watchHref;
        if (monitorLink) monitorLink.href = monitorHref;
        if (backLink) backLink.href = monitorHref;
        if (monitorNavLink) monitorNavLink.href = monitorHref;
    }

    function readEventUpdates() {
        try {
            return JSON.parse(sessionStorage.getItem(EVENT_UPDATES_KEY) || "{}");
        } catch (_error) {
            return {};
        }
    }

    function writeEventUpdates(updates) {
        sessionStorage.setItem(EVENT_UPDATES_KEY, JSON.stringify(updates));
    }

    function applyPendingUpdates(events) {
        const updates = readEventUpdates();
        if (!Object.keys(updates).length) return events;
        return events.map((event) => {
            const patch = updates[String(event.id)];
            return patch ? { ...event, ...patch } : event;
        });
    }

    function pruneAppliedUpdates(events) {
        const updates = readEventUpdates();
        let changed = false;
        for (const event of events) {
            const key = String(event.id);
            const patch = updates[key];
            if (!patch) continue;
            if (
                Boolean(event.acknowledged) === Boolean(patch.acknowledged)
                && String(event.resolution || "") === String(patch.resolution || "")
            ) {
                delete updates[key];
                changed = true;
            }
        }
        if (changed) writeEventUpdates(updates);
    }

    function iconTone(event) {
        if (event.level === "critical") return "bg-[#fff0ed] text-[#b85d4c]";
        if (event.type === "black_screen" || event.type === "no_motion") return "bg-[#fff4e8] text-[#c87b2a]";
        return "bg-primary/8 text-primary";
    }

    function fmtMetricValue(key, value) {
        if (value === null || value === undefined || value === "") return "-";
        if (key === "people" && Array.isArray(value)) return `${value.length} 个人体框`;
        if (key.endsWith("_seconds")) {
            const seconds = Math.max(0, Math.round(Number(value) || 0));
            if (seconds < 60) return `${seconds} 秒`;
            if (seconds < 3600) return `${Math.floor(seconds / 60)} 分`;
            return `${(seconds / 3600).toFixed(seconds >= 36000 ? 0 : 1)} 小时`;
        }
        if (key === "motion_score") return Number(value).toFixed(4);
        if (key === "brightness" || key === "contrast") return Number(value).toFixed(0);
        if (typeof value === "number") return Number.isInteger(value) ? String(value) : Number(value).toFixed(2);
        return String(value);
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

    function summarizeMetrics(metrics) {
        const entries = Object.entries(metrics || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
        if (!entries.length) return "";
        return entries.map(([key, value]) => `${metricLabel(key)} ${fmtMetricValue(key, value)}`).join("，");
    }

    function compactEventFacts(event) {
        const evidence = event?.payload?.evidence || {};
        const metrics = evidence.metrics || {};
        const rule = event?.payload?.rule || evidence.rule || {};
        const observed = rule.observed || {};
        const parts = [];

        const people = metrics.person_count ?? observed.person_count;
        const pose = metrics.pose_count ?? observed.pose_count;
        const confirmFrames = observed.confirm_frames ?? observed.confirm_count;
        const fallScore = metrics.fall_score ?? observed.fall_score;
        const fireScore = metrics.fire_score ?? observed.fire_score;

        if (people !== null && people !== undefined) parts.push(`人数 ${people}`);
        if (pose !== null && pose !== undefined) parts.push(`骨架 ${pose}`);
        if (confirmFrames !== null && confirmFrames !== undefined) parts.push(`连续 ${confirmFrames} 帧`);
        if (fallScore !== null && fallScore !== undefined) parts.push(`跌倒 ${Number(fallScore).toFixed(2)}`);
        if (fireScore !== null && fireScore !== undefined) parts.push(`火灾 ${Number(fireScore).toFixed(3)}`);

        return parts.slice(0, 3).join("，");
    }

    function engineeringCopy(text) {
        return /edge[-_ ]?agent|cannot open|network stream|no frame|rtsp|ffmpeg|opencv|traceback|http \d+|failed/i.test(String(text || ""));
    }

    function cleanReason(event, text) {
        const value = String(text || "").trim();
        if (!value) return "";
        if (!engineeringCopy(value)) return value;
        if (event.type === "camera_offline") return "家庭盒子暂时没有拿到这路画面，会继续重试。";
        if (event.type === "black_screen") return "家庭盒子拿到的画面质量异常，需要确认是否遮挡或背光。";
        return "家庭盒子回传了一条需要查看的提醒。";
    }

    function cameraMap(cameras) {
        return new Map((Array.isArray(cameras) ? cameras : []).map((camera) => [Number(camera.id), camera]));
    }

    function isStaleCameraOffline(event, camerasById) {
        if (event?.type !== "camera_offline" || event.acknowledged) return false;
        const camera = camerasById.get(Number(event.camera_id));
        if (!camera || String(camera.status || "").toLowerCase() !== "online") return false;
        const eventTime = Date.parse(event.occurred_at || event.created_at || "");
        const seenTime = Date.parse(camera.last_seen_at || camera.edge_reported_at || camera.updated_at || "");
        return Number.isFinite(eventTime) && Number.isFinite(seenTime) && seenTime >= eventTime;
    }

    function actionText(event) {
        const rule = event?.payload?.rule || {};
        const verification = event?.payload?.verification || {};
        if (event.acknowledged) return "已处理，可以作为记录查看。";
        if (verification.status === "confirmed") return `云端视觉复核支持这条提醒。${verification.result?.reason || "请尽快确认老人状态。"}`;
        if (verification.status === "rejected") return `云端暂未看到明确紧急线索。${verification.result?.reason || "建议结合实时画面确认。"}`;
        if (verification.status === "uncertain") return "云端证据不足，建议人工查看截图和实时画面。";
        if (["pending", "verifying", "retrying"].includes(verification.status)) return "云端正在复核证据，边缘提醒已经生效。";
        if (rule.reason) {
            const reason = cleanReason(event, rule.reason);
            return compactEventFacts(event) ? `${reason} ${compactEventFacts(event)}。` : reason;
        }
        if (event.type === "fall_candidate") return "建议先确认老人状态，再标记处理。";
        if (event.type === "prolonged_floor_lying") return "请立即联系老人或查看实时画面，确认是否需要紧急协助。";
        if (event.type === "camera_offline") return "家庭盒子暂时没有拿到这路画面，会继续重试。";
        if (event.type === "black_screen") return "建议打开截图，看是否遮挡或背光。";
        return "适合现在看一眼。";
    }

    function displaySummary(event) {
        if (!event) return "";
        if (event.type === "camera_offline") {
            return `${event.camera_name || event.room || "摄像头"} 暂时没有返回画面`;
        }
        if (event.type === "black_screen") {
            return `${event.camera_name || event.room || "摄像头"} 画面疑似遮挡或黑屏`;
        }
        if (event.type === "no_motion") {
            return `${event.camera_name || event.room || "摄像头"} 长时间没有明显变化`;
        }
        if (event.type === "no_person") {
            return `${event.camera_name || event.room || "摄像头"} 长时间未检测到人`;
        }
        if (event.type === "fall_candidate") {
            return `${event.camera_name || event.room || "摄像头"} 出现疑似跌倒姿态`;
        }
        if (event.type === "prolonged_floor_lying") {
            return `${event.camera_name || event.room || "摄像头"} 检测到长时间倒地`;
        }
        return cleanReason(event, event.summary) || GoHomeEdge.eventLabel(event.type);
    }

    function renderEvent(event, cameraId) {
        const time = GoHomeEdge.fmtTime(event.occurred_at);
        const label = GoHomeEdge.eventLabel(event.type);
        const room = event.room || event.camera_name || "家里";
        const status = event.acknowledged ? "已处理" : "待确认";
        const suffix = cameraId ? `&camera_id=${encodeURIComponent(cameraId)}` : "";
        const detailHref = GoHomeEdge.pageHref(`event_detail.html?eventId=${event.id}${suffix}`) || `event_detail.html?eventId=${event.id}${suffix}`;
        const statusClass = event.acknowledged
            ? "bg-surface-container-low text-on-surface-variant"
            : "bg-[#fff4e8] text-[#c87b2a]";

        return `
            <a href="${detailHref}" class="gohome-event-card">
                <div class="gohome-event-meta">
                    <span>${time} ${escapeHtml(room)}</span>
                    <span class="px-2.5 py-1 rounded-full ${statusClass} text-[10px] font-semibold">${status}</span>
                </div>
                <div class="gohome-event-body">
                    <div class="gohome-event-icon ${iconTone(event)}">
                        <span class="material-symbols-outlined">${GoHomeEdge.eventIcon(event.type)}</span>
                    </div>
                    <div class="min-w-0">
                        <h3>${escapeHtml(displaySummary(event))}</h3>
                        <p>${label} ${GoHomeEdge.fmtDateTime(event.occurred_at)}</p>
                        <p class="gohome-event-action">${actionText(event)}</p>
                    </div>
                </div>
            </a>
        `;
    }

    function cameraTitle(camera) {
        const room = String(camera.room || "").trim();
        const name = String(camera.name || "").trim();
        if (room && name && room !== name) return `${room} · ${name}`;
        return room || name || `摄像头 ${camera.id}`;
    }

    function cameraStatusText(camera, evaluation) {
        const status = String(camera.status || evaluation?.state?.camera_state || "").toLowerCase();
        if (camera.enabled === false) return "已停用";
        if (status === "online") return "在线";
        if (status === "pending_edge_sync") return "待同步";
        if (status === "pending_edge_setup") return "待配置";
        return status ? "待确认" : "等待回传";
    }

    function cameraStatusClass(camera, evaluation) {
        const status = String(camera.status || evaluation?.state?.camera_state || "").toLowerCase();
        if (camera.enabled === false) return "muted";
        if (status === "online") return "ok";
        return "warn";
    }

    function evaluationText(camera, evaluation) {
        if (evaluation?.candidates?.length) return `${evaluation.candidates.length} 条候选待核对`;
        if (evaluation?.explanation) return cleanReason({ type: "camera_offline" }, evaluation.explanation);
        if (String(camera.status || "").toLowerCase() === "online") return "摄像头在线，最近没有命中需要确认的规则。";
        return "等待家庭盒子回传检测状态。";
    }

    function renderCameraCheck(camera, evaluation) {
        const statusClass = cameraStatusClass(camera, evaluation);
        const status = cameraStatusText(camera, evaluation);
        const evaluatedAt = evaluation?.evaluated_at || camera.last_seen_at || camera.edge_reported_at || camera.updated_at;
        const ruleText = evaluation?.matched_rules?.length ? `${evaluation.matched_rules.length} 条规则命中` : "未命中告警规则";
        const href = GoHomeEdge.pageHref(`monitor.html?camera_id=${encodeURIComponent(camera.id)}`) || `monitor.html?camera_id=${encodeURIComponent(camera.id)}`;
        return `
            <a class="gohome-camera-check-card" href="${href}">
                <div class="gohome-camera-check-head">
                    <span>${escapeHtml(cameraTitle(camera))}</span>
                    <span class="gohome-camera-check-badge ${statusClass}">${escapeHtml(status)}</span>
                </div>
                <p>${escapeHtml(evaluationText(camera, evaluation))}</p>
                <div class="gohome-camera-check-foot">
                    <span>${escapeHtml(ruleText)}</span>
                    <span>${escapeHtml(evaluatedAt ? GoHomeEdge.fmtDateTime(evaluatedAt) : "等待首次同步")}</span>
                </div>
            </a>
        `;
    }

    function renderEmpty(cameras = [], evaluations = new Map()) {
        const list = $("edgeEventsList");
        if (!list) return;
        const enabled = cameras.filter((camera) => camera.enabled !== false);
        const checks = enabled
            .map((camera) => renderCameraCheck(camera, evaluations.get(Number(camera.id))))
            .join("");
        list.innerHTML = `
            <div class="gohome-panel gohome-empty-state">
                <span class="material-symbols-outlined">health_and_safety</span>
                <h3>暂无待确认事件</h3>
                <p>事件列表只记录需要家属处理的异常。下面是当前摄像头的最近同步状态。</p>
                ${checks ? `<div class="gohome-camera-check-list">${checks}</div>` : ""}
            </div>
        `;
    }

    function enabledCameraIds(cameras) {
        return new Set(cameras.filter((camera) => camera.enabled).map((camera) => Number(camera.id)));
    }

    async function loadEvaluations(cameras) {
        const entries = await Promise.all((Array.isArray(cameras) ? cameras : [])
            .filter((camera) => camera.enabled !== false)
            .map(async (camera) => {
                try {
                    return [Number(camera.id), await GoHomeEdge.appLatestEvaluation(camera.id)];
                } catch (_error) {
                    return [Number(camera.id), null];
                }
            }));
        return new Map(entries);
    }

    async function render() {
        if (!window.GoHomeEdge) return;
        try {
            syncNavLinks(requestedCameraId());
            await GoHomeEdge.connect();
            const [summary, cameras, allEvents] = await Promise.all([
                GoHomeEdge.appSummary(),
                GoHomeEdge.appCameras(),
                GoHomeEdge.appEvents("limit=30"),
            ]);
            const evaluations = await loadEvaluations(cameras);
            const activeCameraIds = enabledCameraIds(cameras);
            const camerasById = cameraMap(cameras);
            pruneAppliedUpdates(allEvents);
            const events = applyPendingUpdates(allEvents)
                .filter((event) => activeCameraIds.has(Number(event.camera_id)))
                .filter((event) => !isStaleCameraOffline(event, camerasById));
            const openEvents = events.filter((event) => !event.acknowledged);
            const mainEvent = openEvents[0] || events[0];
            const requested = requestedCameraId();
            const selectedCameraId = activeCameraIds.has(Number(requested))
                ? requested
                : (activeCameraIds.has(Number(mainEvent?.camera_id)) ? Number(mainEvent.camera_id) : null);

            syncSelectedCameraParam(selectedCameraId);
            syncNavLinks(selectedCameraId);

            const onlineCount = cameras.filter((camera) => camera.enabled !== false && String(camera.status || "").toLowerCase() === "online").length;
            setText("edgeTimelineTitle", mainEvent ? displaySummary(mainEvent) : `${onlineCount} 路摄像头在线，暂无异常`);
            setText("edgeTimelineBadge", openEvents.length ? `${openEvents.length} 条待确认` : "当前平稳");
            setText("edgeTimelineAction", openEvents.length ? "按时间线处理最新提醒，处理后这里会同步状态。" : "最近没有需要处理的安全事件，正常检测不会进入事件列表。");

            const list = $("edgeEventsList");
            if (!list) return;
            if (!events.length) {
                renderEmpty(cameras, evaluations);
                return;
            }
            list.innerHTML = events.map((event) => renderEvent(event, selectedCameraId)).join("");
        } catch (error) {
            if (error?.status === 401) {
                GoHomeEdge.clearAuthToken();
                window.location.href = GoHomeEdge.loginHref(GoHomeEdge.currentPagePath());
                return;
            }
            syncNavLinks(requestedCameraId());
            setText("edgeTimelineTitle", "本机守护服务还没连接");
            setText("edgeTimelineBadge", "离线演示");
            setText("edgeTimelineAction", "启动家庭盒子服务");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        render();
        setInterval(render, 12000);
    });
    window.addEventListener("pageshow", render);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) render();
    });
})();
