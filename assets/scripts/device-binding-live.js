(function () {
    const $ = (id) => document.getElementById(id);

    const state = {
        families: [],
        device: null,
        bindings: [],
        bindingCodes: [],
        claimable: [],
        authStatus: null,
        busy: false,
        tokenBusy: false,
    };

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function setFeedback(message, tone = "neutral") {
        const node = $("bindingFeedback");
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

    function setTokenFeedback(message, tone = "neutral") {
        const node = $("bindingTokenFeedback");
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
        const button = $("bindingSubmitBtn");
        if (!button) return;
        button.disabled = busy;
        button.classList.toggle("opacity-70", busy);
        const bound = hasActiveBinding();
        const icon = bound ? "nest_cam_indoor" : "link";
        const label = busy ? (bound ? "进入中..." : "绑定中...") : (bound ? "继续配置摄像头" : "绑定盒子");
        button.innerHTML = `<span class="material-symbols-outlined text-[20px]">${icon}</span>${label}`;
    }

    function setTokenBusy(id, busy, busyText, idleText) {
        const button = $(id);
        if (!button) return;
        button.disabled = busy;
        button.classList.toggle("opacity-70", busy);
        button.textContent = busy ? busyText : idleText;
    }

    function redirectLogin() {
        const target = window.GoHomeEdge?.loginHref?.(window.GoHomeEdge?.currentPagePath?.() || "device_binding.html") || "login.html";
        window.location.href = target;
    }

    function connectHref() {
        const family = selectedFamily();
        const suffix = family?.id ? `?family_id=${encodeURIComponent(family.id)}` : "";
        return window.GoHomeEdge?.pageHref?.(`connect.html${suffix}`) || `connect.html${suffix}`;
    }

    function familyHref(familyId = "") {
        const suffix = familyId ? `?family_id=${encodeURIComponent(familyId)}` : "";
        return window.GoHomeEdge?.pageHref?.(`family.html${suffix}`) || `family.html${suffix}`;
    }

    function selfHref(familyId = "") {
        const suffix = familyId ? `?family_id=${encodeURIComponent(familyId)}` : "";
        return window.GoHomeEdge?.pageHref?.(`device_binding.html${suffix}`) || `device_binding.html${suffix}`;
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

    function syncFamilyLinks(familyId = "") {
        const backLink = $("bindingBackLink");
        const emptyFamilyLink = $("bindingEmptyFamilyLink");
        const navFamilyLink = $("bindingNavFamilyLink");
        const navSelfLink = $("bindingNavSelfLink");
        const familyTarget = familyHref(familyId);
        const selfTarget = selfHref(familyId);
        if (backLink) backLink.href = familyTarget;
        if (emptyFamilyLink) emptyFamilyLink.href = familyTarget;
        if (navFamilyLink) navFamilyLink.href = familyTarget;
        if (navSelfLink) navSelfLink.href = selfTarget;
    }

    function preferredFamilyId() {
        const params = new URLSearchParams(window.location.search);
        const familyId = Number(params.get("family_id"));
        if (familyId && state.families.some((family) => Number(family.id) === familyId)) {
            return familyId;
        }
        return state.families[0]?.id || "";
    }

    function renderFamilyOptions() {
        const select = $("bindingFamilySelect");
        if (!select) return;
        select.innerHTML = state.families.map((family) => `<option value="${family.id}">${family.name}</option>`).join("");
        select.value = String(preferredFamilyId());
        syncSelectedFamilyParam(select.value || "");
        syncFamilyLinks(select.value || "");
    }

    function selectedFamily() {
        const familyId = Number($("bindingFamilySelect")?.value || preferredFamilyId());
        return state.families.find((family) => Number(family.id) === familyId) || null;
    }

    function activeBindings() {
        return state.bindings.filter((binding) => String(binding.status || "active") !== "revoked");
    }

    function hasActiveBinding() {
        return activeBindings().length > 0;
    }

    function syncPrimaryAction() {
        const button = $("bindingSubmitBtn");
        if (!button) return;
        const bound = hasActiveBinding();
        button.dataset.mode = bound ? "continue" : "bind";
        button.innerHTML = bound
            ? `<span class="material-symbols-outlined text-[20px]">nest_cam_indoor</span>继续配置摄像头`
            : `<span class="material-symbols-outlined text-[20px]">link</span>绑定盒子`;
        const claimInput = $("bindingClaimInput");
        if (claimInput) {
            claimInput.required = !bound;
            claimInput.placeholder = bound ? "已绑定，可直接继续" : "输入二维码内容、序列号或绑定码";
        }
    }

    function renderTokenCard() {
        const activeCode = state.bindingCodes.find((item) => item.status === "active") || state.bindingCodes[0] || null;
        const token = state.authStatus?.token || null;
        setText("bindingCodeText", activeCode?.code || "-");
        setText("bindingHeartbeatText", token?.last_heartbeat_at ? GoHomeEdge.fmtDateTime(token.last_heartbeat_at) : "未发送");
        setText("bindingTokenBadge", token ? "已激活" : "未激活");
    }

    function renderBindings() {
        const list = $("bindingList");
        if (!list) return;
        const bindings = activeBindings();
        setText("bindingListBadge", `${bindings.length} 台`);
        if (!bindings.length) {
            list.innerHTML = `
                <div class="app-soft-card bg-white p-5 text-center">
                    <p class="font-display text-[16px] font-bold text-on-surface">还没有绑定设备</p>
                </div>
            `;
            return;
        }
        list.innerHTML = bindings.map((binding) => `
            <article class="app-soft-card bg-white p-4">
                <div class="flex items-center justify-between gap-3">
                    <div class="min-w-0">
                        <p class="font-display text-[16px] font-bold text-on-surface">${binding.device_name || "设备"}</p>
                        <p class="font-sans text-[12px] text-on-surface-variant mt-1 break-all">${binding.device_id}</p>
                    </div>
                    <span class="px-2.5 py-1 rounded-full bg-[#edf6ee] text-[#2d7d5c] text-[10px] font-bold shrink-0">已绑定</span>
                </div>
                <div class="mt-3 grid grid-cols-[1fr_auto] gap-2">
                    <a class="h-10 rounded-2xl bg-primary text-on-primary font-sans text-[12px] font-bold flex items-center justify-center gap-2" href="${connectHref()}">
                        <span class="material-symbols-outlined text-[18px]">nest_cam_indoor</span>
                        配置摄像头
                    </a>
                    <button type="button" class="binding-unbind-button h-10 rounded-2xl bg-[#f8ece9] px-4 font-sans text-[12px] font-bold text-[#9a4e43] flex items-center justify-center gap-1" data-binding-id="${binding.id}" data-device-name="${binding.device_name || "回家盒子"}">
                        <span class="material-symbols-outlined text-[18px]">link_off</span>
                        解绑
                    </button>
                </div>
            </article>
        `).join("");
        list.querySelectorAll(".binding-unbind-button").forEach((button) => {
            button.addEventListener("click", async () => {
                const bindingId = button.getAttribute("data-binding-id") || "";
                const deviceName = button.getAttribute("data-device-name") || "这台盒子";
                const confirmed = window.confirm(`确认解除“${deviceName}”的家庭绑定吗？\n\n盒子不会掉网，但这个家庭下的摄像头接入配置会被移除。之后可用盒身码重新绑定。`);
                if (!confirmed || !bindingId) return;
                const oldHtml = button.innerHTML;
                try {
                    button.disabled = true;
                    button.classList.add("opacity-60");
                    button.innerHTML = `<span class="material-symbols-outlined text-[18px]">progress_activity</span>解绑中`;
                    setFeedback("正在解除家庭绑定，盒子会保持联网。", "neutral");
                    const result = await GoHomeEdge.unbindDevice(bindingId);
                    await loadData();
                    setFeedback(`已解除绑定，并移除 ${Number(result.removed_camera_count || 0)} 路摄像头配置。盒子现在可以重新认领。`, "success");
                } catch (error) {
                    setFeedback(error.message || "解绑失败。", "error");
                    button.disabled = false;
                    button.classList.remove("opacity-60");
                    button.innerHTML = oldHtml;
                }
            });
        });
    }

    function renderClaimableDevices() {
        const list = $("bindingClaimableList");
        if (!list) return;
        if (!state.claimable.length) {
            list.innerHTML = `
                <div class="rounded-2xl bg-surface-container-low px-4 py-3">
                    <p class="font-sans text-[12px] leading-5 text-on-surface-variant">暂未发现可认领盒子。确认盒子已通电联网后，再输入盒身码绑定。</p>
                </div>
            `;
            return;
        }
        list.innerHTML = state.claimable.map((device) => `
            <button type="button" class="binding-claimable-row w-full rounded-2xl bg-surface-container-low px-4 py-3 text-left" data-serial="${device.serial_number || ""}">
                <div class="flex items-center justify-between gap-3">
                    <div class="min-w-0">
                        <p class="font-sans text-[13px] font-bold text-on-surface">${device.name || "回家盒子"}</p>
                        <p class="mt-1 break-all font-sans text-[12px] text-on-surface-variant">${device.serial_number || device.device_id || "待生成序列号"}</p>
                    </div>
                    <span class="rounded-full bg-[#edf6ee] px-2.5 py-1 font-sans text-[10px] font-bold text-[#2d7d5c]">在线</span>
                </div>
            </button>
        `).join("");
        list.querySelectorAll(".binding-claimable-row").forEach((button) => {
            button.addEventListener("click", () => {
                const serial = button.getAttribute("data-serial") || "";
                if ($("bindingClaimInput") && serial) $("bindingClaimInput").value = serial;
                setFeedback("已填入发现的盒子序列号，请确认后绑定。");
            });
        });
    }

    async function loadBindings() {
        const familyId = Number($("bindingFamilySelect")?.value || preferredFamilyId());
        if (!familyId) {
            state.bindings = [];
            renderBindings();
            state.bindingCodes = [];
            renderTokenCard();
            return;
        }
        state.bindings = await GoHomeEdge.deviceBindings(familyId);
        const currentBound = hasActiveBinding();
        setText("bindingStateText", currentBound ? "已绑定" : "待绑定");
        state.bindingCodes = await GoHomeEdge.deviceBindingCodes(familyId);
        renderBindings();
        renderTokenCard();
        syncPrimaryAction();
        if (currentBound) {
            setFeedback("这个家庭已经绑定盒子，可以继续配置摄像头。", "success");
        } else {
            setFeedback("");
        }
    }

    async function loadData() {
        const [families, device, claimable] = await Promise.all([
            GoHomeEdge.myFamilies(),
            GoHomeEdge.device(),
            GoHomeEdge.claimableDevices ? GoHomeEdge.claimableDevices().catch(() => []) : Promise.resolve([]),
        ]);
        state.families = families;
        state.device = device;
        state.claimable = Array.isArray(claimable) ? claimable : [];
        state.authStatus = await GoHomeEdge.deviceAuthStatus().catch(() => null);
        setText("bindingDeviceText", device.device_id || "");
        setText("bindingDeviceName", device.device_name || "本机设备");
        const hasFamilies = families.length > 0;
        $("bindingFormSection")?.classList.toggle("hidden", !hasFamilies);
        $("bindingEmptySection")?.classList.toggle("hidden", hasFamilies);
        if (!hasFamilies) {
            state.bindings = [];
            setText("bindingStateText", "待创建");
            syncSelectedFamilyParam("");
            syncFamilyLinks("");
            renderBindings();
            renderClaimableDevices();
            return;
        }
        renderFamilyOptions();
        await loadBindings();
        renderClaimableDevices();
    }

    async function bindCurrentDevice(event) {
        event.preventDefault();
        if (state.busy) return;
        const familyId = Number($("bindingFamilySelect")?.value || 0);
        if (!familyId) {
            setFeedback("先选家庭。", "error");
            return;
        }
        if (hasActiveBinding()) {
            setFeedback("盒子已绑定，正在进入摄像头配置。", "success");
            setTimeout(() => {
                window.location.href = connectHref();
            }, 160);
            return;
        }
        const claimCode = $("bindingClaimInput")?.value.trim() || "";
        if (!claimCode) {
            setFeedback("请输入盒身二维码内容、序列号或绑定码。", "error");
            return;
        }
        try {
            setBusy(true);
            setFeedback("");
            await GoHomeEdge.claimDevice({
                family_id: familyId,
                claim_code: claimCode,
                device_name: state.device?.device_name || "回家盒子",
                note: $("bindingNoteInput")?.value.trim() || "",
            });
            $("bindingNoteInput").value = "";
            $("bindingClaimInput").value = "";
            await loadBindings();
            setFeedback("已绑定，正在进入摄像头接入。", "success");
            setTimeout(() => {
                window.location.href = connectHref();
            }, 260);
        } catch (error) {
            setFeedback(error.message || "绑定失败。", "error");
        } finally {
            setBusy(false);
        }
    }

    async function createBindingCode() {
        const family = selectedFamily();
        if (!family) {
            setTokenFeedback("先选家庭。", "error");
            return;
        }
        try {
            setTokenBusy("bindingCodeBtn", true, "生成中...", "生成绑定码");
            setTokenFeedback("");
            await GoHomeEdge.createDeviceBindingCode({
                family_id: family.id,
                expires_in_minutes: 10,
                note: $("bindingNoteInput")?.value.trim() || "",
            });
            await loadBindings();
            setTokenFeedback("已生成。", "success");
        } catch (error) {
            setTokenFeedback(error.message || "生成失败。", "error");
        } finally {
            setTokenBusy("bindingCodeBtn", false, "生成中...", "生成绑定码");
        }
    }

    async function activateCurrentDevice() {
        const activeCode = state.bindingCodes.find((item) => item.status === "active");
        if (!activeCode) {
            setTokenFeedback("先生成绑定码。", "error");
            return;
        }
        try {
            setTokenBusy("bindingActivateBtn", true, "激活中...", "激活当前设备");
            setTokenFeedback("");
            await GoHomeEdge.exchangeDeviceToken({
                code: activeCode.code,
                note: $("bindingNoteInput")?.value.trim() || "",
            });
            state.authStatus = await GoHomeEdge.deviceAuthStatus();
            renderTokenCard();
            setTokenFeedback("已激活。", "success");
        } catch (error) {
            setTokenFeedback(error.message || "激活失败。", "error");
        } finally {
            setTokenBusy("bindingActivateBtn", false, "激活中...", "激活当前设备");
        }
    }

    async function sendHeartbeat() {
        try {
            setTokenBusy("bindingHeartbeatBtn", true, "发送中...", "发送一次心跳");
            setTokenFeedback("");
            await GoHomeEdge.deviceHeartbeatSelf({
                status: "online",
                lan_ip: state.device?.lan_ip || "",
                api_port: state.device?.api_port || null,
            });
            state.authStatus = await GoHomeEdge.deviceAuthStatus();
            renderTokenCard();
            setTokenFeedback("已发送。", "success");
        } catch (error) {
            setTokenFeedback(error.message || "发送失败。", "error");
        } finally {
            setTokenBusy("bindingHeartbeatBtn", false, "发送中...", "发送一次心跳");
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
            await GoHomeEdge.currentUser();
            await loadData();
        } catch (_error) {
            GoHomeEdge.clearAuthToken();
            redirectLogin();
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        $("bindingForm")?.addEventListener("submit", bindCurrentDevice);
        $("bindingFamilySelect")?.addEventListener("change", () => {
            const familyId = $("bindingFamilySelect")?.value || "";
            syncSelectedFamilyParam(familyId);
            syncFamilyLinks(familyId);
            loadBindings().catch((error) => setFeedback(error.message || "读取失败。", "error"));
        });
        $("bindingCodeBtn")?.addEventListener("click", () => {
            createBindingCode();
        });
        $("bindingActivateBtn")?.addEventListener("click", () => {
            activateCurrentDevice();
        });
        $("bindingHeartbeatBtn")?.addEventListener("click", () => {
            sendHeartbeat();
        });
        bootstrap();
    });
})();
