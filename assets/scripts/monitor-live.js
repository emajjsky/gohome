(function () {
    const $ = (id) => document.getElementById(id);

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

    function statusTone(snapshot) {
        const tags = snapshot.tags || [];
        return tags.includes("black_screen") || tags.includes("fall_candidate") ? "text-[#c87b2a]" : "text-[#2d7d5c]";
    }

    function setPillTone(id, tone) {
        const node = $(id);
        if (!node) return;
        node.className = `app-mini-pill ${tone}`;
    }

    async function render() {
        if (!window.GoHomeEdge) return;
        try {
            await GoHomeEdge.connect();
            const [device, cameras] = await Promise.all([GoHomeEdge.device(), GoHomeEdge.cameras()]);
            const camera = cameras.find((item) => item.enabled) || cameras[0];

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

            const snapshot = await GoHomeEdge.latestSnapshot(camera.id);
            const image = $("edgeSnapshotImage");
            if (image && snapshot.image_url) {
                image.src = `${GoHomeEdge.edgeUrl(snapshot.image_url)}?t=${Date.now()}`;
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
})();
