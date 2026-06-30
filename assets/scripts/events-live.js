(function () {
    const $ = (id) => document.getElementById(id);
    const EVENT_UPDATES_KEY = "gohome.eventUpdates";

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
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
        const watchHref = GoHomeEdge.pageHref(`watch.html${suffix}`) || `watch.html${suffix}`;
        const watchLink = $("edgeTimelineWatchLink");
        const monitorLink = $("edgeTimelineMonitorLink");
        const backLink = $("edgeEventsBackLink");
        if (watchLink) watchLink.href = watchHref;
        if (monitorLink) monitorLink.href = GoHomeEdge.pageHref("monitor.html") || "monitor.html";
        if (backLink) backLink.href = GoHomeEdge.pageHref("monitor.html") || "monitor.html";
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

    function actionText(event) {
        if (event.acknowledged) return "已处理，可以作为记录查看。";
        if (event.type === "fall_candidate") return "建议先确认老人状态，再标记处理。";
        if (event.type === "camera_offline") return "建议检查本机服务和摄像头连接。";
        if (event.type === "black_screen") return "建议打开截图，看是否遮挡或背光。";
        return "适合现在看一眼。";
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
            <a href="${detailHref}" class="app-soft-card bg-white p-4 group">
                <div class="flex items-start justify-between gap-3">
                    <div class="flex items-center gap-2 text-on-surface-variant font-sans text-xs font-semibold">
                        <span class="material-symbols-outlined text-[16px]">schedule</span>${time}
                        <span class="w-1 h-1 rounded-full bg-outline-variant"></span>
                        <span class="material-symbols-outlined text-[16px]">nest_cam_indoor</span>${room}
                    </div>
                    <span class="px-2.5 py-1 rounded-full ${statusClass} text-[10px] font-semibold">${status}</span>
                </div>
                <div class="flex items-start gap-3 mt-3">
                    <div class="w-11 h-11 rounded-full ${iconTone(event)} flex items-center justify-center shrink-0">
                        <span class="material-symbols-outlined">${GoHomeEdge.eventIcon(event.type)}</span>
                    </div>
                    <div class="min-w-0">
                        <h3 class="font-display text-[18px] font-bold text-on-surface">${event.summary}</h3>
                        <p class="font-sans text-[13px] text-on-surface-variant mt-1.5 leading-relaxed">${label} · ${GoHomeEdge.fmtDateTime(event.occurred_at)}</p>
                        <p class="font-sans text-[12px] text-primary font-semibold mt-2">${actionText(event)}</p>
                    </div>
                </div>
            </a>
        `;
    }

    function renderEmpty() {
        const list = $("edgeEventsList");
        if (!list) return;
        list.innerHTML = `
            <div class="app-soft-card bg-white p-5 text-center">
                <span class="material-symbols-outlined text-primary text-[30px]">health_and_safety</span>
                <h3 class="font-display text-[18px] font-bold text-on-surface mt-2">今天暂时没有告警</h3>
                <p class="font-sans text-[13px] text-on-surface-variant mt-1 leading-relaxed">本机守护服务会在异常时把截图和事件同步到这里。</p>
            </div>
        `;
    }

    function enabledCameraIds(cameras) {
        return new Set(cameras.filter((camera) => camera.enabled).map((camera) => Number(camera.id)));
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
            const activeCameraIds = enabledCameraIds(cameras);
            pruneAppliedUpdates(allEvents);
            const events = applyPendingUpdates(allEvents).filter((event) => activeCameraIds.has(Number(event.camera_id)));
            const openEvents = events.filter((event) => !event.acknowledged);
            const mainEvent = openEvents[0] || events[0];
            const requested = requestedCameraId();
            const selectedCameraId = activeCameraIds.has(Number(requested))
                ? requested
                : (activeCameraIds.has(Number(mainEvent?.camera_id)) ? Number(mainEvent.camera_id) : null);

            syncSelectedCameraParam(selectedCameraId);
            syncNavLinks(selectedCameraId);

            setText("edgeTimelineTitle", mainEvent ? `今天最让人在意的是：${mainEvent.summary}` : summary.main_message);
            setText("edgeTimelineBadge", openEvents.length ? `${openEvents.length} 条待确认` : "当前平稳");
            setText("edgeTimelineAction", openEvents.length ? "先看最新提醒" : "继续守护");

            const list = $("edgeEventsList");
            if (!list) return;
            if (!events.length) {
                renderEmpty();
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
            setText("edgeTimelineAction", "启动 edge-agent");
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
