(function () {
    const $ = (id) => document.getElementById(id);
    const state = {
        family: null,
        busy: false,
        lastFeedback: "",
    };

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = String(value ?? "");
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

    function listText(items, fallback) {
        const values = Array.isArray(items) ? items.map((item) => labelText(item)).filter(Boolean) : [];
        return values.length ? values.join(" / ") : fallback;
    }

    function fmt(value) {
        return window.GoHomeEdge?.fmtDateTime?.(value) || "-";
    }

    function pageHref(path) {
        return window.GoHomeEdge?.pageHref?.(path) || path;
    }

    function setFeedback(message = "", tone = "info") {
        state.lastFeedback = String(message || "").trim();
        const node = $("notificationFeedback");
        if (!node) return;
        if (!state.lastFeedback) {
            node.classList.add("hidden");
            node.textContent = "";
            return;
        }
        node.textContent = state.lastFeedback;
        node.classList.remove("hidden");
        node.classList.toggle("bg-error-container", tone === "error");
        node.classList.toggle("text-on-error-container", tone === "error");
        node.classList.toggle("bg-primary-fixed", tone !== "error");
        node.classList.toggle("text-primary", tone !== "error");
    }

    function setBusy(busy) {
        state.busy = busy;
        ["notificationGenerateButton", "notificationPushTestButton", "notificationRefreshButton"].forEach((id) => {
            const button = $(id);
            if (button) {
                button.disabled = busy;
                button.classList.toggle("opacity-60", busy);
            }
        });
    }

    function messageBadge(type) {
        const value = String(type || "").trim();
        if (value === "alert") return { label: "告警", icon: "notifications_active", tone: "warn" };
        if (value === "care_card") return { label: "关怀", icon: "volunteer_activism", tone: "good" };
        if (value === "test") return { label: "测试", icon: "science", tone: "muted" };
        if (value === "gohome") return { label: "回家", icon: "home", tone: "good" };
        if (value === "explain") return { label: "解释", icon: "visibility", tone: "muted" };
        return { label: "消息", icon: "favorite", tone: "muted" };
    }

    function deliveryStatus(delivery) {
        const value = String(delivery?.status || "").trim();
        const map = {
            app_message_only: { label: "站内已记录", tone: "good", text: "当前没有 iOS token，消息已进入 App 内消息列表。" },
            simulated: { label: "模拟送达", tone: "good", text: "已登记 token，但 APNs provider 尚未配置，先记录模拟送达。" },
            queued: { label: "已入队", tone: "good", text: "已进入推送队列，等待 provider 发送。" },
            sent: { label: "已发送", tone: "good", text: "推送请求已发送。" },
            delivered: { label: "已送达", tone: "good", text: "推送已确认送达。" },
            failed: { label: "失败", tone: "warn", text: delivery?.error_message || "投递失败，请检查 provider 或 token。" },
        };
        return map[value] || { label: value || "未知", tone: "muted", text: delivery?.error_message || "等待通知服务更新状态。" };
    }

    function statusClass(tone) {
        if (tone === "warn") return "gohome-status-tag warn";
        if (tone === "good") return "gohome-status-tag";
        return "gohome-status-tag muted";
    }

    function emptyCard(icon, title, body, action) {
        const article = document.createElement("article");
        article.className = "gohome-simple-card";
        const iconNode = document.createElement("span");
        iconNode.className = "material-symbols-outlined";
        iconNode.textContent = icon;
        const copy = document.createElement("div");
        const heading = document.createElement("h3");
        heading.textContent = title;
        const text = document.createElement("p");
        text.textContent = body;
        copy.append(heading, text);
        article.append(iconNode, copy);
        if (action) article.append(action);
        return article;
    }

    function renderMessageList(messages) {
        const list = $("notificationMessageList");
        if (!list) return;
        list.innerHTML = "";
        if (!messages.length) {
            const link = document.createElement("a");
            link.className = "gohome-status-tag";
            link.href = pageHref("care_schedule.html");
            link.textContent = "去设置";
            list.append(emptyCard("inbox", "还没有消息", "关怀任务运行后，这里会出现每日关怀和测试通知。", link));
            return;
        }
        messages.slice(0, 6).forEach((message) => {
            const badge = messageBadge(message.message_type);
            const article = document.createElement("article");
            article.className = "gohome-simple-card";
            const icon = document.createElement("span");
            icon.className = "material-symbols-outlined";
            icon.textContent = badge.icon;
            const copy = document.createElement("div");
            const title = document.createElement("h3");
            title.textContent = message.title || "一条新的提醒";
            const body = document.createElement("p");
            body.textContent = [
                message.subtitle || message.body || "这条消息没有补充正文。",
                listText(message.facts, ""),
                fmt(message.created_at),
            ].filter(Boolean).join(" · ");
            const meta = document.createElement("p");
            meta.textContent = listText(message.actions, "暂无建议动作");
            copy.append(title, body, meta);
            const tag = document.createElement("span");
            tag.className = statusClass(badge.tone);
            tag.textContent = badge.label;
            article.append(icon, copy, tag);
            list.append(article);
        });
    }

    function renderDeliveryList(deliveries) {
        const list = $("notificationDeliveryList");
        if (!list) return;
        list.innerHTML = "";
        if (!deliveries.length) {
            list.append(emptyCard("local_post_office", "暂无投递记录", "点击测试通知或等待定时关怀任务运行后，会写入投递记录。"));
            return;
        }
        deliveries.slice(0, 8).forEach((delivery) => {
            const status = deliveryStatus(delivery);
            const article = document.createElement("article");
            article.className = "gohome-simple-card";
            const icon = document.createElement("span");
            icon.className = "material-symbols-outlined";
            icon.textContent = delivery.channel === "app_push" ? "mobile_friendly" : "notifications";
            const copy = document.createElement("div");
            const title = document.createElement("h3");
            title.textContent = delivery.title || "通知投递";
            const body = document.createElement("p");
            body.textContent = `${status.text} · ${delivery.provider || "app_message"} · ${fmt(delivery.created_at)}`;
            const meta = document.createElement("p");
            meta.textContent = delivery.message_id ? `消息 ${delivery.message_id}` : "没有关联消息 ID";
            copy.append(title, body, meta);
            const tag = document.createElement("span");
            tag.className = statusClass(status.tone);
            tag.textContent = status.label;
            article.append(icon, copy, tag);
            list.append(article);
        });
    }

    function renderTokens(tokens) {
        const count = tokens.length;
        setText("notificationTokenCount", count);
        setText("notificationPushTokenBadge", count ? "已登记" : "未登记");
        $("notificationPushTokenBadge")?.classList.toggle("muted", !count);
        if (count) {
            const names = tokens.map((token) => token.device_name || token.platform || token.token_preview).filter(Boolean);
            setText("notificationPushTokenText", `${count} 台设备已登记推送 token：${names.slice(0, 2).join("、") || "iOS App"}`);
        } else {
            setText("notificationPushTokenText", "当前网页无法获取 APNs token；真机 iOS App 登录后会自动登记。");
        }
    }

    function renderSummary({ family, messages, deliveries, tokens }) {
        const openMessages = messages.filter((message) => String(message.status || "open") === "open");
        const lastDelivery = deliveries[0] || null;
        const lastStatus = deliveryStatus(lastDelivery);
        setText("notificationFamilyLine", family ? `${family.name || "当前家庭"} · 通知设置` : "通知设置");
        setText("notificationOpenCount", openMessages.length);
        setText("notificationDeliveryCount", deliveries.length);
        if (family) {
            setText("notificationSummaryTitle", "提醒渠道");
            setText("notificationSummaryText", `当前家庭已接入站内消息；最近 ${messages.length} 条消息、${deliveries.length} 条投递记录。`);
        }
        setText("notificationDeliveryTitle", lastDelivery ? `最近一次：${lastStatus.label}` : "等待第一条通知");
        setText("notificationDeliveryText", lastDelivery ? lastStatus.text : "关怀任务或测试通知运行后，会在这里看到真实投递状态。");
        const badge = $("notificationDeliveryBadge");
        if (badge) {
            badge.textContent = lastDelivery ? lastStatus.label : "未投递";
            badge.className = statusClass(lastDelivery ? lastStatus.tone : "muted");
        }
        setText("notificationSafetyText", "家庭盒子产生的安全事件会进入事件页；高优先级事件也会进入站内消息。");
        setText("notificationCareText", "每日关怀卡片由定时任务生成，首页和陪伴页读取同一条 App 消息。");
        setText("notificationInAppText", tokens.length ? "站内消息和 iOS token 均有记录，APNs provider 接入后可进入真实推送。" : "站内消息已是当前可验证闭环；iOS 真机 token 尚未登记。");
        setText("notificationMessageMeta", `${openMessages.length} 条打开中，${messages.length} 条最近消息`);
        setText("notificationDeliveryMeta", lastDelivery ? `最近更新 ${fmt(lastDelivery.updated_at || lastDelivery.created_at)}` : "暂无投递记录");
        renderTokens(tokens);
    }

    function showUnauthed(message) {
        setText("notificationSummaryTitle", "请先登录");
        setText("notificationSummaryText", message || "登录后才能读取家庭通知状态。");
        setText("notificationDeliveryTitle", "未连接账号");
        setText("notificationDeliveryText", "先完成手机号登录，再返回查看通知链路。");
        setText("notificationOpenCount", "-");
        setText("notificationDeliveryCount", "-");
        setText("notificationTokenCount", "-");
        const list = $("notificationMessageList");
        if (list) {
            const link = document.createElement("a");
            link.className = "gohome-status-tag";
            link.href = pageHref("login.html");
            link.textContent = "去登录";
            list.innerHTML = "";
            list.append(emptyCard("login", "账号未登录", "登录后会读取当前家庭的关怀消息和通知记录。", link));
        }
        renderDeliveryList([]);
    }

    async function resolveFamily() {
        if (!window.GoHomeEdge) return null;
        window.GoHomeEdge.bootstrapLaunchState?.();
        await window.GoHomeEdge.connect();
        if (!window.GoHomeEdge.isAuthenticated()) return null;
        await window.GoHomeEdge.currentUser();
        const families = await window.GoHomeEdge.myFamilies();
        return families[0] || null;
    }

    async function loadData() {
        const family = await resolveFamily();
        if (!family) {
            state.family = null;
            showUnauthed("当前没有可用家庭。先完成登录、老人资料和盒子绑定。");
            return;
        }
        state.family = family;
        const query = new URLSearchParams({ family_id: String(family.id), limit: "20" }).toString();
        const [messagesResult, deliveriesResult, tokensResult] = await Promise.allSettled([
            window.GoHomeEdge.v1AppMessages({ family_id: family.id, limit: 20, status: "all" }),
            window.GoHomeEdge.v1NotificationDeliveries(query),
            window.GoHomeEdge.v1AppPushTokens(family.id),
        ]);
        const messages = messagesResult.status === "fulfilled" && Array.isArray(messagesResult.value) ? messagesResult.value : [];
        const deliveries = deliveriesResult.status === "fulfilled" && Array.isArray(deliveriesResult.value) ? deliveriesResult.value : [];
        const tokens = tokensResult.status === "fulfilled" && Array.isArray(tokensResult.value) ? tokensResult.value : [];
        renderSummary({ family, messages, deliveries, tokens });
        renderMessageList(messages);
        renderDeliveryList(deliveries);
        if (messagesResult.status === "rejected" || deliveriesResult.status === "rejected" || tokensResult.status === "rejected") {
            setFeedback("部分通知数据读取失败，已显示能读取到的内容。", "error");
        } else {
            setFeedback(state.lastFeedback);
        }
    }

    async function runTest(kind) {
        if (state.busy) return;
        setBusy(true);
        setFeedback(kind === "push" ? "正在写入推送链路测试..." : "正在生成测试通知...");
        try {
            const family = state.family || await resolveFamily();
            if (!family) throw new Error("请先完成登录和家庭配置");
            if (kind === "push") {
                await window.GoHomeEdge.v1AppPushTest({ family_id: family.id });
                setFeedback("推送链路测试已写入。没有 iOS token 时会记录为站内消息。");
            } else {
                await window.GoHomeEdge.v1NotificationTest({ family_id: family.id });
                setFeedback("测试通知已生成，最近消息和投递记录已刷新。");
            }
            await loadData();
        } catch (error) {
            setFeedback(error.message || "通知测试失败", "error");
        } finally {
            setBusy(false);
        }
    }

    function bind() {
        $("notificationRefreshButton")?.addEventListener("click", () => {
            if (!state.busy) loadData();
        });
        $("notificationGenerateButton")?.addEventListener("click", () => runTest("notification"));
        $("notificationPushTestButton")?.addEventListener("click", () => runTest("push"));
    }

    document.addEventListener("DOMContentLoaded", () => {
        bind();
        loadData().catch((error) => {
            showUnauthed(error.status === 401 ? "登录已失效，请重新登录。" : (error.message || "通知服务暂时不可用。"));
        });
    });
})();
