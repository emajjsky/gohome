(function () {
    const $ = (id) => document.getElementById(id);

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function isLocalCamera(camera) {
        const streamUrl = String(camera?.stream_url || "").toLowerCase();
        return /^(local|webcam|device|camera):/.test(streamUrl) || /^\d+$/.test(streamUrl);
    }

    function preferredCamera(cameras) {
        return [...cameras].sort((a, b) => {
            const score = (camera) => (
                (camera.enabled ? 100 : 0) +
                (camera.status === "online" ? 30 : 0) +
                (isLocalCamera(camera) ? 0 : 20)
            );
            return score(b) - score(a);
        })[0];
    }

    function importantEvent(events, camera) {
        const currentCameraEvents = events.filter((event) => Number(event.camera_id) === Number(camera.id));
        return currentCameraEvents.find((event) => !event.acknowledged && event.level === "critical")
            || currentCameraEvents.find((event) => !event.acknowledged)
            || null;
    }

    function snapshotState(snapshot) {
        const tags = snapshot.tags || [];
        const analysis = snapshot.analysis || {};
        const personCount = snapshot.person_count ?? analysis.person_count;

        if (tags.includes("fall_candidate") || analysis.fall_candidate) {
            return {
                title: "客厅出现疑似跌倒姿态，建议你现在确认一下",
                subtitle: "系统识别到人体框比例和位置异常，这不是最终诊断，但值得立刻看一眼。",
                fact: "疑似跌倒姿态",
                factSub: "YOLO 检测结果触发了高优先级提醒。",
                feeling: "需要马上确认",
                feelingSub: "先确认老人状态，再判断是不是误报。",
                action: "立即联系老人",
                actionSub: "如果联系不上，再通知其他家属或邻居。",
                snapshot: "检测到疑似跌倒候选",
            };
        }

        if (tags.includes("black_screen") || analysis.black_screen) {
            return {
                title: "摄像头画面疑似遮挡或黑屏，需要看一下设备",
                subtitle: "本机服务仍在线，但画面亮度和对比度异常，可能是遮挡、背光或摄像头异常。",
                fact: "画面异常",
                factSub: "亮度和对比度低于阈值。",
                feeling: "需要排查",
                feelingSub: "先看摄像头位置，再确认家里情况。",
                action: "检查摄像头",
                actionSub: "如果画面恢复，事件可以标记为已处理。",
                snapshot: "画面疑似遮挡或黑屏",
            };
        }

        if (personCount !== null && personCount !== undefined) {
            if (personCount > 0) {
                return {
                    title: `客厅检测到 ${personCount} 个人，当前家里状态平稳`,
                    subtitle: "本机守护服务正在持续抽帧识别，目前没有触发高优先级异常。",
                    fact: `${personCount} 人在画面中`,
                    factSub: "YOLO 人形检测已接入，当前画面有人。",
                    feeling: "家里有活动",
                    feelingSub: "这类结果适合转成安心提醒，而不是告警。",
                    action: "继续观察",
                    actionSub: "有空时打一通电话，比等告警更有温度。",
                    snapshot: `画面检测到 ${personCount} 个人`,
                };
            }
            return {
                title: "客厅暂时没有检测到人，守护服务正在持续观察",
                subtitle: "这不一定是异常，只说明当前这张截图里没有人形目标；系统会继续按规则判断。",
                fact: "当前未见人形",
                factSub: "YOLO 没有在最新截图中识别到人。",
                feeling: "家里很安静",
                feelingSub: "如果持续超过阈值，系统会生成提醒。",
                action: "继续观察",
                actionSub: "现在可以去守护页看实时截图。",
                snapshot: "当前画面暂未检测到人",
            };
        }

        return {
            title: "本机守护服务已连接，正在观察家里状态",
            subtitle: "当前使用基础视觉指标判断画面变化、黑屏和离线情况。",
            fact: "服务在线",
            factSub: "摄像头最新截图已经同步。",
            feeling: "家里平稳",
            feelingSub: "还没有触发需要处理的提醒。",
            action: "继续观察",
            actionSub: "下一步可以打开守护页查看细节。",
            snapshot: "最新画面已同步",
        };
    }

    async function render() {
        if (!window.GoHomeEdge) return;
        try {
            await GoHomeEdge.connect();
            const [device, cameras, events] = await Promise.all([
                GoHomeEdge.device(),
                GoHomeEdge.cameras(),
                GoHomeEdge.events("limit=10&acknowledged=false"),
            ]);
            const camera = preferredCamera(cameras);

            setText("edgeHomeDevice", device.worker_running ? "本机守护服务在线" : "本机守护服务暂停");

            if (!camera) {
                setText("edgeHomeTime", "等待摄像头接入");
                setText("edgeHomeTitle", "还没有添加摄像头");
                setText("edgeHomeSubtitle", "先打开本机守护服务管理台，把局域网摄像头接进来。");
                return;
            }

            const event = importantEvent(events, camera);
            const snapshot = await GoHomeEdge.latestSnapshot(camera.id);
            const state = snapshotState(snapshot);
            const image = $("edgeHomeSnapshotImage");
            if (image && snapshot.image_url) {
                image.src = `${GoHomeEdge.edgeUrl(snapshot.image_url)}?t=${Date.now()}`;
                image.classList.remove("object-[center_38%]");
            }

            setText("edgeHomeTime", `${GoHomeEdge.fmtTime(snapshot.captured_at)} 更新 · ${camera.room || camera.name || "家里"} · ${device.detector_backend === "yolo" ? "YOLO 检测中" : "基础检测中"}`);
            setText("edgeHomeTitle", event ? event.summary : state.title);
            setText("edgeHomeSubtitle", event ? "本机服务已经生成一条待确认提醒，建议先去事件页查看截图和处理状态。" : state.subtitle);
            setText("edgeHomeFactTitle", event ? GoHomeEdge.eventLabel(event.type) : state.fact);
            setText("edgeHomeFactSub", event ? `${GoHomeEdge.fmtDateTime(event.occurred_at)} 触发，来自 ${event.camera_name || camera.name || "摄像头"}。` : state.factSub);
            setText("edgeHomeFeelingTitle", event ? "有一条提醒待确认" : state.feeling);
            setText("edgeHomeFeelingSub", event ? "这类信息应该进入告警处理流程，而不是只作为普通动态展示。" : state.feelingSub);
            setText("edgeHomeActionTitle", event ? "先查看事件，再联系老人" : state.action);
            setText("edgeHomeActionSub", event ? "确认安全后可以标记已处理；误报也要保留记录。" : state.actionSub);
            setText("edgeHomeSnapshotTime", `${GoHomeEdge.fmtTime(snapshot.captured_at)} 更新`);
            setText("edgeHomeSnapshotRoom", camera.room || camera.name || "家里动态");
            setText("edgeHomeSnapshotHeadline", event ? event.summary : state.snapshot);
            setText("edgeHomeSnapshotSub", `亮度 ${Number(snapshot.brightness || 0).toFixed(0)} · 人数 ${snapshot.person_count ?? "-"} · ${snapshot.tags?.length ? snapshot.tags.join(", ") : "无异常标签"}`);
        } catch (error) {
            setText("edgeHomeDevice", "本机守护服务未连接");
            setText("edgeHomeTime", "等待 edge-agent");
            setText("edgeHomeTitle", "主页面还没有连到本机守护服务");
            setText("edgeHomeSubtitle", error.message || "启动 8711 服务后，这里会自动切换成真实摄像头状态。");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        render();
        setInterval(render, 10000);
    });
})();
