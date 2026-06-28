(function () {
    const state = {
        detectorBackend: "basic",
        saving: false,
        saveTimer: null,
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

    function yoloAvailable() {
        return state.detectorBackend === "yolo";
    }

    function numberValue(id) {
        const node = $(id);
        return Number(node?.value || 0);
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
        $("captureInterval").value = rules.capture_interval_seconds;
        $("noMotionSeconds").value = rules.no_motion_seconds;
        $("noPersonSeconds").value = rules.no_person_seconds;
        $("offlineEnabled").checked = Boolean(rules.offline_enabled);
        $("blackEnabled").checked = Boolean(rules.black_screen_enabled);
        $("noMotionEnabled").checked = Boolean(rules.no_motion_enabled);
        $("personDetectionEnabled").checked = Boolean(rules.person_detection_enabled);
        $("noPersonMirror").checked = Boolean(rules.person_detection_enabled);
        $("fallDetectionEnabled").checked = Boolean(rules.fall_detection_enabled);
        $("notificationEnabled").checked = Boolean(rules.notification_enabled);
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
                if ($("noPersonMirror").checked) $("personDetectionEnabled").checked = true;
                if ($("personDetectionEnabled").checked) $("noPersonMirror").checked = true;
                const saved = await GoHomeEdge.updateRules(readPayload());
                applyRules(saved);
                applyCapability();
                setSaveState("已保存", "ok");
                setText("rulesStatusTitle", "规则已同步");
                setText("rulesStatusText", "下一轮抽帧开始按新的规则执行。");
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
            const [device, rules] = await Promise.all([GoHomeEdge.device(), GoHomeEdge.rules()]);
            state.detectorBackend = device.detector_backend || "basic";
            applyRules(rules);
            applyCapability();
            setSaveState("已同步", "ok");
            setText("rulesStatusTitle", "本机规则已连接");
            setText("rulesStatusText", `${device.detector_backend === "yolo" ? "YOLO" : "基础"} 后端正在执行当前规则。`);
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
