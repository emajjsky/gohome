(function () {
    const $ = (id) => document.getElementById(id);
    let currentFamilyId = null;
    let currentFamilyLabel = "当前家庭";
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
                $("companionshipMessageMeta").textContent = `${currentFamilyLabel} · 当前展示打开中的消息`;
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
                $("companionshipMessageMeta").textContent = `${currentFamilyLabel} · 当前展示打开中的消息`;
            }
            feedbackTimer = null;
        }, 2500);
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
            primary: { href: "watch.html", label: "看看家里", icon: "nest_cam_indoor" },
            secondary: { href: "index.html", label: "回首页", icon: "home" },
        };
    }

    function factsText(message) {
        const facts = Array.isArray(message?.facts) ? message.facts.filter(Boolean) : [];
        if (facts.length) return facts.join(" / ");
        return String(message?.subtitle || message?.body || "这条消息目前还没有补充依据。").trim();
    }

    function actionText(message) {
        const actions = Array.isArray(message?.actions) ? message.actions : [];
        const labels = actions.map((item) => item?.label || item?.key || "").filter(Boolean);
        if (labels.length) return labels.join(" / ");
        return "先看消息，再决定是否联系。";
    }

    function sourceText(message) {
        const sources = Array.isArray(message?.source) ? message.source : [];
        const labels = sources.map((item) => item?.label || item?.type || item?.id || "").filter(Boolean);
        if (labels.length) return labels.join(" / ");
        return "当前没有补充来源标签。";
    }

    function safeText(value, fallback = "-") {
        const text = String(value || "").trim();
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
        if (!window.GoHomeEdge?.v1AppMessages || !window.GoHomeEdge?.v1GenerateMessages) return [];
        let messages = await window.GoHomeEdge.v1AppMessages({ family_id: familyId, limit: 3, status: "open" });
        if (messages.length) return messages;
        const generated = await window.GoHomeEdge.v1GenerateMessages({
            family_id: familyId,
            clear_existing: false,
        });
        messages = Array.isArray(generated?.messages) ? generated.messages : [];
        return messages.slice(0, 3);
    }

    async function loadCareCard(familyId) {
        if (!window.GoHomeEdge?.v1CareCardToday) return null;
        return window.GoHomeEdge.v1CareCardToday(familyId);
    }

    function careActionConfig(action) {
        const key = String(action?.key || "").trim();
        if (key === "call") return { href: "#", label: action.label || "打电话问候", icon: "call" };
        if (key === "open_watch") return { href: "watch.html", label: action.label || "看看家里", icon: "nest_cam_indoor" };
        if (key === "open_events") return { href: "events.html", label: action.label || "查看提醒", icon: "history" };
        return { href: "index.html", label: action?.label || "回首页", icon: "home" };
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
        if (meta) meta.textContent = `${family?.name || "当前家庭"} · ${card.card_date || ""} · ${card.generated_by || "care-template-v1"}`;
        const critical = (card.facts || []).some((item) => /高优先级|重要提醒|告警/.test(String(item)));
        setCareStatus(critical ? "需关注" : "平稳", critical ? "warn" : "good");
        renderCareCardImage(card);
        if (facts) {
            facts.innerHTML = "";
            (Array.isArray(card.facts) ? card.facts : []).slice(0, 5).forEach((fact) => {
                const item = document.createElement("div");
                item.className = "rounded-lg bg-white/70 border border-white/60 px-3.5 py-3 flex items-start gap-2";
                const icon = document.createElement("span");
                icon.className = "material-symbols-outlined text-primary text-[18px] mt-0.5";
                icon.textContent = "check_circle";
                const text = document.createElement("p");
                text.className = "font-body-md text-body-md text-on-surface-variant text-sm leading-relaxed";
                text.textContent = String(fact || "");
                item.append(icon, text);
                facts.append(item);
            });
        }
        if (actions) {
            actions.innerHTML = "";
            (Array.isArray(card.actions) ? card.actions : []).slice(0, 3).forEach((action, index) => {
                const config = careActionConfig(action);
                const anchor = document.createElement("a");
                const primary = index === 0 || config.icon === "call";
                anchor.className = primary
                    ? "min-h-[64px] rounded-xl bg-primary text-on-primary px-3.5 py-3 font-label-md text-label-md flex items-start gap-3 hover:opacity-90 transition-opacity focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2"
                    : "min-h-[64px] rounded-xl bg-surface-container-high text-on-surface px-3.5 py-3 font-label-md text-label-md flex items-start gap-3 hover:bg-surface-variant transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2";
                anchor.href = config.href === "#" ? "#" : (window.GoHomeEdge?.pageHref?.(config.href) || config.href);
                const icon = document.createElement("span");
                icon.className = primary
                    ? "material-symbols-outlined w-9 h-9 rounded-lg bg-white/20 text-on-primary flex items-center justify-center shrink-0 text-[20px] mt-0.5"
                    : "material-symbols-outlined w-9 h-9 rounded-lg bg-surface-container-low text-primary flex items-center justify-center shrink-0 text-[20px] mt-0.5";
                icon.setAttribute("aria-hidden", "true");
                icon.textContent = config.icon;
                const textWrap = document.createElement("span");
                textWrap.className = "min-w-0 flex-1 flex items-start justify-between gap-3";
                const label = document.createElement("span");
                label.className = "leading-relaxed break-words text-left";
                label.textContent = config.label;
                const arrow = document.createElement("span");
                arrow.className = primary
                    ? "material-symbols-outlined text-[18px] shrink-0 mt-0.5 text-on-primary/80"
                    : "material-symbols-outlined text-[18px] shrink-0 mt-0.5 text-outline";
                arrow.setAttribute("aria-hidden", "true");
                arrow.textContent = "arrow_forward";
                textWrap.append(label, arrow);
                anchor.append(icon, textWrap);
                if (config.href === "#") {
                    anchor.addEventListener("click", (event) => {
                        event.preventDefault();
                        setFeedback("可以现在给家里打个电话，联系后再回来记录。");
                    });
                }
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
                    lastActionFeedback = "已将一条消息标记为已读，列表已刷新。";
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
        $("companionshipMessageMeta").textContent = `${currentFamilyLabel} · 当前展示打开中的消息`;
        $("companionshipMessageCount").textContent = `${messages.length} 条打开中`;
        setFeedback(lastActionFeedback);
        messages.forEach((message) => {
            const badge = messageBadge(message.message_type);
            const actions = messageActionConfig(message);
            const article = document.createElement("article");
            article.className = "app-panel-muted p-4 flex flex-col gap-3";
            article.innerHTML = `
                <div class="flex items-start justify-between gap-3">
                    <div class="flex items-start gap-3 min-w-0">
                        <div class="app-icon-chip ${badge.tone} shrink-0">
                            <span class="material-symbols-outlined text-[18px]">${badge.icon}</span>
                        </div>
                        <div class="min-w-0">
                            <p class="font-display text-[17px] leading-snug font-bold text-on-surface">${message.title || "一条新的陪伴消息"}</p>
                            <p class="font-sans text-[12px] text-on-surface-variant leading-relaxed mt-1.5">${message.subtitle || message.body || "这条消息正在等待你处理。"}</p>
                        </div>
                    </div>
                    <span class="app-status-badge ${badge.tone} shrink-0">${badge.label}</span>
                </div>
                <div class="grid grid-cols-1 gap-2">
                    <div class="rounded-[18px] bg-white/68 border border-white/55 px-3.5 py-3">
                        <p class="font-sans text-[10px] font-semibold text-primary tracking-[0.12em]">依据</p>
                        <p class="font-sans text-[12px] text-on-surface-variant leading-relaxed mt-1.5">${factsText(message)}</p>
                    </div>
                    <div class="rounded-[18px] bg-white/68 border border-white/55 px-3.5 py-3">
                        <div class="flex items-center justify-between gap-3">
                            <p class="font-sans text-[10px] font-semibold text-[#2d7d5c] tracking-[0.12em]">建议动作</p>
                            <span class="font-sans text-[10px] font-medium text-on-surface-variant">${window.GoHomeEdge?.fmtDateTime?.(message.created_at) || "-"}</span>
                        </div>
                        <p class="font-sans text-[12px] text-on-surface-variant leading-relaxed mt-1.5">${actionText(message)}</p>
                    </div>
                </div>
                <div data-role="detail" class="hidden rounded-[20px] bg-white/72 border border-white/60 px-4 py-3.5">
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <p class="font-sans text-[10px] font-semibold text-on-surface-variant tracking-[0.12em]">消息 ID</p>
                            <p class="font-sans text-[12px] text-on-surface leading-relaxed mt-1.5 break-all">${safeText(message.message_id)}</p>
                        </div>
                        <div>
                            <p class="font-sans text-[10px] font-semibold text-on-surface-variant tracking-[0.12em]">当前状态</p>
                            <p class="font-sans text-[12px] text-on-surface leading-relaxed mt-1.5">${safeText(message.status)}</p>
                        </div>
                        <div>
                            <p class="font-sans text-[10px] font-semibold text-on-surface-variant tracking-[0.12em]">生成来源</p>
                            <p class="font-sans text-[12px] text-on-surface leading-relaxed mt-1.5">${safeText(message.generated_by, "message-service")}</p>
                        </div>
                        <div>
                            <p class="font-sans text-[10px] font-semibold text-on-surface-variant tracking-[0.12em]">来源引用</p>
                            <p class="font-sans text-[12px] text-on-surface leading-relaxed mt-1.5">${sourceText(message)}</p>
                        </div>
                    </div>
                    <div class="rounded-[18px] bg-[#fcfaf7] border border-white/80 px-3.5 py-3 mt-3">
                        <p class="font-sans text-[10px] font-semibold text-primary tracking-[0.12em]">正文</p>
                        <p class="font-sans text-[12px] text-on-surface-variant leading-relaxed mt-1.5">${safeText(message.body, message.subtitle || "当前消息没有额外正文。")}</p>
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-3 pt-1">
                    <a class="app-btn-primary font-sans text-[13px] font-semibold transition-all active:scale-[0.98] flex items-center justify-center gap-1.5" href="events.html?app=1">
                        <span class="material-symbols-outlined text-[18px]">history</span>
                        查看事件
                    </a>
                    <a class="app-btn-secondary font-sans text-[13px] font-semibold transition-all active:scale-[0.98] flex items-center justify-center gap-1.5" href="watch.html?app=1">
                        <span class="material-symbols-outlined text-[18px]">nest_cam_indoor</span>
                        实时看看
                    </a>
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
            const [primaryAction, secondaryAction] = article.querySelectorAll("a");
            setActionLink(primaryAction, actions.primary);
            setActionLink(secondaryAction, actions.secondary);
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
