(function () {
    const $ = (id) => document.getElementById(id);
    let currentFamilyId = null;
    let currentFamilyLabel = "当前家庭";
    let currentElderProfile = null;
    let lastActionFeedback = "";
    let feedbackTimer = null;
    let careImageRenderSeq = 0;

    function toggleMessageSection(show) {
        $("companionshipMessageSection")?.classList.toggle("hidden", !show);
    }

    function setCareStatus(label, tone = "info") {
        const node = $("companionshipCareStatus");
        if (!node) return;
        node.textContent = label;
        node.className = `font-label-md text-label-md px-3 py-1 rounded-full ${
            tone === "good" ? "text-tertiary-container bg-tertiary-fixed"
                : tone === "warn" ? "text-on-error-container bg-error-container"
                    : "text-primary bg-primary-fixed"
        }`;
    }

    function setFeedback(message = "") {
        const node = $("companionshipMessageFeedback");
        if (!node) return;
        if (feedbackTimer) {
            window.clearTimeout(feedbackTimer);
            feedbackTimer = null;
        }
        const text = String(message || "").trim();
        if (!text) {
            node.textContent = "";
            node.classList.add("hidden");
            if ($("companionshipMessageMeta")) {
                $("companionshipMessageMeta").textContent = `${currentFamilyLabel} · 当前展示打开中的关怀提醒`;
            }
            return;
        }
        node.textContent = text;
        node.classList.remove("hidden");
        if ($("companionshipMessageMeta")) {
            $("companionshipMessageMeta").textContent = `${currentFamilyLabel} · ${text}`;
        }
        feedbackTimer = window.setTimeout(() => {
            lastActionFeedback = "";
            node.textContent = "";
            node.classList.add("hidden");
            if ($("companionshipMessageMeta")) {
                $("companionshipMessageMeta").textContent = `${currentFamilyLabel} · 当前展示打开中的关怀提醒`;
            }
            feedbackTimer = null;
        }, 2500);
    }

    function messageBadge(messageType) {
        const type = String(messageType || "").trim();
        if (type === "alert") return { label: "告警", tone: "warn", icon: "notifications_active" };
        if (type === "care_card") return { label: "关怀", tone: "good", icon: "volunteer_activism" };
        if (type === "test") return { label: "测试", tone: "info", icon: "science" };
        if (type === "gohome") return { label: "回家", tone: "good", icon: "home" };
        if (type === "explain") return { label: "解释", tone: "info", icon: "visibility" };
        return { label: "陪伴", tone: "info", icon: "favorite" };
    }

    function isSafetyMessage(message) {
        const type = String(message?.message_type || "").trim();
        const sourceEventIds = Array.isArray(message?.source_event_ids) ? message.source_event_ids : [];
        return type === "alert" || sourceEventIds.length > 0;
    }

    function labelText(value, fallback = "") {
        if (value === null || value === undefined) return fallback;
        if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
            const text = String(value).trim();
            return text || fallback;
        }
        if (typeof value === "object") {
            return labelText(value.label ?? value.title ?? value.name ?? value.key ?? value.type ?? value.summary, fallback);
        }
        return fallback;
    }

    function factsText(message) {
        const facts = Array.isArray(message?.facts) ? message.facts.filter(Boolean) : [];
        if (facts.length) return facts.map((item) => labelText(item)).filter(Boolean).join(" / ");
        return String(message?.subtitle || message?.body || "这条提醒目前还没有补充依据。").trim();
    }

    function actionText(message) {
        const actions = Array.isArray(message?.actions) ? message.actions : [];
        const labels = actions.map((item) => labelText(item)).filter(Boolean);
        if (labels.length) return labels.join(" / ");
        return "先看提醒，再决定是否联系。";
    }

    function sourceText(message) {
        const sources = Array.isArray(message?.source) ? message.source : [];
        const labels = sources.map((item) => labelText(item)).filter(Boolean);
        if (labels.length) return labels.join(" / ");
        return "当前没有补充来源标签。";
    }

    function safeText(value, fallback = "-") {
        const text = labelText(value, "").trim();
        return text || fallback;
    }

    function setCareImageFallback(message, subtext, icon = "volunteer_activism") {
        const image = $("companionshipCareImage");
        const fallback = $("companionshipCareImageFallback");
        if (image) {
            image.removeAttribute("src");
            image.classList.add("hidden");
            image.classList.remove("opacity-0");
        }
        if (fallback) {
            fallback.classList.remove("hidden");
            const iconNode = fallback.querySelector(".material-symbols-outlined");
            const messageNode = fallback.querySelector(".font-label-md");
            const subtextNode = fallback.querySelector(".font-body-md");
            if (iconNode) iconNode.textContent = icon;
            if (messageNode) messageNode.textContent = message;
            if (subtextNode) subtextNode.textContent = subtext;
        }
    }

    async function renderCareCardImage(card) {
        const image = $("companionshipCareImage");
        const fallback = $("companionshipCareImageFallback");
        if (!image || !fallback) return;
        const seq = careImageRenderSeq + 1;
        careImageRenderSeq = seq;
        const imageUrl = String(card?.image_url || "").trim();
        if (!imageUrl) {
            if (card?.image_mode === "failed_provider") {
                setCareImageFallback("今日关怀已生成", "图片稍后再试", "favorite");
            } else {
                setCareImageFallback("今日关怀正在生成", "温暖卡片稍后出现", "volunteer_activism");
            }
            return;
        }
        setCareImageFallback("正在打开今日关怀", "温暖卡片马上出现", "hourglass_top");
        try {
            const resolvedUrl = await window.GoHomeEdge.v1VideoMediaPlaybackUrl(imageUrl);
            if (careImageRenderSeq !== seq) return;
            image.onload = () => {
                if (careImageRenderSeq !== seq) return;
                fallback.classList.add("hidden");
                image.classList.remove("opacity-0");
                image.classList.remove("hidden");
            };
            image.onerror = () => {
                if (careImageRenderSeq !== seq) return;
                image.classList.remove("opacity-0");
                setCareImageFallback("今日关怀已生成", "图片暂时无法打开", "favorite");
            };
            image.classList.remove("hidden");
            image.classList.add("opacity-0");
            image.src = resolvedUrl;
        } catch (_error) {
            if (careImageRenderSeq !== seq) return;
            setCareImageFallback("今日关怀已生成", "图片暂时无法打开", "favorite");
        }
    }

    function setActionLink(anchor, config) {
        if (!anchor || !config) return;
        anchor.href = window.GoHomeEdge?.pageHref?.(config.href) || config.href;
        const iconNode = anchor.querySelector(".material-symbols-outlined");
        if (iconNode) {
            iconNode.textContent = config.icon || "arrow_forward";
            iconNode.classList.toggle("fill", config.icon === "home");
        }
        const textNode = Array.from(anchor.childNodes).find((child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
        if (textNode) {
            textNode.textContent = ` ${config.label}`;
        } else {
            anchor.append(document.createTextNode(` ${config.label}`));
        }
    }

    async function resolvePrimaryFamily() {
        if (!window.GoHomeEdge) return null;
        await window.GoHomeEdge.connect();
        if (!window.GoHomeEdge.isAuthenticated()) return null;
        try {
            await window.GoHomeEdge.currentUser();
        } catch (_error) {
            window.GoHomeEdge.clearAuthToken();
            return null;
        }
        const families = await window.GoHomeEdge.myFamilies();
        return families[0] || null;
    }

    async function loadMessages(familyId) {
        if (!window.GoHomeEdge?.v1AppMessages) return [];
        let messages = await window.GoHomeEdge.v1AppMessages({ family_id: familyId, limit: 6, status: "open" });
        messages = messages.filter((message) => !isSafetyMessage(message));
        return messages.slice(0, 3);
    }

    async function loadCareCard(familyId) {
        if (!window.GoHomeEdge?.v1CareCardToday) return null;
        return window.GoHomeEdge.v1CareCardToday(familyId);
    }

    async function loadElderProfile(familyId) {
        if (!familyId || !window.GoHomeEdge?.v1ElderProfile) return null;
        try {
            return await window.GoHomeEdge.v1ElderProfile(familyId, "elder_primary");
        } catch (_error) {
            return null;
        }
    }

    function phoneFromProfile(profile) {
        return String(profile?.mobile_phone || profile?.phone || profile?.home_phone || "").replace(/[^\d+]/g, "");
    }

    function parentProfileHref() {
        const query = new URLSearchParams();
        if (currentFamilyId) query.set("family_id", String(currentFamilyId));
        query.set("next", "companionship.html");
        return `parent_profile.html?${query.toString()}`;
    }

    function contactActions() {
        const name = currentElderProfile?.display_name || "老人";
        const phone = phoneFromProfile(currentElderProfile);
        return [
            {
                key: "wechat",
                label: "发消息",
                subtext: `给${name}发一句问候`,
                icon: "chat",
                primary: false,
            },
            {
                key: "call",
                label: phone ? "打电话" : "补电话",
                subtext: phone ? phone : "先补充电话",
                icon: "call",
                primary: true,
                href: phone ? `tel:${phone}` : parentProfileHref(),
            },
        ];
    }

    function bindContactAction(node, action) {
        if (!node) return;
        node.addEventListener("click", (event) => {
            if (action.key === "call") {
                if (!action.href || action.href === "#") {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    setFeedback("还没有填写老人电话，请先到家人资料里补充。");
                }
                return;
            }
            if (action.key === "wechat") {
                event.preventDefault();
                event.stopImmediatePropagation();
                if (window.GoHomeEdge?.nativeBridgeAvailable?.()) {
                    window.GoHomeEdge.openNativeExternalURL?.("weixin://")
                        .catch((error) => setFeedback(error.message || "暂时无法打开微信。"));
                    return;
                }
                setFeedback("请在 iOS App 中使用微信联系。 ");
            }
        }, true);
    }

    function renderCareCard(card, family) {
        if (!card) return;
        const title = $("companionshipCareTitle");
        const body = $("companionshipCareBody");
        const meta = $("companionshipCareMeta");
        const facts = $("companionshipCareFacts");
        const actions = $("companionshipCareActions");
        if (title) title.textContent = card.title || "今天家里怎么样";
        if (body) body.textContent = card.body || "今日关怀卡片已经生成。";
        if (meta) meta.textContent = `${family?.name || "当前家庭"} · ${card.card_date || ""}`;
        const careText = [card.title, card.body, ...(Array.isArray(card.facts) ? card.facts : [])].map(String).join(" ");
        const critical = !/无高优先级|无异常|没有未处理|没有待处理|当前没有|整体平稳|一切平稳/.test(careText)
            && /高优先级|重要提醒|告警|跌倒|离线|待确认/.test(careText);
        setCareStatus(critical ? "需关注" : "平稳", critical ? "warn" : "good");
        renderCareCardImage(card);
        if (facts) {
            facts.innerHTML = "";
            (Array.isArray(card.facts) ? card.facts : []).slice(0, 5).forEach((fact) => {
                const item = document.createElement("div");
                item.className = "gohome-mini-fact";
                const icon = document.createElement("span");
                icon.className = "material-symbols-outlined";
                icon.textContent = "check_circle";
                const text = document.createElement("p");
                text.textContent = String(fact || "");
                item.append(icon, text);
                facts.append(item);
            });
        }
        if (actions) {
            actions.innerHTML = "";
            contactActions().forEach((action) => {
                const anchor = document.createElement(action.href ? "a" : "button");
                const primary = action.primary;
                anchor.className = primary
                    ? "bg-primary text-on-primary px-3.5 py-3 font-label-md text-label-md flex items-start gap-3 hover:opacity-90 transition-opacity focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2"
                    : "bg-surface-container-high text-on-surface px-3.5 py-3 font-label-md text-label-md flex items-start gap-3 hover:bg-surface-variant transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2";
                anchor.dataset.action = `contact-${action.key}`;
                if (action.href) {
                    anchor.href = action.href;
                } else {
                    anchor.type = "button";
                }
                const icon = document.createElement("span");
                icon.className = primary
                    ? "material-symbols-outlined w-9 h-9 rounded-lg bg-white/20 text-on-primary flex items-center justify-center shrink-0 text-[20px] mt-0.5"
                    : "material-symbols-outlined w-9 h-9 rounded-lg bg-surface-container-low text-primary flex items-center justify-center shrink-0 text-[20px] mt-0.5";
                icon.setAttribute("aria-hidden", "true");
                icon.textContent = action.icon;
                const textWrap = document.createElement("span");
                textWrap.className = "min-w-0 flex-1";
                const label = document.createElement("span");
                label.className = "block leading-relaxed break-words text-left";
                label.textContent = action.label;
                const subtext = document.createElement("span");
                subtext.className = primary
                    ? "block font-body-md text-body-md text-white/80 text-xs mt-0.5"
                    : "block font-body-md text-body-md text-on-surface-variant text-xs mt-0.5";
                subtext.textContent = action.subtext;
                textWrap.append(label, subtext);
                anchor.append(icon, textWrap);
                bindContactAction(anchor, action);
                actions.append(anchor);
            });
        }
    }

    function bindMessageCardActions(article, message) {
        const expandButton = article.querySelector("[data-role='expand']");
        const markReadButton = article.querySelector("[data-role='mark-read']");
        const detailPanel = article.querySelector("[data-role='detail']");
        if (expandButton && detailPanel) {
            expandButton.addEventListener("click", () => {
                const nextHidden = !detailPanel.classList.contains("hidden");
                detailPanel.classList.toggle("hidden", nextHidden);
                expandButton.textContent = nextHidden ? "查看详情" : "收起详情";
            });
        }
        if (markReadButton && message?.message_id) {
            markReadButton.addEventListener("click", async () => {
                if (!window.GoHomeEdge?.v1UpdateAppMessage || !currentFamilyId) return;
                markReadButton.disabled = true;
                markReadButton.textContent = "处理中...";
                try {
                    await window.GoHomeEdge.v1UpdateAppMessage(message.message_id, { status: "read" }, currentFamilyId);
                    lastActionFeedback = "已将一条提醒标记为已读，列表已刷新。";
                    await render();
                } catch (_error) {
                    markReadButton.disabled = false;
                    markReadButton.textContent = "标记已读";
                    setFeedback("状态更新失败，请稍后重试。");
                }
            });
        }
    }

    function renderMessageList(messages, family) {
        const list = $("companionshipMessageList");
        if (!list) return;
        currentFamilyId = family?.id || null;
        currentFamilyLabel = family?.name || "当前家庭";
        list.innerHTML = "";
        $("companionshipMessageMeta").textContent = `${currentFamilyLabel} · 当前展示打开中的关怀提醒`;
        $("companionshipMessageCount").textContent = `${messages.length} 条打开中`;
        setFeedback(lastActionFeedback);
        messages.forEach((message) => {
            const badge = messageBadge(message.message_type);
            const article = document.createElement("article");
            article.className = "app-panel-muted p-4 flex flex-col gap-3";
            article.innerHTML = `
                <div class="flex items-start justify-between gap-3">
                    <div class="flex items-start gap-3 min-w-0">
                        <div class="app-icon-chip ${badge.tone} shrink-0">
                            <span class="material-symbols-outlined text-[18px]">${badge.icon}</span>
                        </div>
                        <div class="min-w-0">
                            <p class="font-display text-[17px] leading-snug font-bold text-on-surface">${message.title || "一条新的关怀提醒"}</p>
                            <p class="font-sans text-[12px] text-on-surface-variant leading-relaxed mt-1.5">${message.subtitle || message.body || "这条提醒正在等待你处理。"}</p>
                        </div>
                    </div>
                    <span class="app-status-badge ${badge.tone} shrink-0">${badge.label}</span>
                </div>
                <div class="grid grid-cols-1 gap-2">
                    <div class="rounded-[18px] bg-white/68 border border-white/55 px-3.5 py-3">
                        <p class="font-sans text-[11px] font-semibold text-primary">关怀依据</p>
                        <p class="font-sans text-[12px] text-on-surface-variant leading-relaxed mt-1.5">${factsText(message)}</p>
                    </div>
                    <div class="rounded-[18px] bg-white/68 border border-white/55 px-3.5 py-3">
                        <div class="flex items-center justify-between gap-3">
                            <p class="font-sans text-[11px] font-semibold text-[#2d7d5c]">建议动作</p>
                            <span class="font-sans text-[10px] font-medium text-on-surface-variant">${window.GoHomeEdge?.fmtDateTime?.(message.created_at) || "-"}</span>
                        </div>
                        <p class="font-sans text-[12px] text-on-surface-variant leading-relaxed mt-1.5">${actionText(message)}</p>
                    </div>
                </div>
                <div data-role="detail" class="hidden rounded-[20px] bg-white/72 border border-white/60 px-4 py-3.5">
                    <div class="rounded-[18px] bg-[#fcfaf7] border border-white/80 px-3.5 py-3 mt-3">
                        <p class="font-sans text-[11px] font-semibold text-primary">完整内容</p>
                            <p class="font-sans text-[12px] text-on-surface-variant leading-relaxed mt-1.5">${safeText(message.body, message.subtitle || "当前提醒没有额外正文。")}</p>
                        <p class="font-sans text-[11px] font-semibold text-primary mt-3">参考信息</p>
                        <p class="font-sans text-[12px] text-on-surface-variant leading-relaxed mt-1.5">${sourceText(message)}</p>
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <button data-role="expand" class="app-btn-secondary font-sans text-[13px] font-semibold transition-all active:scale-[0.98] flex items-center justify-center gap-1.5" type="button">
                        查看详情
                    </button>
                    <button data-role="mark-read" class="app-btn-secondary font-sans text-[13px] font-semibold transition-all active:scale-[0.98] flex items-center justify-center gap-1.5" type="button">
                        标记已读
                    </button>
                </div>
            `;
            bindMessageCardActions(article, message);
            list.append(article);
        });
    }

    async function render() {
        toggleMessageSection(false);
        if (!window.GoHomeEdge) return;
        try {
            const family = await resolvePrimaryFamily();
            if (!family) return;
            currentElderProfile = await loadElderProfile(family.id);
            const careCard = await loadCareCard(family.id);
            renderCareCard(careCard, family);
            const messages = await loadMessages(family.id);
            if (!messages.length) return;
            renderMessageList(messages, family);
            toggleMessageSection(true);
        } catch (_error) {
            setFeedback("");
            toggleMessageSection(false);
        }
    }

    document.addEventListener("DOMContentLoaded", render);
})();
