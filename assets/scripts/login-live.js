(function () {
    const $ = (id) => document.getElementById(id);

    const state = {
        mode: "login",
        busy: false,
    };

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function setMode(mode) {
        state.mode = mode;
        $("authLoginTab")?.classList.toggle("active", mode === "login");
        $("authRegisterTab")?.classList.toggle("active", mode === "register");
        $("authLoginTab")?.classList.toggle("text-on-surface", mode === "login");
        $("authRegisterTab")?.classList.toggle("text-on-surface", mode === "register");
        $("authLoginTab")?.classList.toggle("text-on-surface-variant", mode !== "login");
        $("authRegisterTab")?.classList.toggle("text-on-surface-variant", mode !== "register");
        $("authDisplayNameGroup")?.classList.toggle("hidden", mode !== "register");
        $("authPassword")?.setAttribute("autocomplete", mode === "login" ? "current-password" : "new-password");
        setText("authSubmitBtn", mode === "login" ? "立即登录" : "创建并登录");
        setFeedback("");
    }

    function setBusy(busy) {
        state.busy = busy;
        const submit = $("authSubmitBtn");
        if (!submit) return;
        submit.disabled = busy;
        submit.classList.toggle("opacity-70", busy);
        submit.textContent = busy
            ? (state.mode === "login" ? "正在登录..." : "正在创建...")
            : (state.mode === "login" ? "立即登录" : "创建并登录");
    }

    function setFeedback(message, tone = "neutral") {
        const node = $("authFeedback");
        if (!node) return;
        node.textContent = message || "";
        node.className = "min-h-[20px] font-sans text-[12px] leading-5";
        if (tone === "error") {
            node.classList.add("text-[#b25d4f]");
        } else if (tone === "success") {
            node.classList.add("text-[#2d7d5c]");
        } else {
            node.classList.add("text-on-surface-variant");
        }
    }

    function toggleLoggedInCard(visible, user) {
        $("authLoggedInCard")?.classList.toggle("hidden", !visible);
        $("authForm")?.classList.toggle("hidden", visible);
        if (visible && user) {
            setText("authLoggedInTitle", `${user.display_name || "家属"}`);
            setText("authLoggedInSub", user.phone || "");
        }
    }

    function redirectHome() {
        const target = window.GoHomeEdge?.redirectTarget?.("index.html") || "index.html";
        window.location.href = window.GoHomeEdge?.pageHref?.(target, { clearNext: true }) || target;
    }

    function refreshLoggedInActionLabel() {
        const target = window.GoHomeEdge?.redirectTarget?.("index.html") || "index.html";
        setText("authGoHomeBtn", target === "app-shell.html" ? "进入 App" : "进入首页");
    }

    async function ensureSessionView() {
        if (!window.GoHomeEdge?.isAuthenticated()) return false;
        try {
            const user = await GoHomeEdge.currentUser();
            toggleLoggedInCard(true, user);
            setFeedback("");
            return true;
        } catch (_error) {
            GoHomeEdge.clearAuthToken();
            toggleLoggedInCard(false);
            return false;
        }
    }

    function readForm() {
        return {
            display_name: $("authDisplayName")?.value.trim() || "",
            phone: ($("authPhone") || $("phone") || $("authEmail"))?.value.trim() || "",
            code: ($("authCode") || $("code") || $("authPassword"))?.value || "",
        };
    }

    function validateForm(payload) {
        if (state.mode === "register" && !payload.display_name) {
            return "请先填写你的称呼。";
        }
        if (!/^\d{11}$/.test(String(payload.phone || "").replace(/\D/g, ""))) return "请先填写 11 位手机号。";
        if (!payload.code || payload.code.length < 6) return "验证码至少需要 6 位。";
        return "";
    }

    async function submitForm(event) {
        event.preventDefault();
        if (state.busy || !window.GoHomeEdge) return;
        const payload = readForm();
        const errorMessage = validateForm(payload);
        if (errorMessage) {
            setFeedback(errorMessage, "error");
            return;
        }

        try {
            setBusy(true);
            setFeedback(state.mode === "login" ? "正在验证账号..." : "正在创建账号...", "neutral");
            if (state.mode === "login") {
                await GoHomeEdge.login({ phone: payload.phone, code: payload.code });
            } else {
                await GoHomeEdge.register(payload);
            }
            setFeedback("登录成功，正在进入首页...", "success");
            setTimeout(redirectHome, 280);
        } catch (error) {
            setFeedback(error.message || "登录失败，请稍后再试。", "error");
        } finally {
            setBusy(false);
        }
    }

    async function bootstrap() {
        if (!window.GoHomeEdge) return;
        try {
            GoHomeEdge.bootstrapLaunchState?.();
            await GoHomeEdge.connect();
            setText("authServiceStatus", "守护服务已连接");
            await ensureSessionView();
            refreshLoggedInActionLabel();
        } catch (error) {
            setText("authServiceStatus", "守护服务未连接");
            setFeedback(error.message || "本机守护服务未连接，请先启动家庭盒子服务。", "error");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        $("authLoginTab")?.addEventListener("click", () => {
            toggleLoggedInCard(false);
            setMode("login");
        });
        $("authRegisterTab")?.addEventListener("click", () => {
            toggleLoggedInCard(false);
            setMode("register");
        });
        $("authForm")?.addEventListener("submit", submitForm);
        $("authGoHomeBtn")?.addEventListener("click", redirectHome);
        $("authLogoutBtn")?.addEventListener("click", async () => {
            GoHomeEdge.clearAuthToken();
            toggleLoggedInCard(false);
            setMode("login");
            setFeedback("");
        });
        setMode("login");
        refreshLoggedInActionLabel();
        bootstrap();
    });
})();
