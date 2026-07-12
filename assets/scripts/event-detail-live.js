(function () {
    const $ = (id) => document.getElementById(id);
    const EVENT_UPDATES_KEY = "gohome.eventUpdates";
    let verificationPollCount = 0;
    let verificationPollTimer = null;

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function eventId() {
        return new URLSearchParams(window.location.search).get("eventId");
    }

    function requestedCameraId() {
        const value = new URLSearchParams(window.location.search).get("camera_id");
        return value ? Number(value) : null;
    }

    function syncDetailLinks(event) {
        const backLink = $("edgeDetailBackLink");
        const watchLink = $("edgeDetailWatchLink");
        const backCameraId = requestedCameraId() || event?.camera_id || null;
        const watchCameraId = event?.camera_id || requestedCameraId() || null;
        if (backLink) {
            const suffix = backCameraId ? `?camera_id=${encodeURIComponent(backCameraId)}` : "";
            backLink.href = GoHomeEdge.pageHref(`events.html${suffix}`) || `events.html${suffix}`;
        }
        if (watchLink) {
            const suffix = watchCameraId ? `?camera_id=${encodeURIComponent(watchCameraId)}` : "";
            watchLink.href = GoHomeEdge.pageHref(`watch.html${suffix}`) || `watch.html${suffix}`;
        }
    }

    function readEventUpdates() {
        try {
            return JSON.parse(sessionStorage.getItem(EVENT_UPDATES_KEY) || "{}");
        } catch (_error) {
            return {};
        }
    }

    function writeEventUpdate(event) {
        if (!event?.id) return;
        const updates = readEventUpdates();
        updates[String(event.id)] = {
            acknowledged: Boolean(event.acknowledged),
            resolution: String(event.resolution || ""),
            updated_at: new Date().toISOString(),
        };
        sessionStorage.setItem(EVENT_UPDATES_KEY, JSON.stringify(updates));
    }

    function statusText(event) {
        const incidentStatus = String(event?.payload?.incident?.status || "");
        if (incidentStatus === "rejected") return "已排除";
        if (incidentStatus === "resolved") return "已恢复";
        if (!event?.acknowledged) return "需要确认";
        if (event.resolution === "false_positive") return "已标记误报";
        return "已确认安全";
    }

    function verificationText(event) {
        const verification = event?.payload?.verification || {};
        const status = String(verification.status || "");
        const result = verification.result || {};
        if (!status) return "";
        if (status === "pending" || status === "verifying") return "云端正在复核事件证据";
        if (status === "retrying") return "云端复核暂时失败，系统正在自动重试";
        if (status === "confirmed") return `云端视觉复核支持这条提醒：${result.reason || "建议立即确认老人状态"}`;
        if (status === "rejected") return `云端视觉复核暂未看到明确紧急线索：${result.reason || "仍建议结合实时画面确认"}`;
        if (status === "uncertain") return `云端视觉证据不足，需要人工确认：${result.reason || "请查看截图和实时画面"}`;
        if (status === "failed") return "云端复核未完成，当前提醒仍以家庭盒子的边缘判断为准";
        if (status === "unavailable") return "当前没有可用的云端复核结果，提醒仍以家庭盒子判断为准";
        return "";
    }

    function syncActionState(event) {
        const handled = $("edgeMarkHandled");
        const falsePositive = $("edgeMarkFalsePositive");
        const incidentStatus = String(event?.payload?.incident?.status || "");
        const locked = Boolean(event?.acknowledged) || ["rejected", "resolved"].includes(incidentStatus);
        if (handled) handled.disabled = locked;
        if (falsePositive) falsePositive.disabled = locked;
        if (handled) handled.classList.toggle("opacity-60", locked);
        if (falsePositive) falsePositive.classList.toggle("opacity-60", locked);
    }

    function detailNote(event) {
        if (event.type === "fall_candidate") {
            return "系统看到的是人体框比例和位置变化，不等于已经确认跌倒。它的意义是提醒你尽快确认。";
        }
        if (event.type === "prolonged_floor_lying") {
            return "系统连续看到同一人在非床或沙发区域保持躺卧超过 3 分钟，请尽快确认老人状态。";
        }
        if (event.type === "long_absence") {
            return "所有参与守护的摄像头在线且观察覆盖达标，但长时间没有检测到老人，请先联系确认是否外出。";
        }
        if (event.type === "black_screen") {
            return "系统检测到画面亮度和对比度异常，可能是遮挡、黑屏或强背光。";
        }
        if (event.type === "camera_offline") {
            return "家庭盒子暂时无法连接摄像头，可能是网络、账号或摄像头电源问题。";
        }
        if (event.type === "no_motion") {
            return "系统在设定时间内没有看到明显画面变化，需要结合时间段判断是否异常。";
        }
        return "这条提醒来自家庭盒子的检测结果，建议结合截图和现实情况确认。";
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

    function displaySummary(event) {
        if (!event) return "正在读取事件";
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
        if (event.type === "long_absence") return "家中长时间没有检测到老人";
        return cleanReason(event, event.summary) || GoHomeEdge.eventLabel(event.type);
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
        if (key === "motion_state") {
            return value === "still" ? "静止" : value === "moving" ? "有变化" : String(value);
        }
        if (key === "person_state") {
            return value === "not_visible" ? "未检测到人" : value === "visible" ? "检测到人" : String(value);
        }
        if (key === "camera_state") {
            return value === "offline" ? "离线" : String(value);
        }
        if (typeof value === "boolean") return value ? "是" : "否";
        if (Array.isArray(value)) return `${value.length} 项`;
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
            camera_state: "摄像头状态",
            person_state: "人物状态",
            motion_state: "画面状态",
            error: "错误信息",
        };
        return labels[key] || key;
    }

    function summarizeMetrics(metrics) {
        const entries = Object.entries(metrics || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
        if (!entries.length) return "";
        return entries.map(([key, value]) => `${metricLabel(key)} ${fmtMetricValue(key, value)}`).join("，");
    }

    function durationText(event, payload, rule) {
        const observed = rule?.observed || {};
        const seconds = payload.no_motion_seconds
            ?? payload.no_person_seconds
            ?? observed.no_motion_seconds
            ?? observed.no_person_seconds
            ?? null;
        if (seconds !== null && seconds !== undefined) return fmtMetricValue("duration_seconds", seconds);
        if (event.type === "camera_offline") return "连接中断";
        return "实时事件";
    }

    function durationHint(event, _payload, rule) {
        const observedSummary = summarizeMetrics(rule?.observed);
        return rule?.label || observedSummary || GoHomeEdge.eventLabel(event.type);
    }

    function factText(event, _payload, rule) {
        const label = rule?.label || GoHomeEdge.eventLabel(event.type);
        const reason = rule?.reason ? `，原因是：${cleanReason(event, rule.reason)}` : "";
        return `${GoHomeEdge.fmtDateTime(event.occurred_at)}，${event.camera_name || "摄像头"} 触发了${label}${reason}`;
    }

    function factSubText(payload, rule) {
        const observed = summarizeMetrics(rule?.observed);
        const threshold = summarizeMetrics(rule?.threshold);
        const state = summarizeMetrics(payload?.evaluation?.state);
        const parts = [];
        if (observed) parts.push(`当前观测：${observed}`);
        if (threshold) parts.push(`规则阈值：${threshold}`);
        if (state) parts.push(`评估状态：${state}`);
        const verification = verificationText({ payload });
        if (verification) parts.push(verification);
        if (!parts.length) return `原始亮度：${Number(payload?.brightness || 0).toFixed(0)}。`;
        return `${parts.join("。")}。`;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function timelineTime(value) {
        if (!value) return "";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "";
        return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    }

    function transitionCopy(transition) {
        const status = String(transition?.status || "");
        const source = String(transition?.source || "");
        if (source === "app_user" || status === "acknowledged") {
            return { icon: "task_alt", title: "你已确认收到", detail: "这条提醒已停止重复推送。", tone: "" };
        }
        if (source === "edge_admin" || (status === "rejected" && transition?.resolution === "false_positive")) {
            return { icon: "rule", title: "已核对为算法误报", detail: "记录和证据保留，用于后续校准。", tone: "" };
        }
        if (source === "presence_recovery" || status === "resolved") {
            return { icon: "person_check", title: "家中状态已经恢复", detail: "摄像头重新检测到老人，本次提醒自动结束。", tone: "" };
        }
        if (source === "vision_verification") {
            if (status === "confirmed") {
                return { icon: "verified", title: "云端模型支持异常判断", detail: "请结合截图或电话尽快确认老人状态。", tone: "warning" };
            }
            if (status === "rejected") {
                return { icon: "fact_check", title: "云端模型未发现明确异常", detail: "原始记录仍然保留，供你核对。", tone: "" };
            }
            if (status === "uncertain") {
                return { icon: "help", title: "云端证据不足", detail: "模型无法明确判断，需要人工确认。", tone: "warning" };
            }
            return { icon: "cloud_sync", title: "云端正在复核", detail: "系统正在检查事件截图和边缘检测依据。", tone: "" };
        }
        if (["active", "verifying", "confirmed"].includes(status)) {
            return { icon: "notifications_active", title: "守护提醒已建立", detail: "系统将持续跟踪，直到收到处理结果。", tone: "warning" };
        }
        return null;
    }

    function timelineItem(item) {
        const detail = item.detail ? `<p>${escapeHtml(item.detail)}</p>` : "";
        const time = item.at ? `<time datetime="${escapeHtml(item.at)}">${escapeHtml(timelineTime(item.at))}</time>` : "";
        return `<div class="timeline-item ${escapeHtml(item.tone || "")}">
            <div class="timeline-icon"><span class="material-symbols-outlined">${escapeHtml(item.icon)}</span></div>
            <div class="timeline-copy">
                <div class="timeline-head"><strong>${escapeHtml(item.title)}</strong>${time}</div>
                ${detail}
            </div>
        </div>`;
    }

    function renderTimeline(event) {
        const node = $("edgeDetailTimeline");
        if (!node) return;
        const payload = event?.payload || {};
        const incident = payload.incident || {};
        const cameraCount = new Set((incident.source_camera_ids || []).map(String).filter(Boolean)).size;
        const items = [{
            icon: "sensors",
            title: "家庭盒子发现异常",
            detail: `${event.camera_name || event.room || "摄像头"}记录了${GoHomeEdge.eventLabel(event.type)}。`,
            at: event.occurred_at,
            tone: event.level === "critical" ? "warning" : "",
        }];
        if (cameraCount > 1) {
            items.push({
                icon: "videocam",
                title: `${cameraCount} 路摄像头提供了佐证`,
                detail: "同一时间窗口的画面已合并为一条守护事件。",
                at: incident.started_at || event.occurred_at,
                tone: "",
            });
        }
        const transitions = Array.isArray(incident.transitions) ? incident.transitions : [];
        for (const transition of transitions) {
            const copy = transitionCopy(transition);
            if (!copy) continue;
            items.push({ ...copy, at: transition.at || event.created_at });
        }
        const verification = payload.verification || {};
        if (verification.status && !transitions.some((item) => item.source === "vision_verification")) {
            const copy = transitionCopy({ status: verification.status, source: "vision_verification" });
            if (copy) items.push({ ...copy, at: verification.updated_at || event.created_at });
        }
        if (event.acknowledged && !transitions.some((item) => item.source === "app_user" || item.status === "acknowledged")) {
            const copy = transitionCopy({ status: "acknowledged", source: "app_user" });
            items.push({ ...copy, at: event.updated_at || event.created_at });
        }
        node.innerHTML = items.map(timelineItem).join("");
    }

    async function applyEvent(event) {
        const payload = event.payload || {};
        const rule = payload.rule || {};
        const image = $("edgeDetailImage");
        syncDetailLinks(event);
        if (image && event.snapshot_url) {
            image.src = await GoHomeEdge.v1VideoMediaPlaybackUrl(event.snapshot_url);
        }
        setText("edgeDetailTime", GoHomeEdge.fmtTime(event.occurred_at));
        setText("edgeDetailStatus", statusText(event));
        setText("edgeDetailHero", displaySummary(event));
        setText("edgeDetailTitle", displaySummary(event));
        setText("edgeDetailRoom", event.room || event.camera_name || "家庭摄像头");
        setText("edgeDetailDuration", durationText(event, payload, rule));
        setText("edgeDetailDurationHint", durationHint(event, payload, rule));
        const verification = verificationText(event);
        setText("edgeDetailNote", verification || cleanReason(event, rule.reason) || detailNote(event));
        setText("edgeDetailFact", factText(event, payload, rule));
        setText("edgeDetailFactSub", factSubText(payload, rule));
        renderTimeline(event);
        syncActionState(event);
        const verificationStatus = String(payload?.verification?.status || "");
        if (["pending", "verifying", "retrying"].includes(verificationStatus) && verificationPollCount < 10) {
            clearTimeout(verificationPollTimer);
            verificationPollCount += 1;
            verificationPollTimer = setTimeout(() => render(), 3000);
        }
    }

    async function markEvent(patch) {
        const id = eventId();
        if (!id || !window.GoHomeEdge) return;
        const event = await GoHomeEdge.appUpdateEvent(id, patch);
        writeEventUpdate(event);
        await applyEvent(event);
    }

    async function render() {
        const id = eventId();
        if (!id || !window.GoHomeEdge) return;

        try {
            await GoHomeEdge.connect();
            const event = await GoHomeEdge.appEvent(id);
            await applyEvent(event);
        } catch (error) {
            if (error?.status === 401) {
                GoHomeEdge.clearAuthToken();
                window.location.href = GoHomeEdge.loginHref(GoHomeEdge.currentPagePath());
                return;
            }
            setText("edgeDetailHero", error.message || "事件详情暂时无法连接");
            syncDetailLinks(null);
            syncActionState(null);
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        render();
        const handled = $("edgeMarkHandled");
        const falsePositive = $("edgeMarkFalsePositive");
        if (handled) {
            handled.addEventListener("click", () => {
                markEvent({ acknowledged: true, resolution: "handled" }).catch(() => {});
            });
        }
        if (falsePositive) {
            falsePositive.addEventListener("click", () => {
                markEvent({ acknowledged: true, resolution: "false_positive" }).catch(() => {});
            });
        }
    });
})();
