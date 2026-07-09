(function () {
    const $ = (id) => document.getElementById(id);
    const EVENT_UPDATES_KEY = "gohome.eventUpdates";

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
        if (!event?.acknowledged) return "需要确认";
        if (event.resolution === "false_positive") return "已标记误报";
        return "已确认安全";
    }

    function syncActionState(event) {
        const handled = $("edgeMarkHandled");
        const falsePositive = $("edgeMarkFalsePositive");
        const locked = Boolean(event?.acknowledged);
        if (handled) handled.disabled = locked;
        if (falsePositive) falsePositive.disabled = locked;
        if (handled) handled.classList.toggle("opacity-60", locked);
        if (falsePositive) falsePositive.classList.toggle("opacity-60", locked);
    }

    function detailNote(event) {
        if (event.type === "fall_candidate") {
            return "系统看到的是人体框比例和位置变化，不等于已经确认跌倒。它的意义是提醒你尽快确认。";
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
        if (!parts.length) return `原始亮度：${Number(payload?.brightness || 0).toFixed(0)}。`;
        return `${parts.join("。")}。`;
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
        setText("edgeDetailNote", cleanReason(event, rule.reason) || detailNote(event));
        setText("edgeDetailFact", factText(event, payload, rule));
        setText("edgeDetailFactSub", factSubText(payload, rule));
        syncActionState(event);
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
