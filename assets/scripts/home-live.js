(function () {
    const $ = (id) => document.getElementById(id);
    const CONTENT_SECTION_IDS = [
        "edgeHomePlanSection",
        "edgeHomeReasonSection",
        "edgeHomeSnapshotSection",
        "edgeHomeMemorySection",
    ];

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function toggleMessageSection(show) {
        $("edgeHomeMessageSection")?.classList.toggle("hidden", !show);
    }

    function setAction(id, href, label, icon) {
        const node = $(id);
        if (!node) return;
        node.href = window.GoHomeEdge?.pageHref?.(href) || href;
        const iconNode = node.querySelector(".material-symbols-outlined");
        if (iconNode && icon) {
            iconNode.textContent = icon;
            iconNode.classList.toggle("fill", icon === "login" || icon === "home" || icon === "call");
        }
        const textNode = Array.from(node.childNodes).find((child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
        if (textNode) {
            textNode.textContent = ` ${label}`;
        } else {
            node.append(document.createTextNode(` ${label}`));
        }
    }

    function messageBadge(messageType) {
        const type = String(messageType || "").trim();
        if (type === "alert") return { label: "告警", tone: "warn", icon: "notifications_active" };
        if (type === "gohome") return { label: "回家", tone: "good", icon: "home" };
        if (type === "explain") return { label: "解释", tone: "info", icon: "visibility" };
        return { label: "陪伴", tone: "info", icon: "favorite" };
    }

    function messageActionConfig(message) {
        const messageType = String(message?.message_type || "").trim();
        const sourceEventIds = Array.isArray(message?.source_event_ids) ? message.source_event_ids : [];
        if (messageType === "alert" || sourceEventIds.length) {
            return {
                primary: { href: "events.html", label: "查看事件", icon: "history" },
                secondary: { href: "watch.html", label: "实时看看", icon: "nest_cam_indoor" },
            };
        }
        return {
            primary: { href: "companionship.html", label: "去陪伴页", icon: "favorite" },
            secondary: { href: "watch.html", label: "看看家里", icon: "nest_cam_indoor" },
        };
    }

    function renderMessageCard(message) {
        if (!message) {
            toggleMessageSection(false);
            return;
        }
        const badge = messageBadge(message.message_type);
        const badgeNode = $("edgeHomeMessageBadge");
        const iconNode = $("edgeHomeMessageIcon");
        const facts = Array.isArray(message.facts) ? message.facts : [];
        const actions = Array.isArray(message.actions) ? message.actions : [];
        const actionConfig = messageActionConfig(message);

        toggleMessageSection(true);
        setText("edgeHomeMessageMeta", `${message.generated_by || "message-service"} · ${window.GoHomeEdge?.fmtDateTime?.(message.created_at) || ""}`);
        setText("edgeHomeMessageTitle", message.title || "今天有一条新的牵挂提醒");
        setText("edgeHomeMessageSubtitle", message.subtitle || message.body || "");
        setText("edgeHomeMessageFacts", facts.length ? facts.join(" / ") : "这条消息目前还没有补充依据。");
        setText("edgeHomeMessageActions", actions.length ? actions.map((item) => item.label || item.key || "").filter(Boolean).join(" / ") : "先打开消息，再决定是否联系。");
        if (badgeNode) {
            badgeNode.textContent = badge.label;
            badgeNode.className = `app-status-badge ${badge.tone} shrink-0`;
        }
        if (iconNode) {
            iconNode.className = `app-icon-chip ${badge.tone} shrink-0`;
            const iconGlyph = iconNode.querySelector(".material-symbols-outlined");
            if (iconGlyph) iconGlyph.textContent = badge.icon;
        }
        setAction("edgeHomeMessagePrimaryAction", actionConfig.primary.href, actionConfig.primary.label, actionConfig.primary.icon);
        setAction("edgeHomeMessageSecondaryAction", actionConfig.secondary.href, actionConfig.secondary.label, actionConfig.secondary.icon);
    }

    async function loadPrimaryMessage(familyId) {
        if (!window.GoHomeEdge?.v1AppMessages || !window.GoHomeEdge?.v1GenerateMessages) return null;
        let messages = [];
        try {
            messages = await window.GoHomeEdge.v1AppMessages({ family_id: familyId, limit: 6, status: "open" });
        } catch (_error) {
            return null;
        }
        if (messages.length) return messages[0];
        try {
            const generated = await window.GoHomeEdge.v1GenerateMessages({ family_id: familyId, clear_existing: true });
            messages = Array.isArray(generated?.messages) ? generated.messages : [];
        } catch (_error) {
            return null;
        }
        return messages[0] || null;
    }

    function syncCameraEntryLinks(camera) {
        const suffix = camera?.id ? `?camera_id=${encodeURIComponent(camera.id)}` : "";
        const monitorHref = suffix ? `monitor.html${suffix}` : "monitor.html";
        const watchHref = suffix ? `watch.html${suffix}` : "watch.html";
        const eventsHref = suffix ? `events.html${suffix}` : "events.html";
        const entries = {
            edgeHomePrimaryAction: watchHref,
            edgeHomeMonitorLink: monitorHref,
            edgeHomeWatchLink: watchHref,
            edgeHomeEventsLink: eventsHref,
            edgeHomeNavMonitorLink: monitorHref,
            edgeHomeNavEventsLink: eventsHref,
        };
        Object.entries(entries).forEach(([id, href]) => {
            const node = $(id);
            if (node) node.href = window.GoHomeEdge?.pageHref?.(href) || href;
        });
    }

    function toggleSetupMode(show) {
        $("edgeHomeSetupPanel")?.classList.toggle("hidden", !show);
        CONTENT_SECTION_IDS.forEach((id) => $(id)?.classList.toggle("hidden", show));
    }

    function setSetupStates(account, family, binding, badge = "未完成") {
        setText("edgeHomeAccountState", account);
        setText("edgeHomeFamilyState", family);
        setText("edgeHomeBindingState", binding);
        setText("edgeHomeSetupBadge", badge);
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

    function fallbackGuestHome() {
        toggleMessageSection(false);
        toggleSetupMode(true);
        setSetupStates("未登录", "未开始", "未绑定", "先登录");
        setText("edgeHomeDevice", "先接身份");
        setText("edgeHomeTime", "先登录");
        setText("edgeHomeTitle", "先登录，再把家庭和设备接上。");
        setText("edgeHomeSubtitle", "");
        setAction("edgeHomePrimaryAction", "login.html", "去登录", "login");
        setAction("edgeHomeSecondaryAction", "family.html", "家庭空间", "groups");
    }

    function renderNoFamilyHome(user) {
        toggleMessageSection(false);
        toggleSetupMode(true);
        setSetupStates("已登录", "未创建", "待绑定", "下一步");
        setText("edgeHomeDevice", user.display_name || user.email || "已登录");
        setText("edgeHomeTime", "下一步");
        setText("edgeHomeTitle", "先建家庭。");
        setText("edgeHomeSubtitle", "");
        setAction("edgeHomePrimaryAction", "family.html", "创建家庭", "groups");
        setAction("edgeHomeSecondaryAction", "login.html", "切换账号", "person");
    }

    function renderNeedsBindingHome(user, family) {
        toggleMessageSection(false);
        toggleSetupMode(true);
        setSetupStates("已登录", family?.name || "已创建", "待绑定", "待绑定");
        setText("edgeHomeDevice", user.display_name || user.email || "已登录");
        setText("edgeHomeTime", "最后一步");
        setText("edgeHomeTitle", "把这台设备绑到家庭。");
        setText("edgeHomeSubtitle", "");
        setAction("edgeHomePrimaryAction", "device_binding.html", "绑定设备", "link");
        setAction("edgeHomeSecondaryAction", "family.html", "家庭空间", "groups");
    }

    async function render() {
        if (!window.GoHomeEdge) return;
        try {
            await GoHomeEdge.connect();
            let user = null;
            if (GoHomeEdge.isAuthenticated()) {
                try {
                    user = await GoHomeEdge.currentUser();
                } catch (_error) {
                    GoHomeEdge.clearAuthToken();
                }
            }
            if (!user) {
                fallbackGuestHome();
                return;
            }

            const [families, device] = await Promise.all([
                GoHomeEdge.myFamilies(),
                GoHomeEdge.appDevice(),
            ]);
            const primaryFamily = families[0] || null;
            if (!primaryFamily) {
                renderNoFamilyHome(user);
                return;
            }

            const bindings = await GoHomeEdge.deviceBindings(primaryFamily.id);
            const currentBinding = bindings.find((item) => item.device_id === device.device_id);
            if (!currentBinding) {
                renderNeedsBindingHome(user, primaryFamily);
                return;
            }

            toggleSetupMode(false);
            setAction("edgeHomePrimaryAction", "watch.html", "实时观看", "nest_cam_indoor");
            setAction("edgeHomeSecondaryAction", "family.html", "家庭空间", "groups");
            const [cameras, events, primaryMessage] = await Promise.all([
                GoHomeEdge.appCameras(),
                GoHomeEdge.appEvents("limit=10&acknowledged=false"),
                loadPrimaryMessage(primaryFamily.id),
            ]);
            renderMessageCard(primaryMessage);
            const enabledCameras = cameras.filter((camera) => camera.enabled !== false);
            const camera = preferredCamera(enabledCameras);

            setText("edgeHomeDevice", primaryFamily.name || "家庭空间");
            setText("edgeHomeTime", device.worker_running ? "守护服务在线" : "守护服务暂停");

            if (!camera) {
                syncCameraEntryLinks(null);
                if (cameras.length) {
                    setText("edgeHomeTime", "等待重新启用摄像头");
                    setText("edgeHomeTitle", "当前没有启用中的摄像头");
                    setText("edgeHomeSubtitle", "先去接入页把一路摄像头设为当前，再进入守护主链。");
                    setAction("edgeHomePrimaryAction", "connect.html", "去接入页", "nest_cam_indoor");
                } else {
                    setText("edgeHomeTime", "等待摄像头接入");
                    setText("edgeHomeTitle", "还没有添加摄像头");
                    setText("edgeHomeSubtitle", "先打开本机守护服务管理台，把局域网摄像头接进来。");
                    setAction("edgeHomePrimaryAction", "connect.html", "去接入页", "nest_cam_indoor");
                }
                return;
            }

            syncCameraEntryLinks(camera);
            const event = importantEvent(events, camera);
            const snapshot = await GoHomeEdge.appLatestSnapshot(camera.id, { allowMissing: true });
            if (snapshot?.available === false) {
                setText("edgeHomeTime", `实时预览中 · ${camera.room || camera.name || "家里"} · ${device.detector_backend === "yolo" ? "YOLO 检测中" : "基础检测中"}`);
                setText("edgeHomeTitle", event ? event.summary : "本机守护服务已连接，正在同步最新检测摘要");
                setText("edgeHomeSubtitle", event ? "本机服务已经生成一条待确认提醒，建议先去事件页查看截图和处理状态。" : "实时画面已经恢复，检测摘要会在后台下一轮抽帧后补上。");
                setText("edgeHomeFactTitle", event ? GoHomeEdge.eventLabel(event.type) : "实时画面正常");
                setText("edgeHomeFactSub", event ? `${GoHomeEdge.fmtDateTime(event.occurred_at)} 触发，来自 ${event.camera_name || camera.name || "摄像头"}。` : "当前优先展示实时视频，证据截图稍后同步。");
                setText("edgeHomeFeelingTitle", event ? "有一条提醒待确认" : "家里平稳");
                setText("edgeHomeFeelingSub", event ? "这类信息应该进入告警处理流程，而不是只作为普通动态展示。" : "不影响你先进入守护页查看实时画面。");
                setText("edgeHomeActionTitle", event ? "先查看事件，再联系老人" : "继续观察");
                setText("edgeHomeActionSub", event ? "确认安全后可以标记已处理；误报也要保留记录。" : "等检测摘要同步后，首页会自动更新。");
                setText("edgeHomeSnapshotTime", "等待检测摘要");
                setText("edgeHomeSnapshotRoom", camera.room || camera.name || "家里动态");
                setText("edgeHomeSnapshotHeadline", event ? event.summary : "实时画面已连接");
                setText("edgeHomeSnapshotSub", "后台正在生成最新证据截图");
                return;
            }

            const state = snapshotState(snapshot);
            const image = $("edgeHomeSnapshotImage");
            if (image && snapshot.image_url) {
                image.src = await GoHomeEdge.v1VideoMediaPlaybackUrl(snapshot.image_url);
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
            if (error?.status === 401) {
                GoHomeEdge.clearAuthToken();
                fallbackGuestHome();
                return;
            }
            toggleSetupMode(true);
            toggleMessageSection(false);
            setSetupStates("未连接", "未连接", "未连接", "离线");
            setText("edgeHomeDevice", "本机守护服务未连接");
            setText("edgeHomeTime", "等待 edge-agent");
            setText("edgeHomeTitle", "主页面还没有连到本机守护服务");
            setText("edgeHomeSubtitle", error.message || "启动 8711 服务后，这里会自动切换成真实摄像头状态。");
            setAction("edgeHomePrimaryAction", "login.html", "去登录", "login");
            setAction("edgeHomeSecondaryAction", "family.html", "家庭空间", "groups");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        render();
        setInterval(render, 10000);
    });
})();
