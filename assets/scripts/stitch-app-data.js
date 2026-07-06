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

  async function ensureFamily() {
    if (!(await ensureApi())) return null;
    const families = await GoHomeEdge.myFamilies();
    state.families = families;
    if (families[0]) return families[0];
    const family = await GoHomeEdge.createFamily({ name: "我的家" });
    state.families = [family];
    return family;
  }

  function selectedRelationship() {
    const selected = $(".relationship-card.selected") || $(".relationship-card.bg-primary-container");
    return selected?.dataset?.name || selected?.innerText?.trim() || "母亲";
  }

  function wireLogin() {
    const form = $("form");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!(await ensureApi())) return;
      const phone = $("#phone")?.value.trim() || "13800000000";
      const code = $("#code")?.value.trim() || "000000";
      const submit = $("button[type='submit']", form);
      const oldText = submit?.textContent || "";
      if (submit) {
        submit.disabled = true;
        submit.textContent = "正在登录...";
      }
      try {
        await GoHomeEdge.register({
          email: `${phone}@phone.gohome.local`,
          password: code.padEnd(6, "0"),
          display_name: "家属",
        });
        toast("登录成功");
        window.setTimeout(() => go("parent_profile.html"), 220);
      } catch (error) {
        toast(error.message || "登录失败", "error");
      } finally {
        if (submit) {
          submit.disabled = false;
          submit.textContent = oldText;
        }
      }
    });
  }

  function wireParentProfile() {
    const next = $("#next-button");
    if (!next) return;
    next.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (next.disabled) return;
      try {
        const family = await ensureFamily();
        if (!family) return;
        const relationship = selectedRelationship();
        const displayName = $("#custom-name")?.value.trim() || relationship || "妈妈";
        await GoHomeEdge.v1UpsertElderProfile(family.id, "elder_primary", {
          display_name: displayName,
          relationship,
          city: "杭州",
        });
        toast("资料已保存");
        window.setTimeout(() => go(`family.html?family_id=${family.id}`), 220);
      } catch (error) {
        toast(error.message || "保存失败", "error");
      }
    }, true);
  }

  function wireFamily() {
    const button = $$("button").find((item) => text(item.innerText).includes("创建") || text(item.innerText).includes("继续"));
    if (!button) return;
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      try {
        const family = await ensureFamily();
        if (!family) return;
        toast("家庭空间已就绪");
        window.setTimeout(() => go(`device_binding.html?family_id=${family.id}`), 220);
      } catch (error) {
        toast(error.message || "创建失败", "error");
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
    const buttons = $$("button").filter((item) => /扫描包装二维码|手动输入序列号|稍后设置/.test(item.innerText || ""));
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
    const dotClass = state.tone === "ok" ? "bg-tertiary" : (state.tone === "error" ? "bg-error" : "bg-primary");
    return `
      <article class="rounded-xl border border-surface-container-low bg-surface-container-lowest p-4 shadow-[0_4px_12px_rgba(0,0,0,0.035)] flex flex-col gap-3" data-camera-id="${camera.id}">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="w-2 h-2 rounded-full ${dotClass} shrink-0"></span>
              <span class="font-label-md text-label-md text-on-surface">${state.label}</span>
            </div>
            <h3 class="font-headline-md text-headline-md text-on-background truncate">${escapeHtml(camera.room || camera.name || "摄像头")}</h3>
            <p class="font-body-md text-[14px] leading-5 text-on-surface-variant">${escapeHtml(camera.name || "摄像头")} · ${escapeHtml(state.detail)}</p>
          </div>
          <button aria-label="同步状态" class="w-10 h-10 rounded-full hover:bg-surface-container-low text-primary shrink-0 inline-flex items-center justify-center" data-action="sync" data-id="${camera.id}">
            <span class="material-symbols-outlined">sync</span>
          </button>
        </div>
        <div class="grid grid-cols-3 gap-2">
          <button class="min-h-10 rounded-lg bg-primary text-on-primary font-label-md text-label-md whitespace-nowrap" data-action="edit" data-id="${camera.id}">配置</button>
          <button class="min-h-10 rounded-lg bg-surface-container-low text-on-surface font-label-md text-label-md whitespace-nowrap" data-action="toggle" data-id="${camera.id}">${camera.enabled ? "停用" : "启用"}</button>
          <button class="min-h-10 rounded-lg bg-[#fff4f1] text-[#93000a] font-label-md text-label-md whitespace-nowrap" data-action="delete" data-id="${camera.id}">删除</button>
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
      : `<div class="bg-surface-container-lowest rounded-2xl p-6 text-center text-on-surface-variant md:col-span-2 lg:col-span-3">
          <p class="mb-4">还没有摄像头，先在 App 里提交摄像头接入信息。</p>
          <button class="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-5 py-3 text-on-primary font-label-md text-label-md" data-action="add">
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
      const [user, families, auth] = await Promise.all([
        GoHomeEdge.currentUser(),
        GoHomeEdge.myFamilies(),
        GoHomeEdge.deviceAuthStatus().catch(() => null),
      ]);
      const cardTitle = $(".user-card-gradient h2");
      if (cardTitle) cardTitle.textContent = user.display_name || "家属";
      const uid = $(".user-card-gradient p");
      if (uid) uid.textContent = user.email || "";
      const familyText = $$("button").find((item) => text(item.innerText).includes("家庭成员"))?.querySelector("p");
      if (familyText) familyText.textContent = `${families[0]?.member_count || 1}位家人共享位置`;
      const badge = $(".user-card-gradient .font-label-md.text-label-md.text-white\\/90");
      if (badge) badge.textContent = auth?.configured ? "家庭盒子已绑定" : "等待绑定家庭盒子";
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
