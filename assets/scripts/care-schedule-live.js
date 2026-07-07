(function () {
    const $ = (id) => document.getElementById(id);
    const state = {
        family: null,
        preferences: null,
        saving: false,
    };

    const defaultSchedule = {
        enabled: true,
        delivery_time: "08:30",
        timezone: "Asia/Shanghai",
        channels: ["app_push"],
        content_types: {
            home_status: true,
            elder_interest_topics: true,
            health_tips: true,
            weather: true,
            holidays: true,
            anniversaries: true,
            visit_reminder: true,
        },
        interest_topics: ["养生", "天气", "戏曲", "家常"],
        message_focus: "用轻松自然的语气提醒今天家里状态，顺带给一个适合打电话时聊的话题。",
        visit_reminder: {
            enabled: true,
            threshold_days: 14,
            location_tracking_enabled: false,
            last_visit_at: "",
        },
        anniversaries: [],
    };

    function schedule() {
        return {
            ...defaultSchedule,
            ...(state.preferences?.metadata?.care_card_schedule || {}),
            content_types: {
                ...defaultSchedule.content_types,
                ...(state.preferences?.metadata?.care_card_schedule?.content_types || {}),
            },
            visit_reminder: {
                ...defaultSchedule.visit_reminder,
                ...(state.preferences?.metadata?.care_card_schedule?.visit_reminder || {}),
            },
        };
    }

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function setFeedback(value) {
        setText("careScheduleFeedback", value || "");
    }

    function checkedValues(name) {
        return [...document.querySelectorAll(`[name="${name}"]:checked`)].map((node) => node.value);
    }

    function setChecked(name, values = []) {
        const set = new Set(values);
        document.querySelectorAll(`[name="${name}"]`).forEach((node) => {
            node.checked = set.has(node.value);
        });
    }

    function renderAnniversaries(items = []) {
        const list = $("anniversaryList");
        if (!list) return;
        const anniversaries = items.length ? items : [{ label: "", date: "", repeat: "yearly" }];
        list.innerHTML = anniversaries.map((item, index) => `
            <div class="anniversary-row grid grid-cols-[minmax(0,1fr)_140px_40px] gap-2 items-center" data-anniversary-row>
                <input class="care-input" data-field="label" value="${escapeHtml(item.label || "")}" placeholder="纪念日">
                <input class="care-input" data-field="date" type="date" value="${escapeHtml(item.date || "")}">
                <button class="icon-button" type="button" data-remove-anniversary="${index}" aria-label="删除纪念日">
                    <span class="material-symbols-outlined">close</span>
                </button>
            </div>
        `).join("");
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function render() {
        const current = schedule();
        $("scheduleEnabled").checked = Boolean(current.enabled);
        $("deliveryTime").value = current.delivery_time || "08:30";
        $("messageFocus").value = current.message_focus || defaultSchedule.message_focus;
        $("visitThreshold").value = String(current.visit_reminder?.threshold_days || 14);
        $("locationTracking").checked = Boolean(current.visit_reminder?.location_tracking_enabled);
        $("lastVisitAt").value = current.visit_reminder?.last_visit_at || "";
        setChecked("contentType", Object.entries(current.content_types || {})
            .filter(([, enabled]) => enabled)
            .map(([key]) => key));
        setChecked("interestTopic", current.interest_topics || []);
        renderAnniversaries(current.anniversaries || []);
        updateSummary();
    }

    function collectAnniversaries() {
        return [...document.querySelectorAll("[data-anniversary-row]")]
            .map((row) => ({
                label: row.querySelector('[data-field="label"]')?.value.trim() || "",
                date: row.querySelector('[data-field="date"]')?.value.trim() || "",
                repeat: "yearly",
            }))
            .filter((item) => item.label && item.date);
    }

    function payloadFromForm() {
        const selectedContent = new Set(checkedValues("contentType"));
        const existing = schedule();
        return {
            ...state.preferences,
            text_model_enabled: true,
            content_recommendations_enabled: selectedContent.has("elder_interest_topics"),
            metadata: {
                ...(state.preferences?.metadata || {}),
                care_card_schedule: {
                    ...existing,
                    enabled: $("scheduleEnabled").checked,
                    delivery_time: $("deliveryTime").value || "08:30",
                    timezone: "Asia/Shanghai",
                    channels: ["app_push"],
                    content_types: {
                        home_status: selectedContent.has("home_status"),
                        elder_interest_topics: selectedContent.has("elder_interest_topics"),
                        health_tips: selectedContent.has("health_tips"),
                        weather: selectedContent.has("weather"),
                        holidays: selectedContent.has("holidays"),
                        anniversaries: selectedContent.has("anniversaries"),
                        visit_reminder: selectedContent.has("visit_reminder"),
                    },
                    interest_topics: checkedValues("interestTopic"),
                    message_focus: $("messageFocus").value.trim(),
                    visit_reminder: {
                        enabled: selectedContent.has("visit_reminder"),
                        threshold_days: Number($("visitThreshold").value || 14),
                        location_tracking_enabled: $("locationTracking").checked,
                        last_visit_at: $("lastVisitAt").value || "",
                    },
                    anniversaries: collectAnniversaries(),
                },
            },
        };
    }

    function updateSummary() {
        const time = $("deliveryTime")?.value || "08:30";
        const enabled = $("scheduleEnabled")?.checked;
        const selected = checkedValues("contentType").length;
        setText("scheduleStatus", enabled ? "已开启" : "已暂停");
        setText("scheduleSummary", `${time} · ${selected} 类内容`);
    }

    async function resolveFamily() {
        const payload = await GoHomeEdge.v1Households();
        const families = Array.isArray(payload) ? payload : (payload.families || []);
        return families[0] || null;
    }

    async function load() {
        if (!window.GoHomeEdge) return;
        GoHomeEdge.bootstrapLaunchState?.();
        await GoHomeEdge.connect();
        state.family = await resolveFamily();
        if (!state.family) {
            setFeedback("还没有家庭空间");
            return;
        }
        state.preferences = await GoHomeEdge.v1CarePreferences(state.family.id);
        setText("familyName", state.family.name || "默认家庭");
        render();
    }

    async function persist(options = {}) {
        if (!state.family || state.saving) return;
        state.saving = true;
        setFeedback("正在保存");
        try {
            state.preferences = await GoHomeEdge.v1UpdateCarePreferences(state.family.id, payloadFromForm());
            render();
            setFeedback("已保存");
            return state.preferences;
        } catch (error) {
            setFeedback(error.message || "保存失败");
            if (options.throwOnError) throw error;
        } finally {
            state.saving = false;
        }
    }

    async function save(event) {
        event?.preventDefault();
        await persist();
    }

    async function generateNow() {
        if (!state.family) return;
        setFeedback("正在生成今日卡片");
        try {
            await persist({ throwOnError: true });
            const result = await GoHomeEdge.v1GenerateCareCard({ family_id: state.family.id, force: true });
            setFeedback(`已生成：${result.card?.title || "今日关怀"}`);
        } catch (error) {
            setFeedback(error.message || "生成失败");
        }
    }

    document.addEventListener("change", (event) => {
        if (event.target.matches("input")) updateSummary();
    });

    document.addEventListener("input", (event) => {
        if (event.target.matches("input, textarea")) updateSummary();
    });

    document.addEventListener("click", (event) => {
        const remove = event.target.closest("[data-remove-anniversary]");
        if (remove) {
            remove.closest("[data-anniversary-row]")?.remove();
            updateSummary();
            return;
        }
        if (event.target.closest("#addAnniversary")) {
            const rows = collectAnniversaries();
            rows.push({ label: "", date: "", repeat: "yearly" });
            renderAnniversaries(rows);
        }
    });

    $("careScheduleForm")?.addEventListener("submit", save);
    $("generateCareNow")?.addEventListener("click", generateNow);

    load().catch((error) => {
        setFeedback(error.message || "读取失败");
    });
})();
