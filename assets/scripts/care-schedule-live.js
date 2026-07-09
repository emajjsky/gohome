(function () {
    const $ = (id) => document.getElementById(id);
    const state = {
        family: null,
        preferences: null,
        profile: null,
        saving: false,
    };

    const contentTypeMeta = [
        ["home_status", "家里状态"],
        ["elder_interest_topics", "问候话题"],
        ["local_hotspots", "本地热点"],
        ["health_tips", "养生小贴士"],
        ["anti_fraud", "防诈骗提醒"],
        ["culture_entertainment", "文娱兴趣"],
        ["weather", "天气问候"],
        ["visit_reminder", "回家间隔"],
        ["holidays", "节日问候"],
        ["anniversaries", "纪念日"],
    ];

    const presets = {
        light: {
            types: ["home_status", "elder_interest_topics", "weather", "visit_reminder", "holidays", "anniversaries"],
            topics: ["天气", "家常", "本地生活"],
            focus: "先说明家里状态，再给一个适合电话开口的轻松话题。",
        },
        balanced: {
            types: ["home_status", "elder_interest_topics", "local_hotspots", "health_tips", "culture_entertainment", "weather", "visit_reminder", "holidays", "anniversaries"],
            topics: ["养生", "天气", "戏曲", "家常", "本地生活", "社区活动"],
            focus: "先说家里是否平稳，再结合天气、本地生活和老人兴趣给一个自然问候话题。",
        },
        safety: {
            types: ["home_status", "elder_interest_topics", "local_hotspots", "health_tips", "anti_fraud", "culture_entertainment", "weather", "visit_reminder", "holidays", "anniversaries"],
            topics: ["养生", "天气", "本地生活", "防诈骗", "社区活动", "电视节目"],
            focus: "先确认家里状态，再用轻松语气提醒天气、饮食和低频安全事项，不制造紧张感。",
        },
    };

    const defaultSchedule = {
        enabled: true,
        delivery_time: "08:30",
        timezone: "Asia/Shanghai",
        channels: ["app_push"],
        content_types: {
            home_status: true,
            elder_interest_topics: true,
            local_hotspots: true,
            health_tips: true,
            anti_fraud: false,
            culture_entertainment: true,
            weather: true,
            holidays: true,
            anniversaries: true,
            visit_reminder: true,
        },
        content_region: {
            city: "",
            district: "",
        },
        interest_topics: ["养生", "天气", "戏曲", "家常", "本地生活"],
        message_focus: "用轻松自然的语气提醒今天家里状态，顺带给一个适合打电话时聊的话题。",
        visit_reminder: {
            enabled: true,
            threshold_days: 14,
            location_tracking_enabled: false,
            last_visit_at: "",
        },
        delivery_rules: {
            daily_digest: { enabled: true, mode: "daily_digest" },
            home_status: { enabled: true, mode: "daily_digest_plus_exception", exception_push_enabled: true },
            elder_interest_topics: { enabled: true, mode: "daily_digest" },
            local_hotspots: { enabled: true, mode: "daily_digest_region" },
            health_tips: { enabled: true, mode: "daily_digest" },
            anti_fraud: { enabled: false, mode: "low_frequency" },
            culture_entertainment: { enabled: true, mode: "daily_digest" },
            weather: { enabled: true, mode: "daily_digest_provider" },
            holidays: { enabled: true, mode: "holiday_window", days_before: 1 },
            anniversaries: { enabled: true, mode: "annual_window", days_before: 3 },
            visit_reminder: { enabled: true, mode: "threshold", threshold_days: 14 },
        },
        anniversaries: [],
    };

    function mergeDeliveryRules(saved = {}) {
        return Object.fromEntries(Object.entries(defaultSchedule.delivery_rules).map(([key, value]) => [
            key,
            {
                ...value,
                ...((saved && typeof saved[key] === "object") ? saved[key] : {}),
            },
        ]));
    }

    function schedule() {
        const savedSchedule = state.preferences?.metadata?.care_card_schedule || {};
        return {
            ...defaultSchedule,
            ...savedSchedule,
            content_types: {
                ...defaultSchedule.content_types,
                ...(savedSchedule.content_types || {}),
            },
            content_region: {
                ...defaultSchedule.content_region,
                ...(savedSchedule.content_region || {}),
            },
            visit_reminder: {
                ...defaultSchedule.visit_reminder,
                ...(savedSchedule.visit_reminder || {}),
            },
            delivery_rules: mergeDeliveryRules(savedSchedule.delivery_rules),
        };
    }

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function setFeedback(value) {
        setText("careScheduleFeedback", value || "");
    }

    function setHtml(id, value) {
        const node = $(id);
        if (node) node.innerHTML = value;
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

    function normalizeTopic(value) {
        return String(value || "").replace(/\s+/g, "").trim().slice(0, 12);
    }

    function ensureInterestTopicChip(value) {
        const topic = normalizeTopic(value);
        const grid = $("interestTopicGrid");
        if (!topic || !grid) return null;
        const existing = [...grid.querySelectorAll('[name="interestTopic"]')]
            .find((node) => node.value === topic);
        if (existing) return existing;
        const label = document.createElement("label");
        label.className = "topic-chip";
        label.innerHTML = `<input name="interestTopic" value="${escapeHtml(topic)}" type="checkbox"><span>${escapeHtml(topic)}</span>`;
        grid.append(label);
        return label.querySelector("input");
    }

    function ensureInterestTopicChips(values = []) {
        values.forEach(ensureInterestTopicChip);
    }

    function renderAnniversaries(items = []) {
        const list = $("anniversaryList");
        if (!list) return;
        const anniversaries = items.length ? items : [{ label: "", date: "", repeat: "yearly" }];
        list.innerHTML = anniversaries.map((item, index) => `
            <div class="anniversary-row grid grid-cols-[minmax(0,1fr)_140px_40px] gap-2 items-center" data-anniversary-row>
                <input class="care-input" data-field="label" value="${escapeHtml(item.label || "")}" placeholder="例如：妈妈生日">
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
        $("contentCity").value = current.content_region?.city || state.profile?.city || "杭州";
        $("contentDistrict").value = current.content_region?.district || state.profile?.district || "";
        $("visitThreshold").value = String(current.visit_reminder?.threshold_days || 14);
        $("locationTracking").checked = false;
        $("lastVisitAt").value = current.visit_reminder?.last_visit_at || "";
        if ($("exceptionPushEnabled")) $("exceptionPushEnabled").checked = current.delivery_rules?.home_status?.exception_push_enabled !== false;
        if ($("holidayLeadDays")) $("holidayLeadDays").value = String(current.delivery_rules?.holidays?.days_before ?? 1);
        if ($("anniversaryLeadDays")) $("anniversaryLeadDays").value = String(current.delivery_rules?.anniversaries?.days_before ?? 3);
        setChecked("contentType", Object.entries(current.content_types || {})
            .filter(([, enabled]) => enabled)
            .map(([key]) => key));
        ensureInterestTopicChips(current.interest_topics || []);
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
        const visitThreshold = Number($("visitThreshold").value || 14);
        return {
            ...state.preferences,
            text_model_enabled: true,
            content_recommendations_enabled: [
                "elder_interest_topics",
                "local_hotspots",
                "health_tips",
                "anti_fraud",
                "culture_entertainment",
            ].some((key) => selectedContent.has(key)),
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
                        local_hotspots: selectedContent.has("local_hotspots"),
                        health_tips: selectedContent.has("health_tips"),
                        anti_fraud: selectedContent.has("anti_fraud"),
                        culture_entertainment: selectedContent.has("culture_entertainment"),
                        weather: selectedContent.has("weather"),
                        holidays: selectedContent.has("holidays"),
                        anniversaries: selectedContent.has("anniversaries"),
                        visit_reminder: selectedContent.has("visit_reminder"),
                    },
                    content_region: {
                        city: $("contentCity")?.value.trim() || state.profile?.city || "杭州",
                        district: $("contentDistrict")?.value.trim() || state.profile?.district || "",
                    },
                    interest_topics: checkedValues("interestTopic"),
                    message_focus: $("messageFocus").value.trim(),
                    visit_reminder: {
                        enabled: selectedContent.has("visit_reminder"),
                        threshold_days: visitThreshold,
                        location_tracking_enabled: false,
                        last_visit_at: $("lastVisitAt").value || "",
                    },
                    delivery_rules: {
                        daily_digest: { enabled: $("scheduleEnabled").checked, mode: "daily_digest" },
                        home_status: {
                            enabled: selectedContent.has("home_status"),
                            mode: "daily_digest_plus_exception",
                            exception_push_enabled: $("exceptionPushEnabled")?.checked !== false,
                        },
                        elder_interest_topics: { enabled: selectedContent.has("elder_interest_topics"), mode: "daily_digest" },
                        local_hotspots: { enabled: selectedContent.has("local_hotspots"), mode: "daily_digest_region" },
                        health_tips: { enabled: selectedContent.has("health_tips"), mode: "daily_digest" },
                        anti_fraud: { enabled: selectedContent.has("anti_fraud"), mode: "low_frequency" },
                        culture_entertainment: { enabled: selectedContent.has("culture_entertainment"), mode: "daily_digest" },
                        weather: { enabled: selectedContent.has("weather"), mode: "daily_digest_provider" },
                        holidays: {
                            enabled: selectedContent.has("holidays"),
                            mode: "holiday_window",
                            days_before: Number($("holidayLeadDays")?.value || 1),
                        },
                        anniversaries: {
                            enabled: selectedContent.has("anniversaries"),
                            mode: "annual_window",
                            days_before: Number($("anniversaryLeadDays")?.value || 3),
                        },
                        visit_reminder: {
                            enabled: selectedContent.has("visit_reminder"),
                            mode: "threshold",
                            threshold_days: visitThreshold,
                        },
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
        const city = $("contentCity")?.value.trim() || state.profile?.city || "杭州";
        const district = $("contentDistrict")?.value.trim() || state.profile?.district || "";
        const selectedNames = contentTypeMeta
            .filter(([key]) => checkedValues("contentType").includes(key))
            .map(([, label]) => label);
        const selectedTopics = checkedValues("interestTopic");
        const hasSearch = ["elder_interest_topics", "local_hotspots", "health_tips", "anti_fraud", "culture_entertainment"]
            .some((key) => checkedValues("contentType").includes(key));
        setText("scheduleStatus", enabled ? "已开启" : "已暂停");
        setText("scheduleSummary", time);
        setText("scheduleContentCount", selected ? `${selected} 类内容` : "未选择内容");
        setText(
            "scheduleLead",
            selectedNames.length
                ? `每天生成一张汇总卡，按${city}${district ? district : ""}和老人偏好检索，重点包含${selectedNames.slice(0, 3).join("、")}${selectedNames.length > 3 ? "等内容；异常和特殊日期按规则提醒。" : "；异常和特殊日期按规则提醒。"}`
                : "先选择要放进卡片的内容，再保存设置。"
        );
        setText(
            "previewHomeFeed",
            selectedNames.length ? `首页会展示：${selectedNames.slice(0, 4).join("、")}${selectedNames.length > 4 ? "等" : ""}` : "首页暂时没有可展示内容"
        );
        setText(
            "previewHomeFeedSub",
            selectedNames.length ? "今日关怀图承载完整图文，今日信号只展示辅助依据。" : "至少保留家里状态、天气或问候话题中的一项。"
        );
        setText(
            "previewSearchScope",
            `${city}${district ? district : ""} · ${hasSearch ? "内容搜索已开启" : "仅使用天气和日历"}`
        );
        setText(
            "previewSearchScopeSub",
            hasSearch
                ? `按${selectedTopics.slice(0, 4).join("、") || "老人兴趣"}筛选候选，不直接推送原始外链。`
                : "天气走天气源，节日纪念日走本地规则，不编造热点。"
        );
        setText(
            "previewDeliveryRules",
            $("exceptionPushEnabled")?.checked ? "异常即时提醒，日常汇总成一张卡" : "日常汇总成一张卡，异常即时提醒已关闭"
        );
        setText(
            "previewDeliveryRulesSub",
            `节日提前 ${$("holidayLeadDays")?.value || 1} 天，纪念日提前 ${$("anniversaryLeadDays")?.value || 3} 天，回家间隔 ${$("visitThreshold")?.value || 14} 天。保存后按这些规则生效。`
        );
        updatePresetSelection();
    }

    function updatePresetSelection() {
        const selected = checkedValues("contentType").sort().join("|");
        let active = "";
        Object.entries(presets).forEach(([key, preset]) => {
            if (preset.types.slice().sort().join("|") === selected) active = key;
        });
        document.querySelectorAll("[data-care-preset]").forEach((node) => {
            node.classList.toggle("selected", node.dataset.carePreset === active);
        });
    }

    function applyPreset(name) {
        const preset = presets[name];
        if (!preset) return;
        setChecked("contentType", preset.types);
        ensureInterestTopicChips(preset.topics);
        setChecked("interestTopic", preset.topics);
        if ($("messageFocus")) $("messageFocus").value = preset.focus;
        if ($("exceptionPushEnabled")) $("exceptionPushEnabled").checked = name !== "light";
        updateSummary();
        setFeedback("已套用推荐组合，保存后生效");
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
        try {
            state.profile = await GoHomeEdge.v1ElderProfile(state.family.id, "elder_primary");
        } catch (_error) {
            state.profile = null;
        }
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
        const region = event.target.closest("[data-region-city]");
        if (region) {
            $("contentCity").value = String(region.dataset.regionCity || "").trim();
            $("contentDistrict").value = String(region.dataset.regionDistrict || "").trim();
            document.querySelectorAll("[data-region-city]").forEach((node) => {
                node.classList.toggle("selected", node === region);
            });
            updateSummary();
            return;
        }
        const preset = event.target.closest("[data-care-preset]");
        if (preset) {
            applyPreset(preset.dataset.carePreset);
            return;
        }
        if (event.target.closest("#addInterestTopic")) {
            const input = $("customInterestTopic");
            const topic = normalizeTopic(input?.value || "");
            const chip = ensureInterestTopicChip(topic);
            if (chip) {
                chip.checked = true;
                if (input) input.value = "";
                updateSummary();
                setFeedback("已添加兴趣，保存后生效");
            }
            return;
        }
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

    $("customInterestTopic")?.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        $("addInterestTopic")?.click();
    });

    $("careScheduleForm")?.addEventListener("submit", save);
    $("generateCareNow")?.addEventListener("click", generateNow);

    load().catch((error) => {
        setFeedback(error.message || "读取失败");
    });
})();
