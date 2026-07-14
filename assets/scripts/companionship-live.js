(function () {
    const $ = (id) => document.getElementById(id);
    let currentFamilyId = null;
    let currentFamilyLabel = "当前家庭";
    let currentElderProfile = null;
    let lastActionFeedback = "";
    let feedbackTimer = null;
    let careImageRenderSeq = 0;
    let pendingCareRefreshTimer = null;

    function toggleMessageSection(show) {
        $("companionshipMessageSection")?.classList.toggle("hidden", !show);
    }

    function setCareStatus(label, tone = "info") {
        const node = $("companionshipCareStatus");
        if (!node) return;
        node.textContent = label;
        node.className = `editorial-section-link ${tone === "warn" ? "text-[#b42318]" : ""}`;
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
                $("companionshipMessageMeta").textContent = `${currentFamilyLabel} · 最近的关怀提醒`;
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
                $("companionshipMessageMeta").textContent = `${currentFamilyLabel} · 最近的关怀提醒`;
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

    function safeText(value, fallback = "-") {
        const text = labelText(value, "").trim();
        return text || fallback;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
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
            const paragraphs = fallback.querySelectorAll("p");
            const messageNode = fallback.querySelector(".font-label-md") || paragraphs[0];
            const subtextNode = fallback.querySelector(".font-body-md") || paragraphs[1];
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
        const hadVisibleImage = Boolean(image.src && !image.classList.contains("hidden"));
        if (!imageUrl) {
            setCareImageFallback(
                card?.title || "今日关怀",
                card?.body || "今天可以从家里近况开始聊起。",
                "favorite"
            );
            return;
        }
        if (!hadVisibleImage) {
            setCareImageFallback(
                card?.title || "今日关怀",
                card?.body || "今天可以从家里近况开始聊起。",
                "favorite"
            );
        }
        try {
            const resolvedUrl = await window.GoHomeEdge.v1VideoMediaPlaybackUrl(imageUrl);
            if (careImageRenderSeq !== seq) return;
            const preload = new Image();
            preload.onload = () => {
                if (careImageRenderSeq !== seq) return;
                image.src = resolvedUrl;
                fallback.classList.add("hidden");
                image.classList.remove("opacity-0");
                image.classList.remove("hidden");
            };
            preload.onerror = () => {
                if (careImageRenderSeq !== seq) return;
                image.classList.remove("opacity-0");
                if (!hadVisibleImage) {
                    setCareImageFallback(card?.title || "今日关怀", card?.body || "今天可以从家里近况开始聊起。", "favorite");
                }
            };
            preload.src = resolvedUrl;
        } catch (_error) {
            if (careImageRenderSeq !== seq) return;
            if (!hadVisibleImage) {
                setCareImageFallback(card?.title || "今日关怀", card?.body || "今天可以从家里近况开始聊起。", "favorite");
            }
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
            const [, families] = await Promise.all([
                window.GoHomeEdge.currentUser(),
                window.GoHomeEdge.myFamilies(),
            ]);
            return families[0] || null;
        } catch (_error) {
            window.GoHomeEdge.clearAuthToken();
            return null;
        }
    }

    async function loadMessages(familyId) {
        if (!window.GoHomeEdge?.v1AppMessages) return [];
        let messages = await window.GoHomeEdge.v1AppMessages({ family_id: familyId, limit: 8, status: "all" });
        messages = messages.filter((message) => (
            !isSafetyMessage(message)
            && String(message?.message_type || "").trim() !== "test"
        ));
        return messages.slice(0, 4);
    }

    async function loadCareCard(familyId, options = {}) {
        if (!window.GoHomeEdge?.v1CareCardToday) return null;
        return window.GoHomeEdge.v1CareCardToday(familyId, options);
    }

    function refreshPendingCareCard(family, attempt = 0) {
        if (pendingCareRefreshTimer) window.clearTimeout(pendingCareRefreshTimer);
        if (attempt >= 6) return;
        pendingCareRefreshTimer = window.setTimeout(async () => {
            pendingCareRefreshTimer = null;
            const nextCard = await loadCareCard(family.id, { forceRefresh: true }).catch(() => null);
            if (!nextCard) return;
            renderCareCard(nextCard, family);
            window.GoHomeAppStore?.scheduleCapture?.();
            if (nextCard.pending_refresh) refreshPendingCareCard(family, attempt + 1);
        }, 5000);
    }

    async function loadElderProfile(familyId) {
        if (!familyId || !window.GoHomeEdge?.v1ElderProfile) return null;
        try {
            return await window.GoHomeEdge.v1ElderProfile(familyId, "elder_primary");
        } catch (_error) {
            return null;
        }
    }

    async function loadCarePreferences(familyId) {
        if (!familyId || !window.GoHomeEdge?.v1CarePreferences) return null;
        try {
            return await window.GoHomeEdge.v1CarePreferences(familyId);
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
        const name = currentElderProfile?.display_name || "家里";
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
                    setFeedback("还没有填写联系电话，请先到家庭联系人资料里补充。");
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

    function renderProfileSummary(profile) {
        const name = String(profile?.display_name || "家庭联系人").trim();
        const city = String(profile?.city || "").trim();
        const district = String(profile?.district || "").trim();
        if ($("companionshipProfileName")) $("companionshipProfileName").textContent = name;
        if ($("companionshipProfileMeta")) {
            $("companionshipProfileMeta").textContent = city
                ? `${city}${district ? ` · ${district}` : ""} · 资料已同步`
                : "完善所在城市后同步天气与本地内容";
        }
        $("companionshipProfileStatus")?.classList.toggle("hidden", !profile);
        renderTopContactActions();
    }

    function renderTopContactActions() {
        const container = $("companionshipContactActions");
        if (!container) return;
        container.innerHTML = "";
        contactActions().forEach((action) => {
            const node = document.createElement(action.href ? "a" : "button");
            node.className = action.primary ? "primary" : "secondary";
            node.dataset.action = `contact-${action.key}`;
            if (action.href) node.href = action.href;
            else node.type = "button";
            const icon = document.createElement("span");
            icon.className = "material-symbols-outlined";
            icon.textContent = action.icon;
            const label = document.createElement("span");
            label.textContent = action.label;
            node.append(icon, label);
            bindContactAction(node, action);
            container.append(node);
        });
    }

    function shanghaiDateKey(date = new Date()) {
        return new Intl.DateTimeFormat("en-CA", {
            timeZone: "Asia/Shanghai",
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
        }).format(date);
    }

    function annualOccurrence(value) {
        const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!match) return null;
        const today = new Date(`${shanghaiDateKey()}T00:00:00+08:00`);
        const year = today.getFullYear();
        let target = new Date(`${year}-${match[2]}-${match[3]}T00:00:00+08:00`);
        if (target < today) target = new Date(`${year + 1}-${match[2]}-${match[3]}T00:00:00+08:00`);
        return {
            date: target,
            days: Math.ceil((target.getTime() - today.getTime()) / 86400000),
        };
    }

    function renderImportantDates(preferences) {
        const list = $("companionshipImportantList");
        if (!list) return;
        const schedule = preferences?.metadata?.care_card_schedule || {};
        const anniversaries = (Array.isArray(schedule.anniversaries) ? schedule.anniversaries : [])
            .map((item) => ({ ...item, occurrence: annualOccurrence(item.date) }))
            .filter((item) => item.occurrence)
            .sort((a, b) => a.occurrence.days - b.occurrence.days)
            .slice(0, 2);
        const year = new Date(`${shanghaiDateKey()}T00:00:00+08:00`).getFullYear();
        const holidays = [
            { label: "中秋节", date: year === 2026 ? "2026-09-25" : `${year}-09-15` },
            { label: "国庆节", date: `${year}-10-01` },
            { label: "元旦", date: `${year + 1}-01-01` },
        ].map((item) => ({ ...item, occurrence: annualOccurrence(item.date) }))
            .filter((item) => item.occurrence)
            .sort((a, b) => a.occurrence.days - b.occurrence.days);
        const rows = [...anniversaries, ...holidays.slice(0, 1)]
            .sort((a, b) => a.occurrence.days - b.occurrence.days)
            .slice(0, 3);
        if (!rows.length) return;
        list.innerHTML = rows.map((item, index) => {
            const date = item.occurrence.date;
            const dateLabel = `${date.getMonth() + 1}月${date.getDate()}日`;
            const countdown = item.occurrence.days === 0 ? "今天" : `还有 ${item.occurrence.days} 天`;
            return `
                <div class="companion-important-row">
                    <span class="material-symbols-outlined">${index === 0 && anniversaries.includes(item) ? "cake" : "event"}</span>
                    <div><h4>${escapeHtml(safeText(item.label, "重要日期"))}</h4><p>${dateLabel}</p></div>
                    <strong>${countdown}</strong>
                </div>
            `;
        }).join("");
    }

    function renderCareCard(card, family) {
        if (!card) return;
        $("companionshipCareSection")?.classList.remove("hidden");
        $("companionshipCareCard")?.classList.toggle("has-generated-image", Boolean(String(card.image_url || "").trim()));
        const title = $("companionshipCareTitle");
        const body = $("companionshipCareBody");
        const meta = $("companionshipCareMeta");
        const facts = $("companionshipCareFacts");
        const actions = $("companionshipCareActions");
        if (title) title.textContent = card.title || "今天家里怎么样";
        if (body) body.textContent = card.body || "今日关怀卡片已经生成。";
        if (meta) meta.textContent = `${family?.name || "当前家庭"} · ${card.card_date || ""}`;
        const careText = [card.title, card.body, ...(Array.isArray(card.facts) ? card.facts : [])].map(String).join(" ");
        const critical = !/无高优先级|无安全告警|无告警|无异常|没有未处理|没有待处理|当前没有|整体平稳|一切平稳/.test(careText)
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
        $("companionshipMessageMeta").textContent = `${currentFamilyLabel} · 最近的关怀内容`;
        $("companionshipMessageCount").textContent = `${messages.length} 条记录`;
        setFeedback(lastActionFeedback);
        messages.forEach((message) => {
            const badge = messageBadge(message.message_type);
            const article = document.createElement("article");
            article.className = "companion-record";
            article.innerHTML = `
                <div class="companion-record-marker">
                    <span class="material-symbols-outlined">${escapeHtml(badge.icon)}</span>
                </div>
                <div class="companion-record-body">
                    <div class="companion-record-meta">
                        <span>${escapeHtml(badge.label)}</span>
                        <time>${escapeHtml(window.GoHomeEdge?.fmtDateTime?.(message.created_at) || "-")}</time>
                    </div>
                    <h4>${escapeHtml(message.title || "一条新的关怀记录")}</h4>
                    <p>${escapeHtml(message.subtitle || message.body || "内容已经记录。")}</p>
                    <div data-role="detail" class="hidden companion-record-detail">
                        <strong>关怀依据</strong>
                        <p>${escapeHtml(factsText(message))}</p>
                        <strong>完整内容</strong>
                        <p>${escapeHtml(safeText(message.body, message.subtitle || "当前记录没有额外正文。"))}</p>
                    </div>
                    <div class="companion-record-actions">
                        <button data-role="expand" type="button">查看详情</button>
                        <button data-role="mark-read" type="button">标记已读</button>
                    </div>
                </div>
            `;
            bindMessageCardActions(article, message);
            list.append(article);
        });
    }

    async function render() {
        const hasVisibleState = window.GoHomeAppStore?.hasVisibleState?.() === true;
        if (!hasVisibleState) toggleMessageSection(false);
        if (!window.GoHomeEdge) {
            window.GoHomeAppStore?.markPageReady?.();
            return;
        }
        try {
            const family = await resolvePrimaryFamily();
            if (!family) return;
            currentFamilyId = family.id;
            currentFamilyLabel = family.name || "当前家庭";
            const profilePromise = loadElderProfile(family.id);
            const careCardPromise = loadCareCard(family.id);
            const preferencesPromise = loadCarePreferences(family.id);
            const messagesPromise = loadMessages(family.id);
            const [profile, careCard, preferences] = await Promise.all([profilePromise, careCardPromise, preferencesPromise]);
            currentElderProfile = profile;
            renderProfileSummary(profile);
            renderImportantDates(preferences);
            renderCareCard(careCard, family);
            if (careCard?.pending_refresh) refreshPendingCareCard(family);
            window.GoHomeAppStore?.markPageReady?.();
            const messages = await messagesPromise;
            if (!messages.length) {
                if ($("companionshipMessageList")) $("companionshipMessageList").innerHTML = "";
                toggleMessageSection(false);
                return;
            }
            renderMessageList(messages, family);
            toggleMessageSection(true);
        } catch (_error) {
            if (!window.GoHomeAppStore?.hasVisibleState?.()) {
                setFeedback("");
                toggleMessageSection(false);
            }
        } finally {
            window.GoHomeAppStore?.markPageReady?.();
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        window.GoHomeRefreshPage = () => render();
        render();
    });
})();
