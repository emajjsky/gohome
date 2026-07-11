(function () {
    const $ = (id) => document.getElementById(id);
    const state = { familyId: null, canEdit: false };

    function setStatus(mode) {
        const labels = {
            active: ["正常守护中", "所有有效摄像头会共同判断家中是否长时间无人。"],
            away: ["临时外出", "长时间无人提醒已暂停，画面仍可正常查看。"],
            travel: ["旅行中", "旅行期间不会因为家中无人而报警。"],
            hospital: ["住院或陪护", "就医期间暂停长时间无人提醒。"],
            paused: ["守护已暂停", "画面仍可正常查看。"],
            paused_until: ["定时暂停", "到设定时间后自动恢复正常守护。"],
        };
        const copy = labels[mode] || labels.active;
        $("presenceSettingsTitle").textContent = copy[0];
        $("presenceSettingsText").textContent = copy[1];
    }

    function syncPausedField() {
        const mode = document.querySelector('input[name="mode"]:checked')?.value || "active";
        $("pausedUntilField").classList.toggle("hidden", mode !== "paused_until");
        setStatus(mode);
    }

    async function load() {
        try {
            GoHomeEdge.bootstrapLaunchState?.();
            await GoHomeEdge.connect();
            const families = await GoHomeEdge.myFamilies();
            const requested = Number(new URLSearchParams(window.location.search).get("family_id"));
            const family = families.find((item) => Number(item.id) === requested) || families[0];
            if (!family) throw new Error("还没有家庭空间");
            state.familyId = family.id;
            const presence = await GoHomeEdge.v1PresenceState(family.id);
            state.canEdit = Boolean(presence.can_edit);
            const mode = presence.monitoring?.mode || "active";
            const radio = document.querySelector(`input[name="mode"][value="${CSS.escape(mode)}"]`);
            if (radio) radio.checked = true;
            if (presence.monitoring?.paused_until) {
                const date = new Date(presence.monitoring.paused_until);
                if (Number.isFinite(date.getTime())) {
                    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
                    $("pausedUntil").value = local;
                }
            }
            document.querySelectorAll("input, button[type=submit]").forEach((node) => { node.disabled = !state.canEdit; });
            $("presencePermissionHint").classList.toggle("hidden", state.canEdit);
            syncPausedField();
        } catch (error) {
            $("presenceSettingsTitle").textContent = "暂时无法读取设置";
            $("presenceSettingsText").textContent = error.message || "请稍后重试。";
        }
    }

    document.addEventListener("change", (event) => {
        if (event.target?.name === "mode") syncPausedField();
    });

    $("presenceSettingsForm")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!state.canEdit || !state.familyId) return;
        const button = $("presenceSaveButton");
        const mode = document.querySelector('input[name="mode"]:checked')?.value || "active";
        const pausedUntil = mode === "paused_until" ? $("pausedUntil").value : "";
        if (mode === "paused_until" && (!pausedUntil || Date.parse(pausedUntil) <= Date.now())) {
            $("presenceSettingsText").textContent = "请选择晚于当前时间的自动恢复时间。";
            return;
        }
        button.disabled = true;
        button.textContent = "正在保存";
        try {
            const result = await GoHomeEdge.v1UpdatePresenceMonitoring(state.familyId, {
                mode,
                enabled: true,
                paused_until: pausedUntil ? new Date(pausedUntil).toISOString() : "",
            });
            setStatus(result.monitoring?.mode || mode);
            button.textContent = "已保存";
            window.setTimeout(() => { button.textContent = "保存守护状态"; button.disabled = false; }, 1200);
        } catch (error) {
            $("presenceSettingsText").textContent = error.message || "保存失败，请稍后重试。";
            button.textContent = "重新保存";
            button.disabled = false;
        }
    });

    document.addEventListener("DOMContentLoaded", load);
})();
