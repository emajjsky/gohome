(function () {
    const state = {
        detectorBackend: "basic",
        device: null,
        capabilities: {},
        saving: false,
        pendingSave: false,
        saveTimer: null,
        runtimeTimer: null,
        latestSavedAt: null,
        staleRulesReconciled: false,
    };

    const visionRules = {
        personDetectionEnabled: {
            capability: "person_detection",
            badgeId: "personCapabilityBadge",
            supportedText: "可用",
            unsupportedText: "需人形模型",
        },
        noPersonMirror: {
            capability: "no_person_detection",
            badgeId: "noPersonCapabilityBadge",
            supportedText: "随人形检测",
            unsupportedText: "需人形模型",
        },
        fallDetectionEnabled: {
            capability: "fall_candidate",
            badgeId: "fallCapabilityBadge",
            supportedText: "可用",
            unsupportedText: "需姿态模型",
        },
        activityDetectionEnabled: {
            capability: "activity_candidate",
            badgeId: "activityCapabilityBadge",
            supportedText: "可用",
            unsupportedText: "盒子未支持",
        },
        fireDetectionEnabled: {
            capability: "fire_candidate",
            badgeId: "fireCapabilityBadge",
            supportedText: "可用",
            unsupportedText: "盒子未支持",
        },
    };

    const $ = (id) => document.getElementById(id);

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function boolValue(value, fallback = false) {
        if (value === undefined || value === null || value === "") return fallback;
        if (typeof value === "string") {
            const normalized = value.trim().toLowerCase();
            if (!normalized) return fallback;
            return !["0", "false", "off", "no", "否"].includes(normalized);
        }
        return Boolean(value);
    }

    function setSaveState(text, tone = "neutral") {
        const node = $("rulesSaveState");
        if (!node) return;
        node.textContent = text;
        const toneClass = tone === "ok"
            ? "app-section-badge shrink-0"
            : tone === "bad"
                ? "px-2.5 py-1 rounded-full bg-[#fff0ed] text-[#b85d4c] text-[10px] font-bold shrink-0"
                : "px-2.5 py-1 rounded-full bg-surface-container-low text-on-surface-variant text-[10px] font-bold shrink-0";
        node.className = toneClass;
    }

    function fmtDateTime(value) {
        return GoHomeEdge.fmtDateTime ? GoHomeEdge.fmtDateTime(value) : (value || "-");
    }

    function normalizedBackend() {
        return String(state.capabilities.backend || state.detectorBackend || state.device?.detector_backend || "unknown").trim().toLowerCase();
    }

    function labelForBackend(backend) {
        if (backend === "yolo") return "YOLO 人形模型";
        if (backend === "demo") return "基础视觉管线";
        if (backend === "rtmpose" || backend === "pose") return "RTMPose 姿态模型";
        if (backend === "basic") return "基础视觉检测";
        return "盒子视觉管线";
    }

    function backendLabel() {
        return state.capabilities.backend_label || labelForBackend(normalizedBackend());
    }

    function normalizeCapabilities(raw = {}) {
        const backend = String(raw.backend || state.device?.detector_backend || state.detectorBackend || "unknown").trim().toLowerCase();
        return {
            quality_detection: boolValue(raw.quality_detection, true),
            motion_detection: boolValue(raw.motion_detection, true),
            person_detection: boolValue(raw.person_detection),
            no_person_detection: boolValue(raw.no_person_detection),
            fall_candidate: boolValue(raw.fall_candidate),
            activity_candidate: boolValue(raw.activity_candidate, true),
            fire_candidate: boolValue(raw.fire_candidate, true),
            pose_detection: boolValue(raw.pose_detection),
            backend,
            backend_label: raw.backend_label || labelForBackend(backend),
        };
    }

    function isCapabilityReady(inputId) {
        const item = visionRules[inputId];
        if (!item) return true;
        return boolValue(state.capabilities[item.capability]);
    }

    function numberValue(id) {
        const node = $(id);
        return Number(node?.value || 0);
    }

    function clampInput(id) {
        const node = $(id);
        if (!node) return;
        const min = Number(node.min || 0);
        const max = Number(node.max || 999999);
        const value = Number(node.value || 0);
        if (Number.isNaN(value)) return;
        node.value = String(Math.min(max, Math.max(min, value)));
    }

    function coerceNumber(value, fallback) {
        const num = Number(value);
        return Number.isFinite(num) ? num : fallback;
    }

    function setRuleCapability(inputId) {
        const input = $(inputId);
        const item = visionRules[inputId];
        if (!input || !item) return;
        const supported = isCapabilityReady(inputId);
        const row = input.closest(".rule-row");
        const badge = $(item.badgeId);
        input.disabled = false;
        if (row) row.dataset.capability = supported ? "supported" : "pending";
        if (badge) badge.textContent = supported ? item.supportedText : `待启用 · ${item.unsupportedText}`;
    }

    function enforceCapabilityChecks() {
        if (!$("personDetectionEnabled")?.checked) {
            if ($("noPersonMirror")) $("noPersonMirror").checked = false;
            return;
        }
        if ($("noPersonMirror")) {
            $("noPersonMirror").checked = true;
        }
    }

    function readPayload() {
        enforceCapabilityChecks();
        return {
            capture_interval_seconds: numberValue("captureInterval"),
            no_motion_seconds: numberValue("noMotionSeconds"),
            no_person_seconds: numberValue("noPersonSeconds"),
            offline_enabled: $("offlineEnabled").checked,
            black_screen_enabled: $("blackEnabled").checked,
            no_motion_enabled: $("noMotionEnabled").checked,
            person_detection_enabled: $("personDetectionEnabled").checked,
            fall_detection_enabled: $("fallDetectionEnabled").checked,
            activity_detection_enabled: $("activityDetectionEnabled")?.checked || false,
            fire_detection_enabled: $("fireDetectionEnabled")?.checked || false,
            notification_enabled: $("notificationEnabled").checked,
        };
    }

    function applyRules(rules) {
        $("captureInterval").value = String(coerceNumber(rules.capture_interval_seconds, 5));
        $("noMotionSeconds").value = String(coerceNumber(rules.no_motion_seconds, 300));
        $("noPersonSeconds").value = String(coerceNumber(rules.no_person_seconds, 300));
        $("offlineEnabled").checked = Boolean(rules.offline_enabled);
        $("blackEnabled").checked = Boolean(rules.black_screen_enabled);
        $("noMotionEnabled").checked = Boolean(rules.no_motion_enabled);
        $("personDetectionEnabled").checked = Boolean(rules.person_detection_enabled);
        $("noPersonMirror").checked = Boolean(rules.person_detection_enabled);
        $("fallDetectionEnabled").checked = Boolean(rules.fall_detection_enabled);
        if ($("activityDetectionEnabled")) $("activityDetectionEnabled").checked = Boolean(rules.activity_detection_enabled);
        if ($("fireDetectionEnabled")) $("fireDetectionEnabled").checked = Boolean(rules.fire_detection_enabled);
        $("notificationEnabled").checked = Boolean(rules.notification_enabled);
        enforceCapabilityChecks();
    }

    function hasUnsupportedEnabled(rules) {
        return Boolean(rules.person_detection_enabled && !isCapabilityReady("personDetectionEnabled"))
            || Boolean(rules.fall_detection_enabled && !isCapabilityReady("fallDetectionEnabled"))
            || Boolean(rules.activity_detection_enabled && !isCapabilityReady("activityDetectionEnabled"))
            || Boolean(rules.fire_detection_enabled && !isCapabilityReady("fireDetectionEnabled"));
    }

    function runtimeMatches(expectedUpdatedAt, runtime) {
        const desired = String(runtime?.desired_rule_version || "");
        const applied = String(runtime?.applied_rule_version || "");
        if (desired || applied) return Boolean(desired && applied && desired === applied);
        if (!expectedUpdatedAt) return true;
        const loadedAt = runtime?.last_rules_loaded_at;
        if (!loadedAt) return false;
        return new Date(loadedAt).getTime() >= new Date(expectedUpdatedAt).getTime();
    }

    function scheduleRuntimeRefresh(expectedUpdatedAt) {
        clearTimeout(state.runtimeTimer);
        if (!expectedUpdatedAt) return;
        state.runtimeTimer = setTimeout(() => {
            refreshRuntime(expectedUpdatedAt, 1).catch(() => {});
        }, 5000);
    }

    async function refreshRuntime(expectedUpdatedAt = null, attempts = 1, waitMs = 0) {
        clearTimeout(state.runtimeTimer);
        if (waitMs > 0) {
            await new Promise((resolve) => setTimeout(resolve, waitMs));
        }
        let runtime = null;
        for (let index = 0; index < attempts; index += 1) {
            runtime = await GoHomeEdge.rulesRuntime();
            if (runtimeMatches(expectedUpdatedAt, runtime)) {
                break;
            }
            if (index < attempts - 1) {
                await new Promise((resolve) => setTimeout(resolve, 700));
            }
        }
        const running = Boolean(runtime?.worker_running);
        if (!running) {
            setText("rulesStatusTitle", "规则已保存，等待盒子运行");
            setText("rulesStatusText", "家庭盒子恢复检测后，会读取这里保存的最新规则。");
            setSaveState("盒子未运行", "bad");
            return runtime;
        }
        if (!runtimeMatches(expectedUpdatedAt, runtime)) {
            setText("rulesStatusTitle", "规则已保存，等待盒子读取");
            setText("rulesStatusText", "规则已经保存，家庭盒子下一次同步后会按新配置检测。");
            setSaveState("待同步");
            scheduleRuntimeRefresh(expectedUpdatedAt);
            return runtime;
        }
        const loadedAt = runtime?.last_rules_loaded_at ? fmtDateTime(runtime.last_rules_loaded_at) : "刚刚";
        setText("rulesStatusTitle", "已同步到家庭盒子");
        setText("rulesStatusText", `${backendLabel()}已连接，最近一次读取规则时间：${loadedAt}。`);
        setSaveState("已生效", "ok");
        return runtime;
    }

    function applyCapability() {
        $("detectorBadge").textContent = backendLabel();
        Object.keys(visionRules).forEach(setRuleCapability);

        const personReady = isCapabilityReady("personDetectionEnabled");
        const fallReady = isCapabilityReady("fallDetectionEnabled");
        if (personReady && fallReady) {
            setText("personHint", `${backendLabel()}已连接，人形、无人和跌倒候选会随规则同步到盒子。`);
        } else if (personReady) {
            setText("personHint", `${backendLabel()}已连接，人形和无人提醒可用；跌倒候选已允许保存，盒子端模型启用后执行。`);
        } else {
            setText("personHint", "这里保存 App 的守护规则；当前盒子未启用人形/姿态模型时，相关规则会同步但不会产生命中。");
        }
        setText(
            "fallHint",
            fallReady
                ? "开启后盒子会用连续帧判断疑似跌倒，只生成候选提醒，仍需要家属确认。"
                : "可先保存规则；需要盒子启用人形或姿态模型后才会真正产生命中。"
        );
        setText(
            "activityHint",
            isCapabilityReady("activityDetectionEnabled")
                ? "用于久坐、长时间低活动等低风险候选，和安全告警分开呈现。"
                : "可先保存规则；当前盒子未回传活动状态能力时暂不产生命中。"
        );
        setText(
            "fireHint",
            isCapabilityReady("fireDetectionEnabled")
                ? "本地连续帧命中后生成候选提醒，减少单帧误报。"
                : "可先保存规则；当前盒子未回传明火或烟火能力时暂不产生命中。"
        );
        enforceCapabilityChecks();
    }

    async function reconcileUnsupportedRules(rules) {
        if (state.staleRulesReconciled || !hasUnsupportedEnabled(rules)) return rules;
        state.staleRulesReconciled = true;
        setText("rulesStatusTitle", "规则已保存，等待盒子能力");
        setText("rulesStatusText", "部分视觉规则已打开，但当前盒子未上报对应模型能力；模型启用后会按这些规则执行。");
        return rules;
    }

    async function saveRules(immediate = false) {
        clearTimeout(state.saveTimer);
        if (state.saving) {
            state.pendingSave = true;
        }
        const run = async () => {
            if (state.saving) {
                state.pendingSave = true;
                return;
            }
            state.saving = true;
            setSaveState("保存中");
            try {
                ["captureInterval", "noMotionSeconds", "noPersonSeconds"].forEach(clampInput);
                enforceCapabilityChecks();
                const saved = await GoHomeEdge.updateRules(readPayload());
                const superseded = state.pendingSave;
                state.latestSavedAt = saved.updated_at || null;
                if (!superseded) {
                    applyRules(saved);
                    applyCapability();
                    await refreshRuntime(state.latestSavedAt, 4, 250);
                }
            } catch (error) {
                setSaveState("保存失败", "bad");
                setText("rulesStatusTitle", "规则保存失败");
                setText("rulesStatusText", error.message || "请确认家庭盒子服务正在运行。");
            } finally {
                state.saving = false;
                if (state.pendingSave) {
                    state.pendingSave = false;
                    saveRules(true).catch(() => {});
                }
            }
        };
        if (immediate) {
            await run();
            return;
        }
        setSaveState("待保存");
        state.saveTimer = setTimeout(run, 650);
    }

    async function initialize() {
        try {
            await GoHomeEdge.connect();
            const [device, rules] = await Promise.all([GoHomeEdge.device(), GoHomeEdge.rules()]);
            state.device = device || {};
            state.detectorBackend = device.detector_backend || "unknown";
            state.capabilities = normalizeCapabilities(device.vision_capabilities || {});
            state.latestSavedAt = rules.updated_at || null;
            applyRules(rules);
            applyCapability();
            const activeRules = await reconcileUnsupportedRules(rules);
            await refreshRuntime(activeRules.updated_at || state.latestSavedAt, 2);
        } catch (error) {
            setSaveState("离线", "bad");
            setText("rulesStatusTitle", "本机服务未连接");
            setText("rulesStatusText", error.message || "启动家庭盒子服务后才能读取和保存规则。");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        initialize();

        $("personDetectionEnabled").addEventListener("change", () => {
            if ($("personDetectionEnabled").disabled) return;
            $("noPersonMirror").checked = $("personDetectionEnabled").checked && isCapabilityReady("noPersonMirror");
        });

        $("noPersonMirror").addEventListener("change", () => {
            if ($("noPersonMirror").disabled) return;
            $("personDetectionEnabled").checked = $("noPersonMirror").checked && isCapabilityReady("personDetectionEnabled");
        });

        document.querySelectorAll("[data-rule-input], #captureInterval, #noMotionSeconds, #noPersonSeconds").forEach((node) => {
            node.addEventListener("change", () => {
                if (node.disabled) return;
                enforceCapabilityChecks();
                saveRules(false);
            });
        });

        $("saveRulesButton").addEventListener("click", () => {
            saveRules(true).catch(() => {});
        });
    });
})();
