(function () {
    const $ = (id) => document.getElementById(id);
    const CONTENT_SECTION_IDS = [
        "edgeHomeCalendarSection",
        "edgeHomeCareSection",
        "edgeHomeCareHistorySection",
        "edgeHomeLocationSection",
        "edgeHomeMetricsSection",
    ];
    let homeCareImageRenderSeq = 0;
    let renderInFlight = false;
    let lastHomeCareImageUrl = "";
    let lastRenderAt = 0;
    let pendingCareRefreshTimer = null;
    let activeFeedFilter = "all";

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function setHtml(id, value) {
        const node = $(id);
        if (node) node.innerHTML = value;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
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

    function toggleMessageSection(show) {
        $("edgeHomeMessageSection")?.classList.toggle("hidden", !show);
    }

    function toggleCareSection(show) {
        $("edgeHomeCareSection")?.classList.toggle("hidden", !show);
    }

    function setAction(id, href, label, icon) {
        const node = $(id);
        if (!node) return;
        node.href = window.GoHomeEdge?.pageHref?.(href) || href;
        const iconNode = node.querySelector(".material-symbols-outlined");
        if (iconNode && icon) {
            iconNode.textContent = icon;
            iconNode.classList.toggle("fill", icon === "login" || icon === "home" || icon === "call");
        }
        const labelNode = node.querySelector("[data-action-label]")
            || Array.from(node.children).find((child) => child.tagName === "SPAN" && !child.classList.contains("material-symbols-outlined"));
        const textNode = Array.from(node.childNodes).find((child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
        if (labelNode) {
            labelNode.textContent = label;
        } else if (textNode) {
            textNode.textContent = ` ${label}`;
        } else {
            node.append(document.createTextNode(` ${label}`));
        }
    }

    function familyPath(path, family = null) {
        const url = new URL(path, window.location.href);
        if (family?.id) url.searchParams.set("family_id", String(family.id));
        return `${url.pathname.split("/").pop() || path}${url.search}${url.hash}`;
    }

    function setHomeCareImageFallback(message, subtext, icon = "volunteer_activism") {
        const image = $("edgeHomeCareImage");
        const fallback = $("edgeHomeCareImageFallback");
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

    async function renderHomeCareImage(card) {
        const image = $("edgeHomeCareImage");
        const fallback = $("edgeHomeCareImageFallback");
        if (!image || !fallback) return;
        const seq = homeCareImageRenderSeq + 1;
        homeCareImageRenderSeq = seq;
        const imageUrl = String(card?.image_url || "").trim();
        if (!imageUrl) {
            lastHomeCareImageUrl = "";
            setHomeCareImageFallback(
                careCardDisplayTitle(card),
                shortText(cardBodyText(card, "今天可以从家里近况开始聊起。"), 46),
                "favorite"
            );
            return;
        }
        if (lastHomeCareImageUrl === imageUrl && image.src && !image.classList.contains("hidden")) {
            fallback.classList.add("hidden");
            image.classList.remove("opacity-0");
            return;
        }
        const hadVisibleImage = Boolean(image.src && !image.classList.contains("hidden"));
        if (!hadVisibleImage) {
            setHomeCareImageFallback(
                careCardDisplayTitle(card),
                shortText(cardBodyText(card, "今天可以从家里近况开始聊起。"), 46),
                "favorite"
            );
        }
        try {
            const resolvedUrl = await window.GoHomeEdge.v1VideoMediaPlaybackUrl(imageUrl);
            if (homeCareImageRenderSeq !== seq) return;
            const preload = new Image();
            preload.onload = () => {
                if (homeCareImageRenderSeq !== seq) return;
                image.src = resolvedUrl;
                fallback.classList.add("hidden");
                image.classList.remove("opacity-0");
                image.classList.remove("hidden");
                lastHomeCareImageUrl = imageUrl;
            };
            preload.onerror = () => {
                if (homeCareImageRenderSeq !== seq) return;
                image.classList.remove("opacity-0");
                if (!hadVisibleImage) {
                    setHomeCareImageFallback("今日关怀已生成", "图片暂时无法打开", "favorite");
                }
            };
            preload.src = resolvedUrl;
        } catch (_error) {
            if (homeCareImageRenderSeq !== seq) return;
            if (!hadVisibleImage) {
                setHomeCareImageFallback("今日关怀已生成", "图片暂时无法打开", "favorite");
            }
        }
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
            primary: { href: "companionship.html", label: "去陪伴页", icon: "favorite" },
            secondary: { href: "watch.html", label: "看看家里", icon: "nest_cam_indoor" },
        };
    }

    function renderMessageCard(message) {
        if (!message) {
            toggleMessageSection(false);
            return;
        }
        const badge = messageBadge(message.message_type);
        const badgeNode = $("edgeHomeMessageBadge");
        const iconNode = $("edgeHomeMessageIcon");
        const facts = Array.isArray(message.facts) ? message.facts : [];
        const actions = Array.isArray(message.actions) ? message.actions : [];
        const actionConfig = messageActionConfig(message);

        toggleMessageSection(true);
        setText("edgeHomeMessageMeta", `关怀服务 · ${window.GoHomeEdge?.fmtDateTime?.(message.created_at) || ""}`);
        setText("edgeHomeMessageTitle", message.title || "今天有一条新的牵挂提醒");
        setText("edgeHomeMessageSubtitle", message.subtitle || message.body || "");
        setText("edgeHomeMessageFacts", facts.length ? facts.map((item) => labelText(item)).filter(Boolean).join(" / ") : "这条消息目前还没有补充依据。");
        setText("edgeHomeMessageActions", actions.length ? actions.map((item) => labelText(item)).filter(Boolean).join(" / ") : "先打开消息，再决定是否联系。");
        if (badgeNode) {
            badgeNode.textContent = badge.label;
            badgeNode.className = `app-status-badge ${badge.tone} shrink-0`;
        }
        if (iconNode) {
            iconNode.className = `app-icon-chip ${badge.tone} shrink-0`;
            const iconGlyph = iconNode.querySelector(".material-symbols-outlined");
            if (iconGlyph) iconGlyph.textContent = badge.icon;
        }
        setAction("edgeHomeMessagePrimaryAction", actionConfig.primary.href, actionConfig.primary.label, actionConfig.primary.icon);
        setAction("edgeHomeMessageSecondaryAction", actionConfig.secondary.href, actionConfig.secondary.label, actionConfig.secondary.icon);
    }

    async function loadPrimaryMessage(familyId) {
        if (!window.GoHomeEdge?.v1AppMessages) return null;
        let messages = [];
        try {
            messages = await window.GoHomeEdge.v1AppMessages({ family_id: familyId, limit: 6, status: "open" });
        } catch (_error) {
            return null;
        }
        if (messages.length) return messages[0];
        return null;
    }

    async function loadCareCard(familyId, options = {}) {
        if (!window.GoHomeEdge?.v1CareCardToday) return null;
        try {
            return await window.GoHomeEdge.v1CareCardToday(familyId, options);
        } catch (_error) {
            return null;
        }
    }

    function refreshPendingCareCard(familyId, family, attempt = 0) {
        if (pendingCareRefreshTimer) window.clearTimeout(pendingCareRefreshTimer);
        if (attempt >= 6) return;
        pendingCareRefreshTimer = window.setTimeout(async () => {
            pendingCareRefreshTimer = null;
            const nextCard = await loadCareCard(familyId, { forceRefresh: true });
            if (!nextCard) return;
            renderCareCardSummary(nextCard, family);
            window.GoHomeAppStore?.scheduleCapture?.();
            if (nextCard.pending_refresh) refreshPendingCareCard(familyId, family, attempt + 1);
        }, 5000);
    }

    async function loadCareCards(familyId) {
        if (!window.GoHomeEdge?.v1CareCards) return [];
        try {
            const cards = await window.GoHomeEdge.v1CareCards({ family_id: familyId, limit: 20 });
            return Array.isArray(cards) ? cards : [];
        } catch (_error) {
            return [];
        }
    }

    function shanghaiDateKey(date = new Date()) {
        try {
            const parts = new Intl.DateTimeFormat("en-CA", {
                timeZone: "Asia/Shanghai",
                year: "numeric",
                month: "2-digit",
                day: "2-digit",
            }).formatToParts(date).reduce((acc, part) => {
                acc[part.type] = part.value;
                return acc;
            }, {});
            return `${parts.year}-${parts.month}-${parts.day}`;
        } catch (_error) {
            return date.toISOString().slice(0, 10);
        }
    }

    function cardDateLabel(card) {
        const value = card?.card_date || card?.created_at || "";
        if (!value) return "关怀卡片";
        const date = new Date(String(value).includes("T") ? value : `${value}T00:00:00+08:00`);
        if (Number.isNaN(date.getTime())) return value;
        return date.toLocaleDateString("zh-CN", {
            month: "long",
            day: "numeric",
        });
    }

    async function hydrateCareFeedImages(root) {
        if (!root || !window.GoHomeEdge?.v1VideoMediaPlaybackUrl) return;
        const images = Array.from(root.querySelectorAll("[data-care-card-image]"));
        await Promise.all(images.map(async (image) => {
            const source = image.dataset.careCardImage || "";
            if (!source) return;
            try {
                image.src = await window.GoHomeEdge.v1VideoMediaPlaybackUrl(source);
                image.classList.remove("hidden");
                image.closest("[data-care-card-thumb]")?.querySelector("[data-care-card-fallback]")?.classList.add("hidden");
            } catch (_error) {
                image.classList.add("hidden");
            }
        }));
    }

    function shanghaiNow() {
        return new Date(`${shanghaiDateKey()}T12:00:00+08:00`);
    }

    function daysUntilDate(value) {
        const raw = String(value || "").trim();
        if (!raw) return null;
        const target = new Date(raw.includes("T") ? raw : `${raw}T00:00:00+08:00`);
        if (Number.isNaN(target.getTime())) return null;
        const now = new Date(`${shanghaiDateKey()}T00:00:00+08:00`);
        return Math.ceil((target.getTime() - now.getTime()) / 86400000);
    }

    function nextAnnualDate(value) {
        const raw = String(value || "").trim();
        const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!match) return null;
        const today = new Date(`${shanghaiDateKey()}T00:00:00+08:00`);
        const year = Number(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric" }).format(today));
        const monthDay = `${match[2]}-${match[3]}`;
        const current = `${year}-${monthDay}`;
        const currentDays = daysUntilDate(current);
        return currentDays !== null && currentDays >= 0
            ? { date: current, days: currentDays }
            : { date: `${year + 1}-${monthDay}`, days: daysUntilDate(`${year + 1}-${monthDay}`) };
    }

    function nextWeekendLabel() {
        const now = shanghaiNow();
        const day = now.getDay();
        const days = day === 0 ? 0 : (6 - day + 7) % 7;
        if (days === 0) return "今天就是周末";
        if (days === 1) return "明天就是周末";
        return `距离周末还有 ${days} 天`;
    }

    function upcomingHolidayCard() {
        const year = Number(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric" }).format(new Date()));
        const holidays = [
            { title: "元旦", date: `${year + 1}-01-01` },
            { title: "春节", date: year === 2026 ? "2026-02-17" : "2027-02-06" },
            { title: "清明节", date: year === 2026 ? "2026-04-05" : "2027-04-05" },
            { title: "劳动节", date: `${year}-05-01` },
            { title: "端午节", date: year === 2026 ? "2026-06-19" : "2027-06-09" },
            { title: "中秋节", date: year === 2026 ? "2026-09-25" : "2027-09-15" },
            { title: "国庆节", date: `${year}-10-01` },
        ].map((item) => ({ ...item, days: daysUntilDate(item.date) }))
            .filter((item) => item.days !== null && item.days >= 0)
            .sort((a, b) => a.days - b.days)[0];
        if (!holidays) return null;
        const sub = holidays.days === 0 ? "今天适合发一张节日问候" : `还有 ${holidays.days} 天，提前准备问候`;
        return { title: holidays.title, sub };
    }

    function upcomingAnniversary(schedule) {
        const anniversaries = Array.isArray(schedule?.anniversaries) ? schedule.anniversaries : [];
        const upcoming = anniversaries.map((item) => {
            const next = nextAnnualDate(item.date);
            return next ? { label: item.label || "纪念日", ...next } : null;
        }).filter(Boolean).sort((a, b) => a.days - b.days)[0];
        if (!upcoming) return null;
        return upcoming.days === 0
            ? `今天是${upcoming.label}`
            : `${upcoming.label}还有 ${upcoming.days} 天`;
    }

    function renderDateRail(weatherSignal = null, profile = null) {
        const now = new Date();
        const dateLabel = new Intl.DateTimeFormat("zh-CN", {
            timeZone: "Asia/Shanghai",
            month: "long",
            day: "numeric",
            weekday: "short",
        }).format(now).replace("周", " 周");
        setText("edgeHomeDate", dateLabel);
        setText("edgeHomeLunarDate", "未来七天 · 日程与内容已整理");

        const available = Boolean(weatherSignal?.available);
        const condition = String(weatherSignal?.condition || "").trim();
        const temperature = Number(weatherSignal?.temperature_c);
        const city = String(weatherSignal?.city || profile?.city || "").trim();
        const icon = /雷/.test(condition)
            ? "thunderstorm"
            : /雨/.test(condition)
                ? "rainy"
                : /雪/.test(condition)
                    ? "weather_snowy"
                    : /阴|云/.test(condition)
                        ? "partly_cloudy_day"
                        : "light_mode";
        setText("edgeHomeWeatherIcon", icon);
        setText("edgeHomeWeatherTemp", available && Number.isFinite(temperature) ? `${temperature}°` : "--°");
        setText("edgeHomeWeatherCity", city || "天气");
        setText(
            "edgeHomeWeatherSub",
            available ? (condition || String(weatherSignal?.advice || "天气已更新").trim()) : (city ? "天气数据更新中" : "完善城市后显示天气")
        );
    }

    function renderWeekCalendar(preferences = null) {
        const grid = $("edgeHomeWeekGrid");
        const notes = $("edgeHomeCalendarNotes");
        if (!grid || !notes) return;
        const now = new Date(`${shanghaiDateKey()}T12:00:00+08:00`);
        setText("edgeHomeCalendarMonth", new Intl.DateTimeFormat("zh-CN", {
            timeZone: "Asia/Shanghai",
            month: "long",
        }).format(now));
        const weekday = ["日", "一", "二", "三", "四", "五", "六"];
        grid.innerHTML = Array.from({ length: 7 }, (_, index) => {
            const date = new Date(now.getTime() + index * 86400000);
            const day = date.getDay();
            const isWeekend = day === 0 || day === 6;
            return `
                <div class="editorial-day ${index === 0 ? "today" : ""} ${isWeekend ? "weekend" : ""}">
                    <span>${index === 0 ? "今天" : `周${weekday[day]}`}</span>
                    <strong>${date.getDate()}</strong>
                    <i></i>
                </div>
            `;
        }).join("");

        const schedule = preferences?.metadata?.care_card_schedule || {};
        const anniversary = upcomingAnniversary(schedule);
        const holiday = upcomingHolidayCard();
        const noteItems = [
            anniversary || holiday?.title || nextWeekendLabel(),
            anniversary ? "按每年同月同日提醒" : (holiday?.sub || "适合安排联系或回家计划"),
        ];
        notes.innerHTML = noteItems.map((item) => `
            <div class="editorial-calendar-note"><i></i><span>${escapeHtml(item)}</span></div>
        `).join("");
    }

    function cardBodyText(card, fallback = "") {
        return String(card?.body || fallback || "").trim().replace(/\s+/g, " ");
    }

    function shortText(value, limit = 58) {
        const text = String(value || "").trim().replace(/\s+/g, " ");
        if (text.length <= limit) return text;
        return `${text.slice(0, Math.max(0, limit - 3))}...`;
    }

    function genericCareText(value) {
        return /(家里一切平稳|聊聊家常|家里今天很平稳|打个电话聊聊近况|递杯茶|递茶|端水|送到手边|陪在身边)/.test(String(value || ""));
    }

    function careSafeTopicText(value, limit = 38) {
        return shortText(String(value || "")
            .replace(/<[^>]*>/g, " ")
            .replace(/\{\{[^}]*\}\}/g, " ")
            .replace(/\\(?:r|n|t)+/gi, " ")
            .replace(/&(?:nbsp|amp|quot|lt|gt|#\d+);/gi, " ")
            .replace(/[_｜|│].*$/g, "")
            .replace(/新闻频道|央视网|中国网|老年频道|公众号|视频号/g, "")
            .replace(/^#+\s*/g, "")
            .replace(/日期：\d{4}\/\d{1,2}\/\d{1,2}.*/g, "")
            .replace(/\s+/g, " ")
            .trim(), limit);
    }

    function friendlySourceLabel(source) {
        const raw = String(source || "").replace(/^www\./, "").trim().toLowerCase();
        if (!raw) return "内容源已筛选";
        const labels = [
            [/wsjkw\.sh\.gov\.cn/, "上海卫健委"],
            [/shobserver\.com|sghexport\.shobserver\.com/, "上观新闻"],
            [/sh\.people\.com\.cn|people\.com\.cn/, "人民网"],
            [/xinhuanet\.com/, "新华社"],
            [/cctv\.com|央视/, "央视"],
            [/gmw\.cn|news\.gmw\.cn/, "光明网"],
        ];
        const matched = labels.find(([pattern]) => pattern.test(raw));
        return matched ? matched[1] : "内容源已筛选";
    }

    function unsafeTopicText(value, options = {}) {
        const text = String(value || "");
        if (!/[\u4e00-\u9fff]{4,}/.test(text)) return true;
        if (/(字体放大|字体缩小|默认大小|来源\s*[:：]|作者\s*[:：]|日期\s*[:：]|###|\{\{|font-size|copyright|版权所有|网站地图|登录\s*注册)/i.test(text)) return true;
        const blocked = options.allowAntiFraud
            ? /(痴迷|割韭菜|谣言|投诉|死亡|猝死|癌|肿瘤|医院花钱|收割|曝光|乱象|焦虑|保健品骗局|坑老|习近平|金正恩|朝鲜|党代会|慢性病|疾病风险|医疗诊断)/
            : /(痴迷|骗局|诈骗|防骗|割韭菜|谣言|投诉|死亡|猝死|癌|肿瘤|医院花钱|收割|警惕|曝光|乱象|焦虑|保健品骗局|坑老|习近平|金正恩|朝鲜|党代会|慢性病|疾病风险|医疗诊断)/;
        return blocked.test(text);
    }

    function safeTopicRecommendation(recommendations, module = "") {
        return (Array.isArray(recommendations) ? recommendations : [])
            .filter((item) => !module || item?.module === module)
            .find((item) => {
            const source = String(item?.source || item?.url || "").toLowerCase();
            if (/(dangjian|cpc\.people|qstheory|theory\.people)/.test(source)) return false;
            const title = careSafeTopicText(item?.title, 80);
            const summary = careSafeTopicText(item?.summary || item?.content, 120);
            if (!title || unsafeTopicText(`${title} ${summary}`, { allowAntiFraud: module === "anti_fraud" })) return false;
            return title.length >= 4;
        }) || null;
    }

    function contentRegionLabel(profile, preferences) {
        const schedule = preferences?.metadata?.care_card_schedule || {};
        const region = schedule.content_region || {};
        const city = String(region.city || profile?.city || "").trim();
        const district = String(region.district || profile?.district || "").trim();
        return `${city}${district ? district : ""}` || "关注地区";
    }

    function enabledContentLabels(preferences) {
        const schedule = preferences?.metadata?.care_card_schedule || {};
        const types = schedule.content_types || {};
        const labels = [
            ["local_hotspots", "本地热点"],
            ["health_tips", "养生"],
            ["anti_fraud", "防诈骗"],
            ["culture_entertainment", "文娱"],
            ["weather", "天气"],
            ["holidays", "节日"],
            ["anniversaries", "纪念日"],
            ["visit_reminder", "回家提醒"],
        ];
        return labels.filter(([key]) => types[key]).map(([, label]) => label);
    }

    function recommendationSource(recommendation) {
        const raw = String(recommendation?.source || recommendation?.url || "").trim();
        return raw ? `来源 ${friendlySourceLabel(raw)}` : "按关怀设置";
    }

    function moduleRecommendationCard(module, recommendation, context) {
        const region = context.region || "本地";
        const interests = context.interests || "家常话题";
        const source = recommendationSource(recommendation);
        const hasCandidate = Boolean(recommendation);
        const candidateTitle = careSafeTopicText(recommendation?.title, 34);
        const candidateSummary = careSafeTopicText(recommendation?.summary || recommendation?.content, 76);
        const moduleCopy = {
            local_hotspots: {
                type: "本地热点",
                icon: "location_city",
                tone: "leaf",
                title: candidateTitle || `${region}今日生活提醒`,
                body: candidateSummary || "正在从便民服务、社区活动和出行信息中筛选值得关注的内容。",
                meta: hasCandidate ? source : "按区域偏好筛选",
                image: String(recommendation?.image_url || "assets/stitch-images/13-0028165750.jpg"),
                ratio: "portrait",
            },
            health_tips: {
                type: "养生小贴士",
                icon: "spa",
                tone: "warm",
                title: candidateTitle || "今日健康生活建议",
                body: candidateSummary || "聚焦喝水、作息、饮食和适度运动，不替代医疗建议。",
                meta: hasCandidate ? source : "按关注主题",
                image: String(recommendation?.image_url || "assets/stitch-images/09-cc5ea760d2.jpg"),
                ratio: "tall",
            },
            anti_fraud: {
                type: "防诈骗",
                icon: "verified_user",
                tone: "sun",
                title: candidateTitle || "陌生来电与转账提醒",
                body: candidateSummary || "只采用官方来源的低频安全提醒，不制造紧张感。",
                meta: hasCandidate ? source : "低频推送",
                image: String(recommendation?.image_url || "assets/stitch-images/04-047f4d8895.jpg"),
                ratio: "landscape",
            },
            culture_entertainment: {
                type: "文娱兴趣",
                icon: "theater_comedy",
                tone: "rose",
                title: candidateTitle || "今天值得看的文化内容",
                body: candidateSummary || `从${interests}中筛选轻松、正向的节目和活动信息。`,
                meta: hasCandidate ? source : "按兴趣生成",
                image: String(recommendation?.image_url || "assets/images/grandma-reading.jpg"),
                ratio: "square",
            },
            elder_interest_topics: {
                type: "兴趣推荐",
                icon: "chat",
                tone: "calm",
                title: candidateTitle || `围绕${interests.split("、").slice(0, 2).join("、") || "日常生活"}的今日推荐`,
                body: candidateSummary || "从已设置的兴趣中筛选轻松、正向的内容。",
                meta: hasCandidate ? source : "按关注主题",
                image: String(recommendation?.image_url || "assets/images/memory-relax-chat.jpg"),
                ratio: "portrait",
            },
        };
        return moduleCopy[module] || null;
    }

    function weatherCareBody(weatherSignal, city) {
        if (!weatherSignal?.available) {
            return "天气源暂不可用，今日关怀不会编造温度、降雨或实时预报。";
        }
        const condition = String(weatherSignal.condition || "").trim();
        const advice = String(weatherSignal.advice || "").replace(/\s+/g, " ").trim();
        const temp = Number(weatherSignal.temperature_c);
        if (/雨|雷|暴雨|阵雨/.test(condition)) {
            return `今天${condition}，电话里提醒出门带伞、路面湿滑慢一点。`;
        }
        if (Number.isFinite(temp) && temp >= 32) {
            return `今天${city || "当地"}偏热，适合提醒喝水、少久晒，再问问晚饭和近况。`;
        }
        if (Number.isFinite(temp) && temp <= 8) {
            return `今天气温偏低，适合提醒添衣保暖，顺便问问家里门窗和晚饭。`;
        }
        if (/风|降温|冷|寒/.test(advice)) {
            return "天气有变化，适合提醒添衣、关窗，再约一个方便通话的时间。";
        }
        return advice || "可以把天气作为今天电话问候的开场。";
    }

    function careCardDisplayTitle(card) {
        const raw = String(card?.title || "").trim();
        if (!raw) return "关怀卡片";
        if (!genericCareText(raw)) return raw;
        const text = cardBodyText(card);
        if (/(晴|阴|多云|雨|雪|气温|闷热|舒适|降温|升温)/.test(text)) return "天气问候卡";
        return `${cardDateLabel(card)}关怀`;
    }

    function careCardHistoryBody(card) {
        const fact = (Array.isArray(card?.facts) ? card.facts : [])
            .map((item) => String(item || "").trim())
            .find((item) => item && !genericCareText(item));
        if (fact) return shortText(fact, 42);
        const body = cardBodyText(card);
        if (body && !genericCareText(body) && !/张阿姨/.test(body)) return shortText(body, 42);
        return "根据家里状态、天气和日程生成。";
    }

    function careHistoryMarkup(card, index = 0) {
        const href = window.GoHomeEdge?.pageHref?.("companionship.html") || "companionship.html";
        const hasImage = Boolean(String(card?.image_url || "").trim());
        const showImage = hasImage && !genericCareText(card?.title);
        const dateLabel = cardDateLabel(card);
        const title = careCardDisplayTitle(card);
        const body = careCardHistoryBody(card);
        return `
            <a class="gohome-care-history-card ${showImage ? "" : "no-image"}" href="${escapeHtml(href)}">
                <div class="gohome-care-history-thumb" data-care-card-thumb>
                    ${showImage ? `<img class="hidden" alt="${escapeHtml(title)}" data-care-card-image="${escapeHtml(card.image_url)}" loading="lazy"/>` : ""}
                    <div class="gohome-care-history-fallback ${showImage ? "" : "visible"}" data-care-card-fallback>
                        <span class="material-symbols-outlined">volunteer_activism</span>
                        <strong>${escapeHtml(title)}</strong>
                        <small>${escapeHtml(body)}</small>
                    </div>
                </div>
                ${showImage ? `
                    <div class="gohome-care-history-copy">
                        <span>${escapeHtml(dateLabel)}</span>
                        <h4>${escapeHtml(title)}</h4>
                        <p>${escapeHtml(body)}</p>
                    </div>
                ` : ""}
            </a>
        `;
    }

    async function renderCareHistory(cards, family) {
        const section = $("edgeHomeCareHistorySection");
        const feed = $("edgeHomeCareHistory");
        const status = $("edgeHomeCareHistoryStatus");
        if (!section || !feed) return;
        const seen = new Set();
        const history = (Array.isArray(cards) ? cards : [])
            .filter((card) => {
                const key = String(card?.card_id || card?.id || `${card?.family_id || ""}:${card?.card_date || ""}`);
                if (!card || seen.has(key)) return false;
                seen.add(key);
                return true;
            })
            .slice(0, 8);
        section.classList.toggle("hidden", !history.length);
        if (!history.length) {
            feed.innerHTML = "";
            return;
        }
        if (status) {
            status.textContent = history.length > 1
                ? `${family?.name || "当前家庭"} · 最近 ${history.length} 张历史关怀卡。`
                : `${family?.name || "当前家庭"} · 1 张历史关怀卡。`;
        }
        feed.innerHTML = history.map(careHistoryMarkup).join("");
        void hydrateCareFeedImages(feed);
    }

    function deviceLooksOnline(device = {}, enabled = []) {
        return Boolean(
            device.worker_running
            || device.last_seen_at
            || (Array.isArray(enabled) && enabled.some((camera) => String(camera.status || "").toLowerCase() === "online"))
        );
    }

    function feedFallbackImage(type) {
        const label = String(type || "");
        if (/本地/.test(label)) return "assets/stitch-images/13-0028165750.jpg";
        if (/养生|健康/.test(label)) return "assets/stitch-images/09-cc5ea760d2.jpg";
        if (/诈骗|安全/.test(label)) return "assets/stitch-images/04-047f4d8895.jpg";
        if (/文娱|兴趣/.test(label)) return "assets/images/grandma-reading.jpg";
        return "assets/images/memory-relax-chat.jpg";
    }

    function pushCardMarkup(card) {
        const href = String(card.href || "").trim();
        const tag = href ? "a" : "article";
        const attrs = href ? `href="${escapeHtml(window.GoHomeEdge?.pageHref?.(href) || href)}"` : "";
        const sizeClass = card.size ? ` ${String(card.size).replace(/[^\w-]/g, "")}` : "";
        const category = /本地/.test(card.type) ? "local"
            : /养生|天气|健康/.test(card.type) ? "health"
                : /诈骗|安全/.test(card.type) ? "fraud"
                    : /文娱|兴趣|问候/.test(card.type) ? "interest"
                        : "all";
        const ratio = String(card.ratio || "portrait").replace(/[^\w-]/g, "");
        const fallbackImage = feedFallbackImage(card.type);
        const media = card.image
            ? `<div class="gohome-push-media ratio-${escapeHtml(ratio)}">
                    <img src="${escapeHtml(card.image)}" data-feed-fallback="${escapeHtml(fallbackImage)}" alt="${escapeHtml(card.title || card.type || "今日资讯")}" loading="lazy"/>
                    <span class="gohome-push-type">${escapeHtml(card.type || "资讯")}</span>
                </div>`
            : `<div class="gohome-push-card-top">
                    <span class="material-symbols-outlined">${escapeHtml(card.icon || "favorite")}</span>
                    <span class="gohome-push-type">${escapeHtml(card.type || "提醒")}</span>
                </div>`;
        return `
            <${tag} ${attrs} data-feed-category="${category}" class="gohome-push-card ${escapeHtml(card.tone || "calm")}${escapeHtml(sizeClass)}">
                ${media}
                <div class="gohome-push-card-copy">
                    <h4>${escapeHtml(card.title || "今日资讯")}</h4>
                    <p>${escapeHtml(shortText(card.body || "打开后查看完整内容。", 72))}</p>
                    <strong>${escapeHtml(card.meta || "")}</strong>
                </div>
            </${tag}>
        `;
    }

    function friendlyTopicTitle(contentSignal, interests, recommendation) {
        const count = Array.isArray(contentSignal?.recommendations) ? contentSignal.recommendations.length : 0;
        const title = careSafeTopicText(recommendation?.title, 18);
        if (/^(澎湃新闻|健康活动|报刊)$/.test(title)) return "可聊时令养生";
        if (/研讨会|举行|活动|趋势|中心|聚焦/.test(title)) return "可聊时令养生";
        if (title) return title;
        if (!count) return "今天聊点感兴趣的";
        const topic = String(interests || "家常话题").split("、").filter(Boolean).slice(0, 2).join("、") || "家常话题";
        return `可聊${topic}`;
    }

    function friendlyTopicBody(contentSignal, interests, recommendation) {
        const count = Array.isArray(contentSignal?.recommendations) ? contentSignal.recommendations.length : 0;
        const summary = careSafeTopicText(recommendation?.summary, 54);
        const title = careSafeTopicText(recommendation?.title, 80);
        if (/^(澎湃新闻|健康活动|报刊)$/.test(title)) return "今天有健康生活内容，可以问问最近饮食、作息和想看的节目。";
        if (/研讨会|举行|活动|趋势|中心|聚焦/.test(title)) return "今天有健康生活内容，可以问问最近饮食、作息和想看的节目。";
        if (summary) return `${summary}，适合电话里轻轻带一句。`;
        if (!count && contentSignal?.available === false) return "今天先按关注主题准备一句自然开场。";
        if (!count) return `围绕${interests}准备一句电话开场。`;
        return "内容搜索已找到可聊方向，先筛成适合家里电话的轻话题。";
    }

    function buildPushCards({ careCard, family, profile, preferences, device, enabled = [], liveEvents = [], weatherSignal, contentSignal }) {
        const schedule = preferences?.metadata?.care_card_schedule || {};
        const enabledIds = new Set((Array.isArray(enabled) ? enabled : []).map((camera) => Number(camera.id)));
        const eventScope = (Array.isArray(liveEvents) ? liveEvents : []).filter((event) => (
            !enabledIds.size || enabledIds.has(Number(event.camera_id))
        ));
        const openEvents = eventScope.filter((event) => !event.acknowledged);
        const criticalEvents = openEvents.filter((event) => event.level === "critical");
        const interests = Array.isArray(schedule.interest_topics) && schedule.interest_topics.length
            ? schedule.interest_topics.slice(0, 3).join("、")
            : "养生、天气、家常";
        const recommendations = Array.isArray(contentSignal?.recommendations) && contentSignal.recommendations.length
            ? contentSignal.recommendations
            : (Array.isArray(careCard?.content_recommendations) ? careCard.content_recommendations : [])
                .filter((item) => item && item.type !== "image_brief");
        const cards = [];
        if (criticalEvents.length) {
            cards.push({
                type: "安全提醒",
                icon: "priority_high",
                tone: "alert",
                size: "feature",
                title: "有提醒需要先确认",
                body: "先看事件证据，再联系家里。",
                meta: `${criticalEvents.length} 条重要事件`,
                href: "events.html",
            });
        }
        const types = schedule.content_types || {};
        const moduleContext = {
            region: contentRegionLabel(profile, preferences),
            interests,
        };
        ["local_hotspots", "health_tips", "anti_fraud", "culture_entertainment"].forEach((module) => {
            if (!types[module]) return;
            const recommendation = safeTopicRecommendation(recommendations, module);
            const card = moduleRecommendationCard(module, recommendation, moduleContext);
            if (card) cards.push(card);
        });
        if (!cards.some((card) => card.image) && types.elder_interest_topics) {
            const recommendation = safeTopicRecommendation(recommendations);
            cards.push(moduleRecommendationCard("elder_interest_topics", recommendation, moduleContext));
        }
        return cards;
    }

    function renderStatusStrip(items) {
        setHtml("edgeHomeStatusStrip", items.map((item) => `
            <span class="${escapeHtml(item.tone || "muted")}"><i></i>${escapeHtml(item.label)}</span>
        `).join(""));
    }

    function setHomeStatusPill(label, tone = "good") {
        const node = $("edgeHomeCareStatus");
        if (!node) return;
        node.textContent = label;
        node.className = `gohome-status-pill ${tone}`;
    }

    function renderHomeSummary({ user, family, device = {}, enabled = [], liveEvents = [], careCard, profile }) {
        const deviceOnline = deviceLooksOnline(device, enabled);
        const enabledIds = new Set((Array.isArray(enabled) ? enabled : []).map((camera) => Number(camera.id)));
        const eventScope = (Array.isArray(liveEvents) ? liveEvents : []).filter((event) => (
            !enabledIds.size || enabledIds.has(Number(event.camera_id))
        ));
        const openEvents = eventScope.filter((event) => !event.acknowledged);
        const criticalEvents = openEvents.filter((event) => event.level === "critical");
        const familyName = family?.name || "本地家庭";
        const elderName = profile?.display_name || "家人";
        const eventLabel = criticalEvents.length
            ? `${criticalEvents.length} 条重要`
            : openEvents.length
                ? `${openEvents.length} 条待看`
                : "无待处理";

        setText("edgeHomeFamilyLine", `${familyName} · ${user?.display_name || user?.phone || "家属端"}`);
        setText("edgeHomeBoxState", deviceOnline ? "已同步" : "待确认");
        setText("edgeHomeCameraState", enabled.length ? `${enabled.length} 路` : "未接入");
        setText("edgeHomeEventState", eventLabel);

        if (criticalEvents.length) {
            setText("edgeHomeLeadTitle", "家里有提醒待确认");
            setText("edgeHomeLeadSub", "先查看事件证据，再决定打电话或通知其他家属。");
            setHomeStatusPill("需确认", "warn");
        } else if (enabled.length && deviceOnline) {
            setText("edgeHomeLeadTitle", `${elderName}家里正在同步`);
            setText("edgeHomeLeadSub", careCard?.title ? "天气、话题和家里状态已同步，今日图文卡已生成。" : "摄像头和家庭盒子在线，今日关怀正在生成。");
            setHomeStatusPill("平稳", "good");
        } else if (enabled.length) {
            setText("edgeHomeLeadTitle", "摄像头已配置，盒子待确认");
            setText("edgeHomeLeadSub", "App 已读到摄像头配置，等待家庭盒子回传在线状态。");
            setHomeStatusPill("待确认", "muted");
        } else {
            setText("edgeHomeLeadTitle", "先接入家里的摄像头");
            setText("edgeHomeLeadSub", "完成摄像头配置后，首页会显示天气、话题、家庭状态和回家提醒。");
            setHomeStatusPill("待配置", "muted");
        }

        renderStatusStrip([
            { label: deviceOnline ? "盒子已同步" : "盒子待确认", tone: deviceOnline ? "good" : "muted" },
            { label: enabled.length ? `${enabled.length} 路摄像头` : "摄像头未接入", tone: enabled.length ? "good" : "muted" },
            { label: eventLabel, tone: criticalEvents.length ? "warn" : openEvents.length ? "muted" : "good" },
        ]);
    }

    async function renderCareCardFeed(cards, family, context = {}) {
        const section = $("edgeHomeCareSection");
        const feed = $("edgeHomeCareFeed");
        const status = $("edgeHomeCareFeedStatus");
        if (!section || !feed) return;
        const history = (Array.isArray(cards) ? cards : [])
            .filter((card) => card)
            .slice(0, 12);
        section.classList.toggle("hidden", false);
        feed.className = "gohome-push-feed gohome-story-grid";
        if (status) {
            const labels = enabledContentLabels(context.preferences).slice(0, 6);
            status.innerHTML = labels.length
                ? `按“我的”设置筛选 <span>${escapeHtml(labels.join(" / "))}</span>`
                : "在“我的”中选择关注的内容类型。";
        }
        const pushCards = buildPushCards({
            careCard: context.careCard || history[0],
            family,
            profile: context.profile,
            preferences: context.preferences,
            device: context.device,
            enabled: context.enabled || [],
            liveEvents: context.liveEvents || [],
            weatherSignal: context.weatherSignal,
            contentSignal: context.contentSignal,
        });
        feed.innerHTML = pushCards.map(pushCardMarkup).join("");
        feed.querySelectorAll("img[data-feed-fallback]").forEach((image) => {
            image.addEventListener("error", () => {
                const fallback = image.dataset.feedFallback || "";
                if (fallback && !image.src.endsWith(fallback)) image.src = fallback;
            }, { once: true });
        });
        applyHomeFeedFilter();
    }

    function applyHomeFeedFilter() {
        document.querySelectorAll("[data-feed-filter]").forEach((button) => {
            const selected = button.dataset.feedFilter === activeFeedFilter;
            button.classList.toggle("active", selected);
            button.setAttribute("aria-selected", selected ? "true" : "false");
        });
        document.querySelectorAll("#edgeHomeCareFeed [data-feed-category]").forEach((card) => {
            const category = card.dataset.feedCategory || "all";
            card.classList.toggle("hidden", activeFeedFilter !== "all" && category !== activeFeedFilter);
        });
    }

    function wireHomeFeedFilters() {
        document.querySelectorAll("[data-feed-filter]").forEach((button) => {
            button.addEventListener("click", () => {
                activeFeedFilter = button.dataset.feedFilter || "all";
                applyHomeFeedFilter();
            });
        });
    }

    function isCareCritical(card) {
        const text = [
            card?.title,
            card?.body,
            ...(Array.isArray(card?.facts) ? card.facts : []),
        ].map(String).join(" ");
        if (/无高优先级|无异常|没有未处理|没有待处理|当前没有|整体平稳|一切平稳/.test(text)) return false;
        return /重要|异常|高优先级|告警|跌倒|离线|待确认/.test(text);
    }

    function renderCareCardSummary(card, family) {
        if (!card) {
            $("edgeHomeCarePreviewSection")?.classList.add("hidden");
            $("edgeHomeCareCardLink")?.classList.remove("has-generated-image");
            setText("edgeHomeCareMeta", `${family?.name || "当前家庭"} · 今日关怀`);
            setText("edgeHomeCareTitle", "今日关怀正在生成");
            setText("edgeHomeCareBody", "稍后会把家里状态、日历提醒和可聊话题汇总成一张图文卡片。");
            const facts = $("edgeHomeCareFacts");
            if (facts) facts.innerHTML = "";
            const link = $("edgeHomeCareCardLink");
            if (link) link.href = window.GoHomeEdge?.pageHref?.("companionship.html") || "companionship.html";
            setHomeCareImageFallback("今日关怀", "家里近况和适合联系的话题会整理在这里。", "favorite");
            return;
        }
        $("edgeHomeCarePreviewSection")?.classList.remove("hidden");
        const critical = isCareCritical(card);
        const hasGeneratedImage = Boolean(String(card?.image_url || "").trim());
        const featureLink = $("edgeHomeCareCardLink");
        featureLink?.classList.toggle("has-generated-image", hasGeneratedImage);
        setText("edgeHomeCareMeta", `${cardDateLabel(card)} · ${family?.name || "当前家庭"}`);
        setText("edgeHomeCareTitle", hasGeneratedImage ? "今日关怀卡片" : careCardDisplayTitle(card));
        setText(
            "edgeHomeCareBody",
            hasGeneratedImage
                ? "由家里状态、天气和日程生成，点开看完整图文和问候动作。"
                : shortText(cardBodyText(card, "点开看完整图文。"), 64)
        );
        const link = featureLink;
        if (link) link.href = window.GoHomeEdge?.pageHref?.("companionship.html") || "companionship.html";
        renderHomeCareImage(card);
        const facts = $("edgeHomeCareFacts");
        if (facts) {
            facts.innerHTML = "";
            facts.classList.remove("hidden");
            (Array.isArray(card.facts) ? card.facts : []).slice(0, 2).forEach((fact) => {
                const item = document.createElement("div");
                item.className = "gohome-mini-fact";
                item.innerHTML = `
                    <span class="material-symbols-outlined">check_circle</span>
                    <p>${escapeHtml(fact)}</p>
                `;
                facts.append(item);
            });
        }
        setAction("edgeHomeCarePrimaryAction", "companionship.html", "看完整卡片", "volunteer_activism");
        setAction("edgeHomeCareSecondaryAction", critical ? "events.html" : "care_schedule.html", critical ? "查看提醒" : "关怀设置", critical ? "history" : "schedule");
    }

    function syncCameraEntryLinks(camera) {
        const suffix = camera?.id ? `?camera_id=${encodeURIComponent(camera.id)}` : "";
        const monitorHref = suffix ? `monitor.html${suffix}` : "monitor.html";
        const watchHref = suffix ? `watch.html${suffix}` : "watch.html";
        const eventsHref = suffix ? `events.html${suffix}` : "events.html";
        const entries = {
            edgeHomePrimaryAction: watchHref,
            edgeHomeMonitorLink: monitorHref,
            edgeHomeWatchLink: watchHref,
            edgeHomeEventsLink: eventsHref,
            edgeHomeNavMonitorLink: monitorHref,
            edgeHomeNavEventsLink: eventsHref,
        };
        Object.entries(entries).forEach(([id, href]) => {
            const node = $(id);
            if (node) node.href = window.GoHomeEdge?.pageHref?.(href) || href;
        });
    }

    function toggleSetupMode(show) {
        const setup = $("edgeHomeSetupPanel");
        if (!setup) return;
        document.body.classList.toggle("gohome-setup-mode", show);
        setup.classList.toggle("hidden", !show);
        if (show) $("edgeHomeCarePreviewSection")?.classList.add("hidden");
        CONTENT_SECTION_IDS.forEach((id) => $(id)?.classList.toggle("hidden", show));
    }

    function setSetupStates(account, family, profile, binding, badge = "未完成") {
        setText("edgeHomeAccountState", account);
        setText("edgeHomeFamilyState", family);
        setText("edgeHomeProfileState", profile);
        setText("edgeHomeBindingState", binding);
        setText("edgeHomeSetupBadge", badge);
    }

    function isLocalCamera(camera) {
        const streamUrl = String(camera?.stream_url || "").toLowerCase();
        return /^(local|webcam|device|camera):/.test(streamUrl) || /^\d+$/.test(streamUrl);
    }

    function enabledCameras(cameras) {
        return (Array.isArray(cameras) ? cameras : []).filter((camera) => camera && camera.enabled !== false);
    }

    function preferredCamera(cameras) {
        return [...cameras].sort((a, b) => {
            const score = (camera) => (
                (camera.enabled ? 100 : 0) +
                (camera.status === "online" ? 30 : 0) +
                (isLocalCamera(camera) ? 0 : 20)
            );
            return score(b) - score(a);
        })[0];
    }

    function importantEvent(events, camera) {
        const currentCameraEvents = events.filter((event) => Number(event.camera_id) === Number(camera.id));
        return currentCameraEvents.find((event) => !event.acknowledged && event.level === "critical")
            || currentCameraEvents.find((event) => !event.acknowledged)
            || null;
    }

    function isStaleCameraOffline(event, camera) {
        if (event?.type !== "camera_offline" || event.acknowledged || !camera) return false;
        if (String(camera.status || "").toLowerCase() !== "online") return false;
        const eventTime = Date.parse(event.occurred_at || event.created_at || "");
        const seenTime = Date.parse(camera.last_seen_at || camera.edge_reported_at || camera.updated_at || "");
        return Number.isFinite(eventTime) && Number.isFinite(seenTime) && seenTime >= eventTime;
    }

    function withoutStaleCameraOffline(events, cameras) {
        const camerasById = new Map((Array.isArray(cameras) ? cameras : []).map((camera) => [Number(camera.id), camera]));
        return (Array.isArray(events) ? events : []).filter((event) => !isStaleCameraOffline(event, camerasById.get(Number(event.camera_id))));
    }

    function messageOnlyReferences(message, eventIds) {
        const sourceIds = Array.isArray(message?.source_event_ids) ? message.source_event_ids.map(String) : [];
        return sourceIds.length > 0 && sourceIds.every((id) => eventIds.has(String(id)));
    }

    function messageHasVisibleEvent(message, eventIds) {
        const sourceIds = Array.isArray(message?.source_event_ids) ? message.source_event_ids.map(String) : [];
        return !sourceIds.length || sourceIds.some((id) => eventIds.has(String(id)));
    }

    function daysSinceDateString(value) {
        const raw = String(value || "").trim();
        if (!raw) return null;
        const date = new Date(raw.includes("T") ? raw : `${raw}T00:00:00+08:00`);
        if (Number.isNaN(date.getTime())) return null;
        return Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
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

    async function loadWeatherSignal(familyId, profile) {
        if (!familyId || !window.GoHomeEdge?.v1WeatherSignals) return null;
        try {
            return await window.GoHomeEdge.v1WeatherSignals(familyId, {
                elder_id: profile?.elder_id || profile?.id || "elder_primary",
                city: profile?.city || "",
            });
        } catch (_error) {
            return null;
        }
    }

    async function loadContentRecommendations(familyId, profile) {
        if (!familyId || !window.GoHomeEdge?.v1ContentRecommendations) return null;
        try {
            return await window.GoHomeEdge.v1ContentRecommendations(familyId, {
                elder_id: profile?.elder_id || profile?.id || "elder_primary",
                city: profile?.city || "",
                district: profile?.district || "",
            });
        } catch (_error) {
            return null;
        }
    }

    function renderLocationSummary(profile, preferences) {
        const section = $("edgeHomeLocationSection");
        if (!section) return;
        section.classList.remove("hidden");
        const city = String(profile?.city || "").trim();
        const schedule = preferences?.metadata?.care_card_schedule || {};
        const visit = schedule.visit_reminder || {};
        const days = daysSinceDateString(visit.last_visit_at);
        setText("edgeHomeLocationTitle", city ? `${city} · 家庭位置` : "家庭位置待完善");
        setText("edgeHomeLocationDistance", "距离待授权");
        setText("edgeHomeLocationSub", "iOS 定位授权接入后，这里显示当前位置与家的实际距离。");
        setText("edgeHomeVisitState", days === null ? "上次回家时间待补充" : `距离上次回家 ${days} 天`);
    }

    function snapshotState(snapshot) {
        const tags = snapshot.tags || [];
        const analysis = snapshot.analysis || {};
        const personCount = snapshot.person_count ?? analysis.person_count;

        if (tags.includes("fall_candidate") || analysis.fall_candidate) {
            return {
                title: "客厅出现疑似跌倒姿态，建议你现在确认一下",
                subtitle: "系统识别到人体框比例和位置异常，这不是最终诊断，但值得立刻看一眼。",
                fact: "疑似跌倒姿态",
                factSub: "视觉模型结果触发了高优先级提醒。",
                feeling: "需要马上确认",
                feelingSub: "先确认家中人员状态，再判断是不是误报。",
                action: "立即联系家里",
                actionSub: "如果联系不上，再通知其他家属或邻居。",
                snapshot: "检测到疑似跌倒候选",
            };
        }

        if (tags.includes("black_screen") || analysis.black_screen) {
            return {
                title: "摄像头画面疑似遮挡或黑屏，需要看一下设备",
                subtitle: "本机服务仍在线，但画面亮度和对比度异常，可能是遮挡、背光或摄像头异常。",
                fact: "画面异常",
                factSub: "亮度和对比度低于阈值。",
                feeling: "需要排查",
                feelingSub: "先看摄像头位置，再确认家里情况。",
                action: "检查摄像头",
                actionSub: "如果画面恢复，事件可以标记为已处理。",
                snapshot: "画面疑似遮挡或黑屏",
            };
        }

        if (personCount !== null && personCount !== undefined) {
            if (personCount > 0) {
                return {
                    title: `客厅检测到 ${personCount} 个人，当前家里状态平稳`,
                    subtitle: "本机守护服务正在持续抽帧识别，目前没有触发高优先级异常。",
                    fact: `${personCount} 人在画面中`,
                    factSub: "人形检测已接入，当前画面有人。",
                    feeling: "家里有活动",
                    feelingSub: "这类结果适合转成安心提醒，而不是告警。",
                    action: "继续观察",
                    actionSub: "有空时打一通电话，比等告警更有温度。",
                    snapshot: `画面检测到 ${personCount} 个人`,
                };
            }
            return {
                title: "客厅暂时没有检测到人，守护服务正在持续观察",
                subtitle: "这不一定是异常，只说明当前这张截图里没有人形目标；系统会继续按规则判断。",
                fact: "当前未见人形",
                factSub: "视觉模型没有在最新截图中识别到人。",
                feeling: "家里很安静",
                feelingSub: "如果持续超过阈值，系统会生成提醒。",
                action: "继续观察",
                actionSub: "现在可以去守护页看实时截图。",
                snapshot: "当前画面暂未检测到人",
            };
        }

        return {
            title: "本机守护服务已连接，正在观察家里状态",
            subtitle: "当前使用基础视觉指标判断画面变化、黑屏和离线情况。",
            fact: "服务在线",
            factSub: "摄像头最新截图已经同步。",
            feeling: "家里平稳",
            feelingSub: "还没有触发需要处理的提醒。",
            action: "继续观察",
            actionSub: "下一步可以打开守护页查看细节。",
            snapshot: "最新画面已同步",
        };
    }

    function fallbackGuestHome() {
        toggleMessageSection(false);
        toggleSetupMode(true);
        renderHomeSummary({
            user: { display_name: "未登录" },
            family: { name: "回家" },
            device: {},
            enabled: [],
            liveEvents: [],
        });
        renderCareCardSummary(null, { name: "回家" });
        renderCareHistory([], { name: "回家" });
        renderLocationSummary(null, null);
        setSetupStates("未登录", "未开始", "待填写", "未绑定", "先登录");
        setText("edgeHomeDevice", "先接身份");
        setText("edgeHomeTime", "先登录");
        setText("edgeHomeBoxState", "未登录");
        setText("edgeHomeCameraState", "待接入");
        setText("edgeHomeTitle", "先登录，再把家庭和设备接上。");
        setText("edgeHomeSubtitle", "");
        setAction("edgeHomePrimaryAction", "login.html", "去登录", "login");
        setAction("edgeHomeSecondaryAction", "family.html", "家庭空间", "groups");
        toggleSetupMode(true);
    }

    function renderNoFamilyHome(user) {
        toggleMessageSection(false);
        toggleSetupMode(true);
        renderHomeSummary({
            user,
            family: { name: "家庭待创建" },
            device: {},
            enabled: [],
            liveEvents: [],
        });
        renderCareCardSummary(null, { name: "家庭待创建" });
        renderCareHistory([], { name: "家庭待创建" });
        renderLocationSummary(null, null);
        setSetupStates("已登录", "未创建", "待填写", "待绑定", "下一步");
        setText("edgeHomeDevice", user.display_name || user.phone || "已登录");
        setText("edgeHomeTime", "下一步");
        setText("edgeHomeBoxState", "未建家");
        setText("edgeHomeCameraState", "待接入");
        setText("edgeHomeTitle", "先建家庭。");
        setText("edgeHomeSubtitle", "");
        setAction("edgeHomePrimaryAction", "family.html", "创建家庭", "groups");
        setAction("edgeHomeSecondaryAction", "login.html", "切换账号", "person");
        toggleSetupMode(true);
    }

    function renderNeedsProfileHome(user, family) {
        toggleMessageSection(false);
        toggleSetupMode(true);
        renderHomeSummary({
            user,
            family,
            device: {},
            enabled: [],
            liveEvents: [],
        });
        renderCareCardSummary(null, family);
        renderCareHistory([], family);
        renderLocationSummary(null, null);
        setSetupStates("已登录", family?.name || "已创建", "待填写", "待绑定", "待资料");
        setText("edgeHomeDevice", user.display_name || user.phone || "已登录");
        setText("edgeHomeTime", "填写资料");
        setText("edgeHomeBoxState", "待绑定");
        setText("edgeHomeCameraState", "待接入");
        setText("edgeHomeTitle", "先填写家庭联系人资料。");
        setText("edgeHomeSubtitle", "称呼、电话和所在城市会用于拨号、天气、关怀卡片和后续提醒。");
        const familyId = family?.id ? `?family_id=${encodeURIComponent(family.id)}&next=device_binding.html` : "";
        setAction("edgeHomePrimaryAction", `parent_profile.html${familyId}`, "填写资料", "badge");
        setAction("edgeHomeSecondaryAction", "family.html", "家庭空间", "groups");
        toggleSetupMode(true);
    }

    function renderNeedsBindingHome(user, family, profile = null) {
        toggleMessageSection(false);
        toggleSetupMode(true);
        renderHomeSummary({
            user,
            family,
            device: {},
            enabled: [],
            liveEvents: [],
        });
        renderCareCardSummary(null, family);
        renderCareHistory([], family);
        setSetupStates("已登录", family?.name || "已创建", profile ? "已填写" : "待填写", "待绑定", "待绑定");
        setText("edgeHomeDevice", user.display_name || user.phone || "已登录");
        setText("edgeHomeTime", "最后一步");
        setText("edgeHomeBoxState", "待绑定");
        setText("edgeHomeCameraState", "待接入");
        setText("edgeHomeTitle", "把这台设备绑到家庭。");
        setText("edgeHomeSubtitle", "输入盒身二维码内容、序列号或临时绑定码后，才能配置摄像头。");
        setAction("edgeHomePrimaryAction", familyPath("device_binding.html", family), "绑定设备", "link");
        setAction("edgeHomeSecondaryAction", "family.html", "家庭空间", "groups");
        toggleSetupMode(true);
    }

    async function render() {
        if (!window.GoHomeEdge) return;
        if (renderInFlight) return;
        renderInFlight = true;
        try {
            GoHomeEdge.bootstrapLaunchState?.();
            await GoHomeEdge.connect();
            let user = null;
            let coreState = null;
            if (GoHomeEdge.isAuthenticated()) {
                try {
                    [user, coreState] = await Promise.all([
                        GoHomeEdge.currentUser(),
                        Promise.all([
                            GoHomeEdge.myFamilies(),
                            GoHomeEdge.appDevice(),
                            GoHomeEdge.appCameras(),
                            GoHomeEdge.appEvents("limit=30"),
                        ]),
                    ]);
                } catch (_error) {
                    GoHomeEdge.clearAuthToken();
                }
            }
            if (!user) {
                fallbackGuestHome();
                return;
            }

            const [families, device, cameras, events] = coreState;
            const enabled = enabledCameras(cameras);
            const primaryFamily = Array.isArray(families) ? families[0] : null;
            if (!primaryFamily) {
                renderNoFamilyHome(user);
                return;
            }

            const [elderProfile, bindings] = await Promise.all([
                loadElderProfile(primaryFamily.id),
                GoHomeEdge.deviceBindings(primaryFamily.id),
            ]);
            if (!elderProfile) {
                renderNeedsProfileHome(user, primaryFamily);
                return;
            }
            renderDateRail(null, elderProfile);

            const currentBinding = bindings.find((item) => String(item.status || "active") !== "revoked") || null;
            if (!currentBinding) {
                renderNeedsBindingHome(user, primaryFamily, elderProfile);
                return;
            }

            const liveEvents = withoutStaleCameraOffline(events, cameras);
            const camera = preferredCamera(enabled);

            setText("edgeHomeDevice", primaryFamily.name || "家庭空间");
            setText("edgeHomeTime", deviceLooksOnline(device, enabled) ? "家庭盒子已同步" : "等待家庭盒子");
            setText("edgeHomeBoxState", deviceLooksOnline(device, enabled) ? "已同步" : "待确认");
            setText("edgeHomeCameraState", enabled.length ? `${enabled.length} 路` : "未接入");

            if (!camera) {
                toggleSetupMode(true);
                setSetupStates("已登录", primaryFamily?.name || "已创建", "已填写", "已绑定，待摄像头", "待摄像头");
                syncCameraEntryLinks(null);
                if (cameras.length) {
                    renderHomeSummary({ user, family: primaryFamily, device, enabled, liveEvents, careCard: null, profile: elderProfile });
                    setText("edgeHomeTime", "等待重新启用摄像头");
                    setText("edgeHomeCameraState", "未启用");
                    setText("edgeHomeTitle", "当前没有启用中的摄像头");
                    setText("edgeHomeSubtitle", "先在摄像头配置页启用至少一路摄像头，盒子同步成功后再进入首页。");
                    setAction("edgeHomePrimaryAction", familyPath("connect.html", primaryFamily), "配置摄像头", "nest_cam_indoor");
                    toggleSetupMode(true);
                } else {
                    renderHomeSummary({ user, family: primaryFamily, device, enabled: [], liveEvents, careCard: null, profile: elderProfile });
                    setText("edgeHomeTime", "等待摄像头接入");
                    setText("edgeHomeCameraState", "未接入");
                    setText("edgeHomeTitle", "还没有添加摄像头");
                    setText("edgeHomeSubtitle", "在 App 里添加摄像头配置，家庭盒子会从云端拉取并在家中局域网内测试。");
                    setAction("edgeHomePrimaryAction", familyPath("connect.html", primaryFamily), "添加摄像头", "nest_cam_indoor");
                    toggleSetupMode(true);
                }
                return;
            }

            renderHomeSummary({
                user,
                family: primaryFamily,
                device,
                enabled,
                liveEvents,
                careCard: null,
                profile: elderProfile,
            });
            renderLocationSummary(elderProfile, null);
            toggleSetupMode(false);
            setAction("edgeHomePrimaryAction", "watch.html", "实时观看", "nest_cam_indoor");
            setAction("edgeHomeSecondaryAction", "family.html", "家庭空间", "groups");
            syncCameraEntryLinks(camera);
            window.GoHomeAppStore?.markPageReady?.();

            const careCardPromise = loadCareCard(primaryFamily.id);
            const careCardsPromise = loadCareCards(primaryFamily.id);
            const carePreferencesPromise = loadCarePreferences(primaryFamily.id);
            const careCard = await careCardPromise;
            renderHomeSummary({
                user,
                family: primaryFamily,
                device,
                enabled,
                liveEvents,
                careCard,
                profile: elderProfile,
            });
            renderCareCardSummary(careCard, primaryFamily);
            if (careCard?.pending_refresh) refreshPendingCareCard(primaryFamily.id, primaryFamily);
            window.GoHomeAppStore?.scheduleCapture?.();

            const [careCards, carePreferences] = await Promise.all([
                careCardsPromise,
                carePreferencesPromise,
            ]);
            renderWeekCalendar(carePreferences);
            const currentCareKey = String(careCard?.card_id || careCard?.id || "");
            const currentCareDate = String(careCard?.card_date || "");
            const historyCards = [careCard, ...careCards].filter((card) => {
                if (!card) return false;
                const key = String(card.card_id || card.id || "");
                const date = String(card.card_date || "");
                if (currentCareKey && key === currentCareKey) return false;
                if (currentCareDate && date === currentCareDate) return false;
                return true;
            });
            renderCareHistory(historyCards, primaryFamily);
            renderCareCardFeed(careCards, primaryFamily, {
                careCard,
                profile: elderProfile,
                preferences: carePreferences,
                device,
                enabled,
                liveEvents,
                weatherSignal: null,
                contentSignal: null,
            });
            renderLocationSummary(elderProfile, carePreferences);
            void Promise.all([
                loadWeatherSignal(primaryFamily.id, elderProfile),
                loadContentRecommendations(primaryFamily.id, elderProfile),
            ]).then(([weatherSignal, contentSignal]) => {
                renderDateRail(weatherSignal, elderProfile);
                renderCareCardFeed(careCards, primaryFamily, {
                    careCard,
                    profile: elderProfile,
                    preferences: carePreferences,
                    device,
                    enabled,
                    liveEvents,
                    weatherSignal,
                    contentSignal,
                });
                window.GoHomeAppStore?.scheduleCapture?.();
            }).catch(() => {});
            const staleEventIds = new Set(events.filter((event) => !liveEvents.includes(event)).map((event) => String(event.id)));
            const visibleEventIds = new Set(liveEvents.filter((event) => enabled.some((item) => Number(item.id) === Number(event.camera_id))).map((event) => String(event.id)));
            let primaryMessage = await loadPrimaryMessage(primaryFamily.id);
            if (messageOnlyReferences(primaryMessage, staleEventIds)) primaryMessage = null;
            if (!messageHasVisibleEvent(primaryMessage, visibleEventIds)) primaryMessage = null;
            renderMessageCard(primaryMessage);

            const event = importantEvent(liveEvents, camera);
            const snapshot = await GoHomeEdge.appLatestSnapshot(camera.id, { allowMissing: true });
            if (snapshot?.available === false) {
                setText("edgeHomeTime", `实时预览中 · ${camera.room || camera.name || "家里"} · ${device.detector_backend === "yolo" ? "视觉检测中" : "基础检测中"}`);
                setText("edgeHomeTitle", event ? event.summary : "本机守护服务已连接，正在同步最新检测摘要");
                setText("edgeHomeSubtitle", event ? "本机服务已经生成一条待确认提醒，建议先去事件页查看截图和处理状态。" : "实时画面已经恢复，检测摘要会在后台下一轮抽帧后补上。");
                setText("edgeHomeFactTitle", event ? GoHomeEdge.eventLabel(event.type) : "实时画面正常");
                setText("edgeHomeFactSub", event ? `${GoHomeEdge.fmtDateTime(event.occurred_at)} 触发，来自 ${event.camera_name || camera.name || "摄像头"}。` : "当前优先展示实时视频，证据截图稍后同步。");
                setText("edgeHomeFeelingTitle", event ? "有一条提醒待确认" : "家里平稳");
                setText("edgeHomeFeelingSub", event ? "这类信息应该进入告警处理流程，而不是只作为普通动态展示。" : "不影响你先进入守护页查看实时画面。");
                setText("edgeHomeActionTitle", event ? "先查看事件，再联系家里" : "继续观察");
                setText("edgeHomeActionSub", event ? "确认安全后可以标记已处理；误报也要保留记录。" : "等检测摘要同步后，首页会自动更新。");
                setText("edgeHomeSnapshotTime", "等待检测摘要");
                setText("edgeHomeSnapshotRoom", camera.room || camera.name || "家里动态");
                setText("edgeHomeSnapshotHeadline", event ? event.summary : "实时画面已连接");
                setText("edgeHomeSnapshotSub", "后台正在生成最新证据截图");
                return;
            }

            const state = snapshotState(snapshot);
            const image = $("edgeHomeSnapshotImage");
            if (image && snapshot.image_url) {
                image.src = await GoHomeEdge.v1VideoMediaPlaybackUrl(snapshot.image_url);
                image.classList.remove("object-[center_38%]");
            }

            setText("edgeHomeTime", `${GoHomeEdge.fmtTime(snapshot.captured_at)} 更新 · ${camera.room || camera.name || "家里"} · ${device.detector_backend === "yolo" ? "视觉检测中" : "基础检测中"}`);
            setText("edgeHomeCameraState", enabled.length ? `${enabled.length} 路` : "未接入");
            setText("edgeHomeTitle", event ? event.summary : state.title);
            setText("edgeHomeSubtitle", event ? "本机服务已经生成一条待确认提醒，建议先去事件页查看截图和处理状态。" : state.subtitle);
            setText("edgeHomeFactTitle", event ? GoHomeEdge.eventLabel(event.type) : state.fact);
            setText("edgeHomeFactSub", event ? `${GoHomeEdge.fmtDateTime(event.occurred_at)} 触发，来自 ${event.camera_name || camera.name || "摄像头"}。` : state.factSub);
            setText("edgeHomeFeelingTitle", event ? "有一条提醒待确认" : state.feeling);
            setText("edgeHomeFeelingSub", event ? "这类信息应该进入告警处理流程，而不是只作为普通动态展示。" : state.feelingSub);
            setText("edgeHomeActionTitle", event ? "先查看事件，再联系家里" : state.action);
            setText("edgeHomeActionSub", event ? "确认安全后可以标记已处理；误报也要保留记录。" : state.actionSub);
            setText("edgeHomeSnapshotTime", `${GoHomeEdge.fmtTime(snapshot.captured_at)} 更新`);
            setText("edgeHomeSnapshotRoom", camera.room || camera.name || "家里动态");
            setText("edgeHomeSnapshotHeadline", event ? event.summary : state.snapshot);
            setText("edgeHomeSnapshotSub", `亮度 ${Number(snapshot.brightness || 0).toFixed(0)} · 人数 ${snapshot.person_count ?? "-"} · ${snapshot.tags?.length ? snapshot.tags.join(", ") : "无异常标签"}`);
        } catch (error) {
            if (error?.status === 401) {
                GoHomeEdge.clearAuthToken();
                fallbackGuestHome();
                return;
            }
            if (window.GoHomeAppStore?.hasVisibleState?.()) return;
            toggleSetupMode(true);
            toggleMessageSection(false);
            renderHomeSummary({
                user: { display_name: "本机服务" },
                family: { name: "连接失败" },
                device: {},
                enabled: [],
                liveEvents: [],
            });
            renderCareCardSummary(null, { name: "连接失败" });
            renderCareHistory([], { name: "连接失败" });
            renderLocationSummary(null, null);
            setSetupStates("未连接", "未连接", "待填写", "未连接", "离线");
            setText("edgeHomeDevice", "本机守护服务未连接");
            setText("edgeHomeTime", "等待家庭盒子服务");
            setText("edgeHomeBoxState", "离线");
            setText("edgeHomeCameraState", "未同步");
            setText("edgeHomeTitle", "主页面还没有连到本机守护服务");
            setText("edgeHomeSubtitle", error.message || "启动家庭盒子服务后，这里会自动切换成真实摄像头状态。");
            setAction("edgeHomePrimaryAction", "login.html", "去登录", "login");
            setAction("edgeHomeSecondaryAction", "family.html", "家庭空间", "groups");
            toggleSetupMode(true);
        } finally {
            lastRenderAt = Date.now();
            renderInFlight = false;
            window.GoHomeAppStore?.markPageReady?.();
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        renderDateRail();
        renderWeekCalendar();
        wireHomeFeedFilters();
        render();
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible" && Date.now() - lastRenderAt > 180000) {
                render();
            }
        });
        window.GoHomeRefreshHome = () => render();
        window.GoHomeRefreshPage = () => render();
    });
})();
