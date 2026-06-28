(function () {
    const $ = (id) => document.getElementById(id);

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function eventId() {
        return new URLSearchParams(window.location.search).get("eventId");
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

    async function markEvent(patch, message) {
        const id = eventId();
        if (!id || !window.GoHomeEdge) return;
        await GoHomeEdge.updateEvent(id, patch);
        setText("edgeDetailStatus", message);
    }

    async function render() {
        const id = eventId();
        if (!id || !window.GoHomeEdge) return;

        try {
            await GoHomeEdge.connect();
            const event = await GoHomeEdge.event(id);
            const payload = event.payload || {};
            const image = $("edgeDetailImage");
            if (image && event.snapshot_url) {
                image.src = `${GoHomeEdge.edgeUrl(event.snapshot_url)}?t=${Date.now()}`;
            }

            setText("edgeDetailTime", GoHomeEdge.fmtTime(event.occurred_at));
            setText("edgeDetailStatus", event.acknowledged ? "已处理" : "需要确认");
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
        } catch (error) {
            setText("edgeDetailHero", error.message || "事件详情暂时无法连接");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        render();
        const handled = $("edgeMarkHandled");
        const falsePositive = $("edgeMarkFalsePositive");
        if (handled) {
            handled.addEventListener("click", () => {
                markEvent({ acknowledged: true, resolution: "handled" }, "已确认安全").catch(() => {});
            });
        }
        if (falsePositive) {
            falsePositive.addEventListener("click", () => {
                markEvent({ acknowledged: true, resolution: "false_positive" }, "已标记误报").catch(() => {});
            });
        }
    });
})();
