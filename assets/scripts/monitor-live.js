(function () {
    const $ = (id) => document.getElementById(id);
    const state = {
        familyId: null,
        cameras: [],
        streamControllers: new Map(),
        cameraSignature: "",
        inFlight: false,
    };

    const safetyTypes = new Set(["fall_candidate", "prolonged_floor_lying", "fire_candidate", "long_absence"]);
    const postureLabels = {
        standing: "站立",
        sitting: "坐姿",
        squatting: "蹲姿",
        bending: "弯腰",
        lying: "躺姿",
        fallen: "疑似跌倒",
        walking: "走动",
        upper_body: "上半身入镜",
        low_body: "低位姿态",
        unknown: "持续识别中",
    };
    const eventLabels = {
        fall_candidate: "疑似跌倒",
        prolonged_floor_lying: "长时间倒地",
        fire_candidate: "疑似烟火",
        long_absence: "长时间未见到老人",
    };

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function pageHref(path) {
        return window.GoHomeEdge?.pageHref?.(path) || path;
    }

    function domId(prefix, cameraId) {
        return `${prefix}-${String(cameraId).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    }

    function cameraLabel(camera) {
        return camera.name || camera.room || "摄像头";
    }

    function relativeTime(value, empty = "尚未记录") {
        const timestamp = Date.parse(value || "");
        if (!Number.isFinite(timestamp)) return empty;
        const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
        if (seconds < 60) return "刚刚";
        if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟前`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时前`;
        return `${Math.floor(seconds / 86400)}天前`;
    }

    function coverageLabel(presence) {
        const value = Number(presence?.observation_coverage);
        return Number.isFinite(value) ? `${Math.round(value * 100)}%` : "待统计";
    }

    function petTypesLabel(types) {
        const labels = { cat: "猫", dog: "狗" };
        const values = [...new Set((Array.isArray(types) ? types : []).map((item) => labels[String(item)] || String(item)).filter(Boolean))];
        return values.join("、") || "宠物";
    }

    function postureFromEvaluation(evaluation) {
        const event = evaluation?.candidates?.[0] || null;
        const candidates = [
            evaluation?.analysis?.posture,
            evaluation?.analysis?.pose_factor_graph?.posture,
            event?.payload?.verification?.result?.posture,
            event?.payload?.evidence?.posture,
            event?.payload?.evidence?.pose_factor_graph?.posture,
        ];
        const posture = candidates.find(Boolean);
        return postureLabels[String(posture || "unknown")] || "持续识别中";
    }

    function presenceCopy(presence) {
        const mode = String(presence?.monitoring?.mode || "active");
        if (presence?.status === "paused") {
            const labels = { away: "临时外出", travel: "旅行中", hospital: "住院陪护", paused: "已暂停", paused_until: "定时暂停" };
            return {
                eyebrow: "无人提醒已暂停",
                title: labels[mode] || "守护已暂停",
                text: "摄像头仍可查看，但暂停判断长时间无人。恢复正常守护后会重新累计。",
                tone: "paused",
            };
        }
        if (presence?.status === "long_absence") {
            const petNote = presence?.pet_activity_recent
                ? `期间检测到${petTypesLabel(presence.pet_types)}活动，但宠物不计入老人出现记录。`
                : "";
            return {
                eyebrow: "需要尽快确认",
                title: "较长时间没有看到老人",
                text: `所有有效摄像头持续未检测到人，请联系家里确认情况。${petNote}`,
                tone: "alert",
            };
        }
        const petSeenAt = Date.parse(presence?.last_pet_seen_at || "");
        const personSeenAt = Date.parse(presence?.last_person_seen_at || "");
        if (presence?.pet_activity_recent && Number.isFinite(petSeenAt) && (!Number.isFinite(personSeenAt) || petSeenAt > personSeenAt)) {
            return {
                eyebrow: "家庭观察正常",
                title: `暂未看到老人，检测到${petTypesLabel(presence.pet_types)}活动`,
                text: `最近一次宠物活动在 ${relativeTime(presence.last_pet_seen_at)}。宠物不会重置老人未见计时，守护仍在继续。`,
                tone: "good",
            };
        }
        if (presence?.status === "suspended") {
            return {
                eyebrow: "观察条件不足",
                title: "部分画面没有持续同步",
                text: "无人判断已自动暂停，避免因摄像头离线或覆盖不足造成误报。",
                tone: "warn",
            };
        }
        return {
            eyebrow: "家庭观察正常",
            title: presence?.last_person_seen_at ? "刚刚在家中看到人" : "正在建立观察记录",
            text: presence?.last_person_seen_at
                ? `最近一次在 ${relativeTime(presence.last_person_seen_at)} 检测到人物，当前没有长时间无人提醒。`
                : "摄像头已进入有效观察，检测到人物后会开始记录。",
            tone: "good",
        };
    }

    function renderPresence(presence, device) {
        const copy = presenceCopy(presence);
        const hero = $("familyPresenceHero");
        if (hero) hero.dataset.tone = copy.tone;
        setText("familyPresenceEyebrow", copy.eyebrow);
        setText("edgeStatusTitle", copy.title);
        setText("edgeStatusText", copy.text);
        setText("familyPresenceCameraCount", `${presence?.valid_camera_count || 0}/${presence?.camera_count || state.cameras.length}`);
        setText("familyPresenceLastSeen", relativeTime(presence?.last_person_seen_at, "未见到"));
        const cameraPresence = Array.isArray(presence?.cameras) ? presence.cameras : [];
        const coverageValues = cameraPresence
            .map((item) => Number(item.presence?.observation_coverage))
            .filter(Number.isFinite);
        const average = coverageValues.length ? coverageValues.reduce((sum, value) => sum + value, 0) / coverageValues.length : null;
        setText("familyPresenceCoverage", Number.isFinite(average) ? `${Math.round(average * 100)}%` : "待统计");
        setText("familyPetActivity", presence?.last_pet_seen_at
            ? `${petTypesLabel(presence.pet_types)} · ${relativeTime(presence.last_pet_seen_at)}`
            : "未检测到");
        setText("edgeDeviceStatus", device?.worker_running ? "家庭盒子在线" : "家庭盒子待连接");
        setText("edgeDetector", device?.worker_running ? "视觉感知运行中" : "等待视觉服务");
    }

    function cameraStructure(cameras) {
        const grid = $("edgeMonitorCameraGrid");
        if (!grid) return;
        const signature = cameras.map((camera) => `${camera.id}:${camera.name || ""}:${camera.room || ""}`).join("|");
        if (signature === state.cameraSignature) return;
        const restoredCameraIds = [...grid.querySelectorAll("img[id^='monitorStream-']")]
            .map((image) => image.id.replace("monitorStream-", ""))
            .join("|");
        const cameraIds = cameras.map((camera) => String(camera.id)).join("|");
        if (!state.cameraSignature && cameras.length && (
            grid.dataset.cameraSignature === signature || restoredCameraIds === cameraIds
        )) {
            state.cameraSignature = signature;
            grid.dataset.cameraSignature = signature;
            return;
        }
        state.cameraSignature = signature;
        grid.dataset.cameraSignature = signature;
        state.streamControllers.forEach((controller) => controller.dispose());
        state.streamControllers.clear();
        if (!cameras.length) {
            grid.innerHTML = `
                <div class="gohome-panel gohome-empty-state">
                    <span class="material-symbols-outlined">linked_camera</span>
                    <h3>还没有接入摄像头</h3>
                    <p>完成家庭盒子绑定后，在设备管理中添加摄像头。</p>
                    <a class="gohome-camera-action mt-4" href="${pageHref("cameras.html")}">进入设备管理</a>
                </div>`;
            return;
        }
        grid.innerHTML = cameras.map((camera) => `
            <article class="gohome-camera-card gohome-observation-card">
                <a href="${pageHref(`watch.html?camera_id=${encodeURIComponent(camera.id)}`)}" class="gohome-camera-live">
                    <img id="${domId("monitorStream", camera.id)}" alt="${escapeHtml(cameraLabel(camera))}实时画面"/>
                    <span class="gohome-live-badge">实时</span>
                    <p id="${domId("streamState", camera.id)}" class="gohome-stream-label">正在连接画面</p>
                </a>
                <div class="gohome-camera-copy">
                    <div class="gohome-camera-title-row">
                        <div><h4>${escapeHtml(cameraLabel(camera))}</h4><p id="${domId("cameraSeen", camera.id)}">正在同步观察记录</p></div>
                        <span id="${domId("cameraStatus", camera.id)}" class="app-mini-pill muted">同步中</span>
                    </div>
                    <div class="gohome-observation-facts">
                        <span><small>当前姿态</small><strong id="${domId("cameraPosture", camera.id)}">识别中</strong></span>
                        <span><small>观察覆盖</small><strong id="${domId("cameraCoverage", camera.id)}">待统计</strong></span>
                        <span><small>最近见到人</small><strong id="${domId("cameraPersonSeen", camera.id)}">尚未记录</strong></span>
                        <span><small>宠物活动</small><strong id="${domId("cameraPetSeen", camera.id)}">尚未记录</strong></span>
                    </div>
                </div>
            </article>`).join("");
    }

    function attachStreams(cameras) {
        cameras.forEach((camera) => {
            if (state.streamControllers.has(Number(camera.id))) return;
            const image = $(domId("monitorStream", camera.id));
            if (!image) return;
            const controller = GoHomeEdge.createManagedVideoStream(image, {
                cameraId: camera.id,
                scene: "monitor",
                snapshotRefreshMs: 3000,
                onStateChange(nextState) {
                    const labels = {
                        playing: "实时画面已连接",
                        snapshot: "实时画面已连接",
                        waiting: "等待家庭盒子画面",
                        loading: "正在连接画面",
                        error: "画面暂不可用",
                    };
                    setText(domId("streamState", camera.id), labels[nextState] || "等待画面");
                },
            });
            state.streamControllers.set(Number(camera.id), controller);
        });
    }

    function updateCamera(camera, presenceCamera, evaluation) {
        const online = presenceCamera?.observation_valid === true;
        const status = $(domId("cameraStatus", camera.id));
        if (status) {
            const reasonLabels = {
                camera_offline: "摄像头离线",
                config_not_synced: "配置同步中",
                report_stale: "数据已超时",
                coverage_insufficient: "覆盖不足",
            };
            status.textContent = online ? "有效观察" : (reasonLabels[presenceCamera?.observation_reason] || "暂未观察");
            status.className = `app-mini-pill ${online ? "good" : "warn"}`;
        }
        setText(domId("cameraSeen", camera.id), online ? "画面与检测记录正在持续回传" : "当前不参与长时间无人判断");
        setText(domId("cameraCoverage", camera.id), coverageLabel(presenceCamera?.presence || camera.presence));
        setText(domId("cameraPersonSeen", camera.id), relativeTime(presenceCamera?.presence?.last_person_seen_at || camera.presence?.last_person_seen_at));
        const petPresence = presenceCamera?.presence || camera.presence || {};
        setText(domId("cameraPetSeen", camera.id), petPresence.last_pet_seen_at
            ? `${petTypesLabel(petPresence.pet_types)} · ${relativeTime(petPresence.last_pet_seen_at)}`
            : "未检测到");
        setText(domId("cameraPosture", camera.id), postureFromEvaluation(evaluation));
    }

    function renderIncidents(events) {
        const list = $("activeIncidentList");
        const incidents = (Array.isArray(events) ? events : [])
            .filter((event) => safetyTypes.has(String(event.event_type || event.type || ""))
                && !event.acknowledged
                && ["active", "verifying", "confirmed", "uncertain"].includes(String(event.payload?.incident?.status || "")))
            .slice(0, 4);
        setText("activeIncidentCount", `${incidents.length} 条`);
        if (!list) return;
        if (!incidents.length) {
            list.innerHTML = `<div class="gohome-incident-empty"><span class="material-symbols-outlined">verified</span><div><strong>暂无待确认事件</strong><p>家庭盒子会继续在本地观察。</p></div></div>`;
            return;
        }
        list.innerHTML = incidents.map((event) => `
            <article class="gohome-incident-row ${event.level === "critical" ? "critical" : ""}">
                <span class="material-symbols-outlined">${event.event_type === "fire_candidate" ? "local_fire_department" : "warning"}</span>
                <div><strong>${escapeHtml(eventLabels[event.event_type] || event.summary || "安全提醒")}</strong><p>${escapeHtml(event.room || event.camera_name || "家里")} · ${relativeTime(event.occurred_at || event.created_at)}</p></div>
                <span class="app-mini-pill warn">待确认</span>
            </article>`).join("");
    }

    async function refresh() {
        if (!window.GoHomeEdge || state.inFlight) return;
        state.inFlight = true;
        try {
            GoHomeEdge.bootstrapLaunchState?.();
            await GoHomeEdge.connect();
            const families = await GoHomeEdge.myFamilies();
            const requestedFamilyId = Number(new URLSearchParams(window.location.search).get("family_id"));
            const family = families.find((item) => Number(item.id) === requestedFamilyId) || families[0];
            if (!family) return;
            state.familyId = family.id;
            const [device, cameras, presence, events] = await Promise.all([
                GoHomeEdge.appDevice().catch(() => null),
                GoHomeEdge.appCameras().catch(() => []),
                GoHomeEdge.v1PresenceState(family.id),
                GoHomeEdge.appEvents("limit=50").catch(() => []),
            ]);
            state.cameras = cameras.filter((camera) => camera.enabled !== false);
            cameraStructure(state.cameras);
            attachStreams(state.cameras);
            renderPresence(presence, device);
            const evaluations = await Promise.all(state.cameras.map((camera) => GoHomeEdge.appLatestEvaluation(camera.id).catch(() => null)));
            state.cameras.forEach((camera, index) => {
                const presenceCamera = presence.cameras?.find((item) => Number(item.id) === Number(camera.id));
                updateCamera(camera, presenceCamera, evaluations[index]);
            });
            renderIncidents(events);
        } catch (error) {
            if (error?.status === 401) {
                GoHomeEdge.clearAuthToken();
                window.location.href = GoHomeEdge.loginHref(GoHomeEdge.currentPagePath());
                return;
            }
            if (window.GoHomeAppStore?.hasVisibleState?.()) return;
            setText("edgeStatusTitle", "暂时无法读取家庭状态");
            setText("edgeStatusText", error.message || "请稍后重试。");
        } finally {
            state.inFlight = false;
            window.GoHomeAppStore?.markPageReady?.();
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        window.GoHomeRefreshPage = () => refresh();
        refresh();
        window.setInterval(refresh, 10000);
    });

    window.addEventListener("beforeunload", () => {
        state.streamControllers.forEach((controller) => controller.dispose());
        state.streamControllers.clear();
    });
})();
