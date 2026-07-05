(function () {
    const $ = (id) => document.getElementById(id);

    const state = {
        user: null,
        families: [],
        busy: false,
    };

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function setFeedback(message, tone = "neutral") {
        const node = $("familyFeedback");
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

    function setBusy(busy) {
        state.busy = busy;
        const button = $("familyCreateBtn");
        if (!button) return;
        button.disabled = busy;
        button.classList.toggle("opacity-70", busy);
        button.textContent = busy ? "创建中..." : "创建家庭";
    }

    function redirectLogin() {
        const target = window.GoHomeEdge?.loginHref?.(window.GoHomeEdge?.currentPagePath?.() || "family.html") || "login.html";
        window.location.href = target;
    }

    function deviceBindingHref(familyId = "") {
        const suffix = familyId ? `?family_id=${encodeURIComponent(familyId)}` : "";
        return window.GoHomeEdge?.pageHref?.(`device_binding.html${suffix}`) || `device_binding.html${suffix}`;
    }

    function requestedFamilyId() {
        return String(new URLSearchParams(window.location.search).get("family_id") || "").trim();
    }

    function syncSelectedFamilyParam(familyId = "") {
        const url = new URL(window.location.href);
        if (familyId) {
            url.searchParams.set("family_id", String(familyId));
        } else {
            url.searchParams.delete("family_id");
        }
        window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    }

    function preferredFamily() {
        const requested = requestedFamilyId();
        if (requested) {
            const matched = state.families.find((family) => String(family.id) === requested);
            if (matched) return matched;
        }
        return state.families[0] || null;
    }

    function syncBindingLinks() {
        const family = preferredFamily();
        syncSelectedFamilyParam(family?.id || "");
        const href = deviceBindingHref(family?.id || "");
        ["familyPrimaryBindingLink", "familyListBindingLink", "familyNavBindingLink"].forEach((id) => {
            const node = $(id);
            if (node) node.href = href;
        });
        const selfLink = $("familyNavSelfLink");
        if (selfLink) selfLink.href = window.GoHomeEdge?.pageHref?.(`family.html${family?.id ? `?family_id=${encodeURIComponent(family.id)}` : ""}`) || `family.html${family?.id ? `?family_id=${encodeURIComponent(family.id)}` : ""}`;
    }

    function renderFamilies() {
        const list = $("familyList");
        if (!list) return;
        setText("familyCount", String(state.families.length));
        setText("familyNextStep", state.families.length ? "绑设备" : "先创建");
        syncBindingLinks();

        if (!state.families.length) {
            list.innerHTML = `
                <div class="app-soft-card bg-white p-5 text-center">
                    <p class="font-display text-[16px] font-bold text-on-surface">还没有家庭</p>
                </div>
            `;
            return;
        }

        list.innerHTML = state.families.map((family) => `
            <article class="app-soft-card bg-white p-4 flex items-center justify-between gap-3">
                <div class="min-w-0">
                    <p class="font-display text-[16px] font-bold text-on-surface">${family.name}</p>
                    <p class="font-sans text-[12px] text-on-surface-variant mt-1">${family.member_count || 1} 人</p>
                </div>
                <a href="${deviceBindingHref(family.id)}" class="h-11 px-4 rounded-2xl bg-[#f4f6fb] text-on-surface font-sans text-[12px] font-bold flex items-center justify-center">绑定设备</a>
            </article>
        `).join("");
    }

    async function loadData() {
        const [user, families] = await Promise.all([
            GoHomeEdge.currentUser(),
            GoHomeEdge.myFamilies(),
        ]);
        state.user = user;
        state.families = families;
        setText("familyUserName", user.display_name || "家庭空间");
        setText("familyStatusText", user.email || "");
        renderFamilies();
    }

    async function createFamily(event) {
        event.preventDefault();
        if (state.busy) return;
        const name = $("familyNameInput")?.value.trim() || "";
        if (!name) {
            setFeedback("先填家庭名称。", "error");
            return;
        }
        try {
            setBusy(true);
            setFeedback("");
            const family = await GoHomeEdge.createFamily({ name });
            $("familyNameInput").value = "";
            await loadData();
            setFeedback("已创建，正在进入绑定设备。", "success");
            setTimeout(() => {
                window.location.href = deviceBindingHref(family?.id || "");
            }, 260);
        } catch (error) {
            setFeedback(error.message || "创建失败。", "error");
        } finally {
            setBusy(false);
        }
    }

    async function bootstrap() {
        if (!window.GoHomeEdge) return;
        if (!GoHomeEdge.isAuthenticated()) {
            redirectLogin();
            return;
        }
        try {
            await GoHomeEdge.connect();
            await loadData();
        } catch (_error) {
            GoHomeEdge.clearAuthToken();
            redirectLogin();
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        $("familyCreateForm")?.addEventListener("submit", createFamily);
        $("familyLogoutBtn")?.addEventListener("click", () => {
            GoHomeEdge.clearAuthToken();
            redirectLogin();
        });
        bootstrap();
    });
})();
