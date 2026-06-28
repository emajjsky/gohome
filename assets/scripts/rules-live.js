(function () {
    const state = {
        detectorBackend: "basic",
        saving: false,
        saveTimer: null,
        latestSavedAt: null,
    };

    const $ = (id) => document.getElementById(id);

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
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

    function yoloAvailable() {
        return state.detectorBackend === "yolo";
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

    function readPayload() {
        const personEnabled = $("personDetectionEnabled").checked && yoloAvailable();
        return {
            capture_interval_seconds: numberValue("captureInterval"),
            no_motion_seconds: numberValue("noMotionSeconds"),
            no_person_seconds: numberValue("noPersonSeconds"),
            offline_enabled: $("offlineEnabled").checked,
            black_screen_enabled: $("blackEnabled").checked,
            no_motion_enabled: $("noMotionEnabled").checked,
            person_detection_enabled: yoloAvailable() && (personEnabled || $("noPersonMirror").checked),
            fall_detection_enabled: $("fallDetectionEnabled").checked && yoloAvailable(),
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
        $("notificationEnabled").checked = Boolean(rules.notification_enabled);
    }

    function runtimeMatches(expectedUpdatedAt, runtime) {
        if (!expectedUpdatedAt) return true;
        const loadedAt = runtime?.last_rules_loaded_at;
        if (!loadedAt) return false;
        return new Date(loadedAt).getTime() >= new Date(expectedUpdatedAt).getTime();
    }

    async function refreshRuntime(expectedUpdatedAt = null, attempts = 1, waitMs = 0) {
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
                await new Promise((resolve) => setTimeout(resolve, 500));
            }
        }
        const running = Boolean(runtime?.worker_running);
        if (!running) {
            setText("rulesStatusTitle", "规则已保存，worker 未运行");
            setText("rulesStatusText", "规则已经写入本机数据库，但后台守护循环当前没有运行。");
            setSaveState("待运行", "bad");
            return runtime;
        }
        if (expectedUpdatedAt && !runtimeMatches(expectedUpdatedAt, runtime)) {
            setText("rulesStatusTitle", "规则已保存，等待生效");
            setText("rulesStatusText", "规则已经保存，正在等待下一轮抽帧读取新配置。");
            setSaveState("等待生效");
            return runtime;
        }
        const loadedAt = runtime?.last_rules_loaded_at ? fmtDateTime(runtime.last_rules_loaded_at) : "刚刚";
        setText("rulesStatusTitle", "规则已同步");
        setText("rulesStatusText", `worker 最近一次读取规则时间：${loadedAt}。`);
        setSaveState("已生效", "ok");
        return runtime;
    }

    function applyCapability() {
        const yolo = yoloAvailable();
        $("detectorBadge").textContent = yolo ? "YOLO 已启用" : "基础检测";
        $("personHint").textContent = yolo ? "当前由 YOLO 检测人形和人数。" : "需要以 YOLO 模式启动 edge-agent。";
        $("fallHint").textContent = yolo ? "当前基于 YOLO 人框比例生成候选提醒。" : "需要以 YOLO 模式启动 edge-agent。";
        ["personDetectionEnabled", "noPersonMirror", "fallDetectionEnabled"].forEach((id) => {
            const node = $(id);
            node.disabled = !yolo;
            if (!yolo) node.checked = false;
        });
    }

    async function saveRules(immediate = false) {
        clearTimeout(state.saveTimer);
        const run = async () => {
            if (state.saving) return;
            state.saving = true;
            setSaveState("保存中");
            try {
                ["captureInterval", "noMotionSeconds", "noPersonSeconds"].forEach(clampInput);
                if ($("noPersonMirror").checked) $("personDetectionEnabled").checked = true;
                if ($("personDetectionEnabled").checked) $("noPersonMirror").checked = true;
                const saved = await GoHomeEdge.updateRules(readPayload());
                state.latestSavedAt = saved.updated_at || null;
                applyRules(saved);
                applyCapability();
                await refreshRuntime(state.latestSavedAt, 3, 250);
            } catch (error) {
                setSaveState("保存失败", "bad");
                setText("rulesStatusTitle", "规则保存失败");
                setText("rulesStatusText", error.message || "请确认本机 edge-agent 正在运行。");
            } finally {
                state.saving = false;
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
            const [device, rules, runtime] = await Promise.all([GoHomeEdge.device(), GoHomeEdge.rules(), GoHomeEdge.rulesRuntime()]);
            state.detectorBackend = device.detector_backend || "basic";
            state.latestSavedAt = rules.updated_at || null;
            applyRules(rules);
            applyCapability();
            await refreshRuntime(state.latestSavedAt);
            if (!(runtime && runtime.worker_running)) {
                setText("rulesStatusText", "规则可以读取和保存，但后台守护循环当前没有运行。");
            } else if (!runtime.last_rules_loaded_at) {
                setText("rulesStatusText", `${device.detector_backend === "yolo" ? "YOLO" : "基础"} 后端已连接，等待第一轮 worker 读取规则。`);
            }
        } catch (error) {
            setSaveState("离线", "bad");
            setText("rulesStatusTitle", "本机服务未连接");
            setText("rulesStatusText", error.message || "启动 edge-agent 后才能读取和保存规则。");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        initialize();

        document.querySelectorAll("[data-rule-input], #captureInterval, #noMotionSeconds, #noPersonSeconds").forEach((node) => {
            node.addEventListener("change", () => saveRules(false));
        });

        $("personDetectionEnabled").addEventListener("change", () => {
            $("noPersonMirror").checked = $("personDetectionEnabled").checked;
        });

        $("noPersonMirror").addEventListener("change", () => {
            $("personDetectionEnabled").checked = $("noPersonMirror").checked;
        });

        $("saveRulesButton").addEventListener("click", () => {
            saveRules(true).catch(() => {});
        });
    });
})();
