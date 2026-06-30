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
            return "本机守护服务暂时无法连接摄像头，可能是网络、账号或摄像头电源问题。";
        }
        if (event.type === "no_motion") {
            return "系统在设定时间内没有看到明显画面变化，需要结合时间段判断是否异常。";
        }
        return "这条提醒来自本机守护服务的检测结果，建议结合截图和现实情况确认。";
    }

    async function applyEvent(event) {
        const payload = event.payload || {};
        const image = $("edgeDetailImage");
        syncDetailLinks(event);
        if (image && event.snapshot_url) {
            image.src = await GoHomeEdge.v1VideoMediaPlaybackUrl(event.snapshot_url);
        }
        setText("edgeDetailTime", GoHomeEdge.fmtTime(event.occurred_at));
        setText("edgeDetailStatus", statusText(event));
        setText("edgeDetailHero", event.summary);
        setText("edgeDetailTitle", event.summary);
        setText("edgeDetailRoom", event.room || event.camera_name || "本机测试");
        setText("edgeDetailDuration", payload.no_motion_seconds ? `${payload.no_motion_seconds} 秒` : "实时事件");
        setText("edgeDetailDurationHint", GoHomeEdge.eventLabel(event.type));
        setText("edgeDetailNote", detailNote(event));
        setText("edgeDetailFact", `${GoHomeEdge.fmtDateTime(event.occurred_at)}，${event.camera_name || "摄像头"} 触发了${GoHomeEdge.eventLabel(event.type)}。`);
        setText("edgeDetailFactSub", payload.person_count !== null && payload.person_count !== undefined
            ? `当时画面人数：${payload.person_count}，原始亮度：${Number(payload.brightness || 0).toFixed(0)}。`
            : `原始亮度：${Number(payload.brightness || 0).toFixed(0)}。`);
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
