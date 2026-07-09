(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const page = () => window.location.pathname.split("/").pop() || "index.html";
  const text = (value) => String(value || "").replace(/\s+/g, "").trim();

  const state = {
    connected: false,
    families: [],
    editingCamera: null,
  };

  const mainTabPages = new Set([
    "index.html",
    "monitor.html",
    "events.html",
    "companionship.html",
    "privacy.html",
  ]);

  const shellPages = new Set([
    ...mainTabPages,
    "rules.html",
    "cameras.html",
    "family_members.html",
  ]);

  function pageSlug(name) {
    return String(name || "index.html").replace(/\.html$/i, "").replace(/[^a-z0-9_-]/gi, "-");
  }

  function isNotificationButton(button) {
    const label = [
      button.getAttribute("aria-label"),
      button.innerText,
      button.textContent,
    ].map(text).join("");
    return /通知|notifications/i.test(label);
  }

  function hideRedundantHeaderNode(node) {
    if (!node) return;
    node.classList.add("gohome-redundant-node");
    node.setAttribute("aria-hidden", "true");
    if ("tabIndex" in node) node.tabIndex = -1;
  }

  function compactStitchAppChrome() {
    const current = page();
    document.body.classList.add(`gohome-page-${pageSlug(current)}`);
    if (!shellPages.has(current)) return;

    document.body.classList.add("gohome-app-shell-page");
    if (mainTabPages.has(current)) document.body.classList.add("gohome-main-tab-page");

    const header = Array.from(document.body.children).find((node) => node.tagName === "HEADER");
    if (!header) return;
    const redundantTitle = $$("h1", header).find((node) => text(node.textContent) === "回家");
    if (!redundantTitle) return;

    header.classList.add("gohome-compact-topbar");
    hideRedundantHeaderNode(redundantTitle);

    $$("img", header).forEach((image) => {
      const holder = image.closest("button, a") || image.closest("div") || image;
      hideRedundantHeaderNode(holder);
    });

    $$("button", header).forEach((button) => {
      if (isNotificationButton(button)) hideRedundantHeaderNode(button);
    });

    const visibleControls = $$("button, a", header).filter((node) => !node.classList.contains("gohome-redundant-node"));
    if (!visibleControls.length || mainTabPages.has(current)) {
      header.classList.add("gohome-topbar-collapsed");
    } else {
      header.classList.add("gohome-topbar-back-only");
    }
  }

  function toast(message, tone = "info") {
    let node = document.getElementById("gohome-stitch-toast");
    if (!node) {
      node = document.createElement("div");
      node.id = "gohome-stitch-toast";
      node.className = "fixed left-1/2 z-[80] -translate-x-1/2 rounded-full px-4 py-2 text-sm font-semibold shadow-lg transition-opacity";
      node.style.bottom = "calc(92px + env(safe-area-inset-bottom, 0px))";
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.style.background = tone === "error" ? "#ffdad6" : "#d4e3ff";
    node.style.color = tone === "error" ? "#93000a" : "#001c39";
    node.style.opacity = "1";
    window.clearTimeout(node._timer);
    node._timer = window.setTimeout(() => {
      node.style.opacity = "0";
    }, 1800);
  }

  function go(path) {
    window.location.href = window.GoHomeEdge?.pageHref?.(path) || path;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function ensureApi() {
    if (!window.GoHomeEdge) return false;
    if (state.connected) return true;
    try {
      GoHomeEdge.bootstrapLaunchState?.();
      await GoHomeEdge.connect();
      state.connected = true;
      return true;
    } catch (error) {
      toast(error.message || "服务器未连接", "error");
      return false;
    }
  }

  async function ensureFamily(options = {}) {
    const createIfMissing = Boolean(options.createIfMissing);
    if (!(await ensureApi())) return null;
    const families = await GoHomeEdge.myFamilies();
    state.families = families;
    if (families[0]) return families[0];
    if (!createIfMissing) {
      if (options.redirect !== false) go("family.html?mode=setup");
      return null;
    }
    const family = await GoHomeEdge.createFamily({ name: "我的家" });
    state.families = [family];
    return family;
  }

  function selectedRelationship() {
    const selected = $(".relationship-card.selected") || $(".relationship-card.bg-primary-container");
    return selected?.dataset?.name || selected?.innerText?.trim() || "母亲";
  }

  function setInputValue(selector, value) {
    const input = $(selector);
    if (input) input.value = String(value || "");
  }

  function setParentProfileNextEnabled() {
    const next = $("#next-button");
    if (!next) return;
    const hasName = Boolean($("#custom-name")?.value.trim());
    next.disabled = !hasName;
  }

  function selectRelationshipCard(name) {
    const targetName = String(name || "").trim();
    $$(".relationship-card").forEach((card) => {
      const selected = targetName && card.dataset.name === targetName;
      card.setAttribute("aria-pressed", selected ? "true" : "false");
      card.classList.toggle("selected", selected);
      card.classList.toggle("border-primary", selected);
      card.classList.toggle("bg-primary-container", selected);
      card.classList.toggle("text-on-primary-container", selected);
      card.classList.toggle("border-surface-container-highest", !selected);
      card.classList.toggle("bg-surface-container-lowest", !selected);
    });
  }

  function wireRelationshipCards() {
    const input = $("#custom-name");
    const clear = $("#clear-input");
    const next = $("#next-button");
    $$(".relationship-card").forEach((card) => {
      card.setAttribute("aria-pressed", card.classList.contains("selected") ? "true" : "false");
      card.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        const name = String(card.dataset.name || "").trim();
        selectRelationshipCard(name);
        if (input) input.value = name;
        clear?.classList.toggle("hidden", !name);
        if (next) next.disabled = !name;
        setParentProfileNextEnabled();
      }, true);
    });
  }

  function setParentProfileCopy(editing) {
    const title = document.querySelector("body.gohome-page-parent_profile header div.font-headline-md");
    const heading = document.querySelector("body.gohome-page-parent_profile main h1");
    const subheading = document.querySelector("body.gohome-page-parent_profile main h1 + p");
    const next = $("#next-button");
    if (title) title.textContent = editing ? "家人资料" : "添加家人";
    if (heading) heading.textContent = editing ? "编辑被守护人资料" : "先补全被守护人资料";
    if (subheading) subheading.textContent = "用于关怀卡片、电话联系和回家提醒。";
    if (next) {
      const textNode = Array.from(next.childNodes).find((child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
      if (textNode) textNode.textContent = editing ? "保存资料 " : "下一步 ";
    }
  }

  async function hydrateParentProfile() {
    if (!(await ensureApi())) return null;
    if (!GoHomeEdge.isAuthenticated?.()) {
      go(GoHomeEdge.loginHref?.(GoHomeEdge.currentPagePath?.() || "parent_profile.html") || "login.html");
      return null;
    }
    let families = [];
    try {
      await GoHomeEdge.currentUser();
      families = await GoHomeEdge.myFamilies();
    } catch (_error) {
      GoHomeEdge.clearAuthToken?.();
      go(GoHomeEdge.loginHref?.(GoHomeEdge.currentPagePath?.() || "parent_profile.html") || "login.html");
      return null;
    }
    state.families = families;
    const familyId = new URLSearchParams(window.location.search).get("family_id") || families[0]?.id || "";
    if (!familyId) {
      go("family.html?mode=setup");
      return null;
    }
    try {
      const profile = await GoHomeEdge.v1ElderProfile(familyId, "elder_primary");
      const editing = Boolean(profile?.display_name || profile?.mobile_phone || profile?.phone || profile?.home_phone);
      setParentProfileCopy(editing);
      const relationship = profile.relationship || "";
      setInputValue("#custom-name", profile.display_name || relationship || "");
      setInputValue("#elder-mobile", profile.mobile_phone || profile.phone || "");
      setInputValue("#elder-home-phone", profile.home_phone || "");
      setInputValue("#elder-city", profile.city || "杭州");
      setInputValue("#elder-district", profile.district || "");
      selectRelationshipCard(relationship);
      $("#clear-input")?.classList.toggle("hidden", !$("#custom-name")?.value.trim());
      setParentProfileNextEnabled();
      return { family: families.find((item) => String(item.id) === String(familyId)) || families[0] || null, profile };
    } catch (_error) {
      setParentProfileCopy(false);
      return { family: families.find((item) => String(item.id) === String(familyId)) || families[0] || null, profile: null };
    }
  }

  function wireLogin() {
    const form = $("form");
    if (!form) return;
    let authMode = new URLSearchParams(window.location.search).get("mode") === "register" ? "register" : "login";
    const tabs = $$(".gohome-auth-mode-tab", form);
    const hint = $("#auth-mode-hint");
    const submitButton = $("#auth-submit") || $("button[type='submit']", form);

    function setAuthMode(mode) {
      authMode = mode === "register" ? "register" : "login";
      tabs.forEach((tab) => {
        const selected = tab.dataset.authMode === authMode;
        tab.setAttribute("aria-pressed", selected ? "true" : "false");
        tab.classList.toggle("bg-surface-container-lowest", selected);
        tab.classList.toggle("text-on-background", selected);
        tab.classList.toggle("shadow-sm", selected);
        tab.classList.toggle("text-on-surface-variant", !selected);
      });
      if (hint) {
        hint.textContent = authMode === "register"
          ? "用手机号创建新的家属身份。新手机号不会自动读取已有家庭、盒子和摄像头数据。"
          : "用手机号登录，家庭与设备数据只跟随当前手机号显示。";
      }
      if (submitButton) submitButton.textContent = authMode === "register" ? "创建并登录" : "登录";
    }

    tabs.forEach((tab) => {
      tab.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        setAuthMode(tab.dataset.authMode);
      }, true);
    });
    setAuthMode(authMode);

    const codeButton = $$("button", form).find((button) => /获取验证码|演示验证码/.test(text(button.innerText)));
    codeButton?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      const codeInput = $("#code");
      if (codeInput) codeInput.value = "000000";
      toast("验证码已填入");
    }, true);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (form.reportValidity && !form.reportValidity()) return;
      if (!(await ensureApi())) return;
      const phone = ($("#phone")?.value || "").replace(/\D/g, "");
      const code = $("#code")?.value.trim() || "000000";
      if (!/^\d{11}$/.test(phone)) {
        toast("请输入 11 位手机号", "error");
        return;
      }
      const submit = submitButton || $("button[type='submit']", form);
      const oldText = submit?.textContent || "";
      if (submit) {
        submit.disabled = true;
        submit.textContent = authMode === "register" ? "正在创建..." : "正在登录...";
      }
      try {
        const payload = {
          phone,
          code: code.padEnd(6, "0"),
          display_name: "家属",
        };
        if (authMode === "register") {
          await GoHomeEdge.register(payload);
          toast("手机号已创建");
          window.setTimeout(() => go("family.html?mode=setup"), 220);
          return;
        }
        await GoHomeEdge.login(payload);
        toast("登录成功");
        const families = await GoHomeEdge.myFamilies().catch(() => []);
        const fallback = Array.isArray(families) && families.length ? "index.html" : "family.html?mode=setup";
        const target = GoHomeEdge.redirectTarget?.(fallback) || fallback;
        window.setTimeout(() => go(target), 220);
      } catch (error) {
        if (authMode === "register" && error.status === 409) {
          toast("手机号已注册，请切换到手机号登录", "error");
        } else if (authMode === "login" && error.status === 401) {
          toast("手机号未注册或验证码不正确", "error");
        } else {
          toast(error.message || (authMode === "register" ? "创建失败" : "登录失败"), "error");
        }
      } finally {
        if (submit) {
          submit.disabled = false;
          submit.textContent = oldText || (authMode === "register" ? "创建并登录" : "登录");
        }
      }
    });
  }

  function wireParentProfile() {
    const next = $("#next-button");
    if (!next) return;
    hydrateParentProfile();
    wireRelationshipCards();
    ["#custom-name", "#elder-mobile", "#elder-home-phone", "#elder-city", "#elder-district"].forEach((selector) => {
      $(selector)?.addEventListener("input", setParentProfileNextEnabled);
    });
    next.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (next.disabled) return;
      try {
        const family = await ensureFamily({ redirect: true });
        if (!family) return;
        const relationship = selectedRelationship();
        const displayName = $("#custom-name")?.value.trim() || relationship || "妈妈";
        await GoHomeEdge.v1UpsertElderProfile(family.id, "elder_primary", {
          display_name: displayName,
          relationship,
          city: $("#elder-city")?.value.trim() || "杭州",
          district: $("#elder-district")?.value.trim() || "",
          phone: $("#elder-mobile")?.value.trim() || "",
          mobile_phone: $("#elder-mobile")?.value.trim() || "",
          home_phone: $("#elder-home-phone")?.value.trim() || "",
        });
        toast("资料已保存");
        const target = GoHomeEdge.redirectTarget?.(`family.html?family_id=${family.id}`) || `family.html?family_id=${family.id}`;
        window.setTimeout(() => go(target), 220);
      } catch (error) {
        toast(error.message || "保存失败", "error");
      }
    }, true);
  }

  async function hydrateFamilySetup() {
    if (!(await ensureApi())) return;
    if (!GoHomeEdge.isAuthenticated?.()) {
      go(GoHomeEdge.loginHref?.("family.html?mode=setup") || "login.html");
      return;
    }
    const status = $("#familySetupStatus");
    const list = $("#familyExistingList");
    const createInput = $("#spaceName");
    try {
      const families = await GoHomeEdge.myFamilies();
      state.families = Array.isArray(families) ? families : [];
      if (createInput && !createInput.value.trim()) createInput.value = state.families.length ? "" : "我的家";
      if (status) {
        status.textContent = state.families.length
          ? "你已经加入家庭。可以继续绑定盒子、填写资料，或把邀请码发给其他家人。"
          : "新账号还没有家庭数据。创建家庭或输入邀请码后，才能看到盒子、摄像头和关怀卡片。";
      }
      if (!list) return;
      if (!state.families.length) {
        list.classList.add("hidden");
        list.innerHTML = "";
        return;
      }
      list.classList.remove("hidden");
      list.innerHTML = state.families.map((family) => {
        const profileHref = GoHomeEdge.pageHref?.(`parent_profile.html?family_id=${family.id}`, {
          next: `device_binding.html?family_id=${family.id}`,
        }) || `parent_profile.html?family_id=${family.id}`;
        const bindingHref = GoHomeEdge.pageHref?.(`device_binding.html?family_id=${family.id}`) || `device_binding.html?family_id=${family.id}`;
        return `
          <article class="rounded-xl border border-outline-variant/20 bg-surface-container-lowest p-4 shadow-sm">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="font-label-md text-label-md text-on-surface">${escapeHtml(family.name || "我的家")}</p>
                <p class="mt-1 font-body-md text-[13px] text-on-surface-variant">${Number(family.member_count || 1)} 位家人共享守护</p>
              </div>
              <span class="rounded-full bg-primary-container px-3 py-1 font-label-md text-[12px] text-primary">已加入</span>
            </div>
            <div class="mt-3 rounded-xl bg-surface-container-low px-3 py-2">
              <p class="font-body-md text-[12px] text-on-surface-variant">家庭邀请码</p>
              <p class="mt-1 break-all font-label-md text-label-md text-on-surface">${escapeHtml(family.join_code || "待生成")}</p>
            </div>
            <div class="mt-3 grid grid-cols-2 gap-2">
              <a class="rounded-xl bg-primary text-on-primary py-3 text-center font-label-md text-label-md" href="${profileHref}">填写资料</a>
              <a class="rounded-xl bg-primary-container text-primary py-3 text-center font-label-md text-label-md" href="${bindingHref}">绑定盒子</a>
            </div>
          </article>
        `;
      }).join("");
    } catch (error) {
      if (status) {
        status.textContent = error.message || "读取家庭信息失败，请稍后重试。";
        status.classList.add("text-[#93000a]");
      }
    }
  }

  function wireFamily() {
    hydrateFamilySetup();
    const createButton = $("#familyCreateButton")
      || $$("button").find((item) => text(item.innerText).includes("创建") || text(item.innerText).includes("继续"));
    const joinButton = $("#familyJoinButton");
    createButton?.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      try {
        if (!(await ensureApi())) return;
        const name = $("#spaceName")?.value.trim() || "我的家";
        const family = await GoHomeEdge.createFamily({ name });
        if (!family) return;
        toast("家庭空间已就绪");
        const next = GoHomeEdge.pageHref?.(`parent_profile.html?family_id=${family.id}`, {
          next: `device_binding.html?family_id=${family.id}`,
        }) || `parent_profile.html?family_id=${family.id}&next=device_binding.html`;
        window.setTimeout(() => go(next), 220);
      } catch (error) {
        toast(error.message || "创建失败", "error");
      }
    }, true);
    joinButton?.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      try {
        if (!(await ensureApi())) return;
        const code = $("#familyJoinCode")?.value.trim() || "";
        if (!code) {
          toast("请填写家庭邀请码", "error");
          return;
        }
        const family = await GoHomeEdge.joinFamily({ code });
        toast("已加入家庭");
        window.setTimeout(() => go(`index.html?family_id=${family.id}`), 220);
      } catch (error) {
        toast(error.message || "加入失败", "error");
      }
    }, true);
  }

  function currentFamilyId() {
    return new URLSearchParams(window.location.search).get("family_id") || state.families[0]?.id || 1;
  }

  function currentCameraId() {
    return new URLSearchParams(window.location.search).get("camera_id") || "";
  }

  function wireDeviceBinding() {
    if ($("#bindingClaimInput")) return;
    const buttons = $$("button").filter((item) => /扫描.*二维码|输入.*序列号|手动输入序列号|稍后设置/.test(item.innerText || ""));
    buttons.forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        try {
          const family = await ensureFamily();
          if (!family) return;
          const code = await GoHomeEdge.createDeviceBindingCode({ family_id: family.id, expires_in_minutes: 30 });
          toast(`绑定码 ${code.code}`);
          window.setTimeout(() => go(`camera_intro.html?family_id=${family.id}`), 260);
        } catch (error) {
          toast(error.message || "生成绑定码失败", "error");
        }
      }, true);
    });
  }

  function checkedRoom() {
    const checked = $("input[name='location']:checked");
    if (!checked) return "客厅";
    return $(`label[for='${checked.id}']`)?.innerText.trim() || "客厅";
  }

  function setCameraFeedback(message, tone = "neutral") {
    const node = $("#cameraConfigFeedback");
    if (!node) return;
    node.textContent = message || "";
    node.classList.remove("text-on-surface-variant", "text-[#93000a]", "text-[#2d7d5c]");
    if (tone === "error") node.classList.add("text-[#93000a]");
    else if (tone === "success") node.classList.add("text-[#2d7d5c]");
    else node.classList.add("text-on-surface-variant");
  }

  function setCameraSubmitBusy(button, busy, editing = false) {
    if (!button) return;
    button.disabled = busy;
    button.classList.toggle("opacity-70", busy);
    button.textContent = busy ? "正在提交..." : (editing ? "保存并同步" : "提交给家庭盒子同步");
  }

  function normalizeCameraPath(value) {
    const path = String(value || "").trim() || "/1/2";
    return path.startsWith("/") ? path : `/${path}`;
  }

  function cameraStreamUrlFromInputs() {
    const hostOrUrl = $("#cameraHostInput")?.value.trim() || "";
    if (!hostOrUrl) throw new Error("请填写摄像头 IP 或 RTSP 地址。");
    if (/^rtsp:\/\//i.test(hostOrUrl) || /^(demo|sample|mock):/i.test(hostOrUrl)) {
      return hostOrUrl;
    }
    if (/^https?:\/\//i.test(hostOrUrl)) {
      throw new Error("摄像头视频流需要填写 RTSP 地址，不是网页管理地址。");
    }
    const port = $("#cameraPortInput")?.value.trim() || "554";
    if (!/^\d+$/.test(port)) throw new Error("端口必须是数字。");
    const path = normalizeCameraPath($("#cameraPathInput")?.value);
    return `rtsp://${hostOrUrl}:${port}${path}`;
  }

  function cameraPayloadFromConnectForm({ editing = false, existing = null } = {}) {
    const room = checkedRoom();
    const username = $("#cameraUsernameInput")?.value.trim() || "";
    const password = $("#cameraPasswordInput")?.value || "";
    const hostOrUrl = $("#cameraHostInput")?.value.trim() || "";
    const payload = {
      family_id: currentFamilyId(),
      name: $("#cameraNameInput")?.value.trim() || `${room}摄像头`,
      room,
      enabled: true,
      status: "pending_edge_sync",
      sync_status: "pending_edge_sync",
      source: "app_server_config",
    };

    if (hostOrUrl) {
      payload.stream_url = cameraStreamUrlFromInputs();
    } else if (!editing || !existing?.has_stream_config) {
      throw new Error("请填写摄像头 IP 或 RTSP 地址。");
    }

    if (!editing || username) payload.username = username || null;
    if (!editing || password) payload.password = password || null;
    return payload;
  }

  function setCheckedRoom(room) {
    const target = String(room || "").trim();
    if (!target) return;
    const match = $$("input[name='location']").find((input) => {
      const label = $(`label[for='${input.id}']`);
      return label && text(label.innerText) === text(target);
    });
    if (match) match.checked = true;
  }

  async function hydrateConnectEditMode() {
    const cameraId = currentCameraId();
    if (!cameraId) return null;
    if (!(await ensureApi())) return null;
    const cameras = await GoHomeEdge.cameras();
    const camera = cameras.find((item) => String(item.id) === String(cameraId));
    if (!camera) {
      setCameraFeedback("没有找到这台摄像头，可以重新添加。", "error");
      return null;
    }
    state.editingCamera = camera;
    const title = $("#cameraConfigTitle");
    const heroTitle = $("#cameraConfigHeroTitle");
    const submit = $("#cameraSubmitButton");
    if (title) title.textContent = "配置摄像头";
    if (heroTitle) heroTitle.textContent = "更新家庭盒子接入信息";
    if (submit) submit.textContent = "保存并同步";
    const nameInput = $("#cameraNameInput");
    if (nameInput) nameInput.value = camera.name || "";
    setCheckedRoom(camera.room);
    const hostInput = $("#cameraHostInput");
    const usernameInput = $("#cameraUsernameInput");
    const passwordInput = $("#cameraPasswordInput");
    if (hostInput) {
      hostInput.value = "";
      hostInput.placeholder = camera.has_stream_config
        ? "留空保留当前 RTSP 配置，或填写新地址"
        : "请填写摄像头 IP 或 rtsp:// 地址";
    }
    if (usernameInput) {
      usernameInput.value = "";
      usernameInput.placeholder = camera.password_set ? "留空保留当前账号" : "admin";
    }
    if (passwordInput) {
      passwordInput.value = "";
      passwordInput.placeholder = camera.password_set ? "留空保留当前密码" : "摄像头密码";
    }
    setCameraFeedback(camera.has_stream_config
      ? "当前摄像头已有接入配置。只改名称/位置时，RTSP 和密码可以留空。"
      : "这台摄像头还缺少接入信息，请补齐后同步给家庭盒子。");
    return camera;
  }

  function wireConnect() {
    hydrateConnectEditMode().catch((error) => setCameraFeedback(error.message || "读取摄像头失败", "error"));
    const clearName = $("[data-clear-camera-name]");
    clearName?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      const input = $("#cameraNameInput");
      if (input) input.value = "";
      input?.focus();
    }, true);

    const action = $("#cameraSubmitButton")
      || $$("button").find((item) => (
        text(item.innerText).includes("提交给家庭盒子同步")
        || text(item.innerText).includes("生成连接二维码")
        || text(item.innerText).includes("下一步")
      ));
    if (!action) return;
    action.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!(await ensureApi())) return;
      const editing = Boolean(currentCameraId());
      try {
        setCameraSubmitBusy(action, true, editing);
        setCameraFeedback(editing ? "正在更新配置并等待家庭盒子同步..." : "正在保存配置并等待家庭盒子同步...");
        const payload = cameraPayloadFromConnectForm({ editing, existing: state.editingCamera });
        const camera = editing
          ? await GoHomeEdge.updateCamera(currentCameraId(), payload)
          : await GoHomeEdge.createCamera(payload);
        await GoHomeEdge.testCamera(camera.id).catch(() => null);
        toast(editing ? "已更新并提交同步" : "已提交给家庭盒子");
        setCameraFeedback("已提交。家庭盒子会在 10 秒内拉取配置并回传状态。", "success");
        window.setTimeout(() => go(`cameras.html?camera_id=${camera.id}`), 420);
      } catch (error) {
        setCameraFeedback(error.message || "添加失败", "error");
        toast(error.message || "添加失败", "error");
      } finally {
        setCameraSubmitBusy(action, false, editing);
      }
    }, true);
  }

  function cameraState(camera) {
    if (!camera.enabled) {
      return { label: "未启用", tone: "off", detail: "已暂停下发给家庭盒子" };
    }
    if (camera.status === "online") {
      return { label: "在线", tone: "ok", detail: "家庭盒子已接入并回传状态" };
    }
    if (camera.status === "offline") {
      return { label: "离线", tone: "error", detail: camera.last_error || "家庭盒子暂未回传画面" };
    }
    return { label: "待同步", tone: "pending", detail: "等待家庭盒子同步配置并完成本地接入" };
  }

  function cameraCard(camera, index) {
    const state = cameraState(camera);
    const badgeTone = state.tone === "ok" ? "good" : (state.tone === "error" ? "warn" : "muted");
    return `
      <article class="gohome-camera-device-card" data-camera-id="${camera.id}">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <span class="app-mini-pill ${badgeTone}">${state.label}</span>
            <h3 class="mt-2">${escapeHtml(camera.room || camera.name || "摄像头")}</h3>
            <p>${escapeHtml(camera.name || "摄像头")} ${escapeHtml(state.detail)}</p>
          </div>
          <button aria-label="同步状态" class="w-10 h-10 rounded-full bg-surface-container-low text-primary shrink-0 inline-flex items-center justify-center" data-action="sync" data-id="${camera.id}">
            <span class="material-symbols-outlined">sync</span>
          </button>
        </div>
        <div class="gohome-camera-device-actions">
          <button data-action="edit" data-id="${camera.id}">配置</button>
          <button data-action="toggle" data-id="${camera.id}">${camera.enabled ? "停用" : "启用"}</button>
          <button data-action="delete" data-id="${camera.id}">删除</button>
        </div>
      </article>
    `;
  }

  async function renderCameras() {
    if (!(await ensureApi())) return;
    const grid = $("#cameraDeviceGrid") || $("section.grid");
    if (!grid) return;
    const cameras = await GoHomeEdge.cameras();
    grid.innerHTML = cameras.length
      ? cameras.map(cameraCard).join("")
      : `<div class="gohome-panel gohome-empty-state md:col-span-2 lg:col-span-3">
          <span class="material-symbols-outlined">linked_camera</span>
          <h3>还没有摄像头</h3>
          <p>先在 App 里提交摄像头接入信息，家庭盒子会自动同步。</p>
          <button class="gohome-pill-button primary inline-flex items-center justify-center gap-2 mt-4" data-action="add">
            <span class="material-symbols-outlined text-[20px]">add</span>
            添加摄像头
          </button>
        </div>`;
  }

  function wireCameras() {
    renderCameras().catch((error) => toast(error.message || "读取摄像头失败", "error"));
    const main = $("main");
    main?.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const id = button.dataset.id;
      try {
        if (button.dataset.action === "add") {
          go("connect.html");
          return;
        } else if (button.dataset.action === "monitor") {
          go("monitor.html");
          return;
        } else if (button.dataset.action === "edit") {
          go(`connect.html?camera_id=${encodeURIComponent(id)}`);
          return;
        } else if (button.dataset.action === "delete") {
          await GoHomeEdge.deleteCamera(id);
          toast("已删除摄像头");
        } else if (button.dataset.action === "toggle") {
          const current = (await GoHomeEdge.cameras()).find((item) => String(item.id) === String(id));
          await GoHomeEdge.updateCamera(id, { enabled: !current?.enabled });
          toast(current?.enabled ? "已停用" : "已启用");
        } else if (button.dataset.action === "sync") {
          const result = await GoHomeEdge.testCamera(id);
          toast(result.message || "已提交给家庭盒子");
        }
        await renderCameras();
      } catch (error) {
        toast(error.message || "操作失败", "error");
      }
    }, true);
  }

  async function hydratePrivacy() {
    if (!(await ensureApi())) return;
    try {
      const [user, families, auth, device, cameras] = await Promise.all([
        GoHomeEdge.currentUser(),
        GoHomeEdge.myFamilies(),
        GoHomeEdge.deviceAuthStatus().catch(() => null),
        GoHomeEdge.appDevice().catch(() => null),
        GoHomeEdge.appCameras().catch(() => []),
      ]);
      const family = families[0] || null;
      const profile = family
        ? await GoHomeEdge.v1ElderProfile(family.id, "elder_primary").catch(() => null)
        : null;
      const cardTitle = $(".user-card-gradient h2");
      const rawName = String(user.display_name || "").trim();
      const userName = rawName && rawName !== "回家管理员" ? rawName : (profile?.display_name ? `${profile.display_name}家属` : "家属账号");
      if (cardTitle) cardTitle.textContent = userName;
      const uid = $(".user-card-gradient p");
      if (uid) uid.textContent = family ? `${family.name || "家庭空间"} · ${profile?.relationship || "家属"}` : "家属端账号";
      const familyText = $$("button").find((item) => text(item.innerText).includes("家庭成员"))?.querySelector("p");
      if (familyText) familyText.textContent = `${families[0]?.member_count || 1}位家人共享守护`;
      const badge = $(".user-card-gradient .font-label-md.text-label-md.text-white\\/90");
      const connected = Boolean(auth?.configured || device?.worker_running || (Array.isArray(cameras) && cameras.some((camera) => camera.enabled !== false && camera.status === "online")));
      if (badge) badge.textContent = connected ? "家庭盒子已连接" : "等待连接家庭盒子";
    } catch (_error) {
      // Static content remains usable.
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const current = page();
    compactStitchAppChrome();
    if (current === "login.html") wireLogin();
    if (current === "parent_profile.html") wireParentProfile();
    if (current === "family.html") wireFamily();
    if (current === "device_binding.html") wireDeviceBinding();
    if (current === "connect.html") wireConnect();
    if (current === "cameras.html") wireCameras();
    if (current === "privacy.html") hydratePrivacy();
  });

  if (document.body) compactStitchAppChrome();
})();
