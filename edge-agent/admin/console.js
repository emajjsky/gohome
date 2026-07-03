const pageName = document.body.dataset.page || "home";
const defaultCameraChannel = "1";
const defaultCameraStream = "2";

const state = {
  device: null,
  setupNetwork: null,
  cameraPresets: null,
  cameraDiscovery: [],
  cameras: [],
  selectedCameraId: null,
  cameraMode: "lan",
  previewAlgorithm: "quality",
  maxCameras: 3,
  detectorBackend: "basic",
  latestSnapshot: null,
  cameraFormPrefilled: false,
  wifiConnecting: false,
  refreshTimer: null,
  streamMaskTimer: null,
  liveAnalysisTimer: null,
  liveAnalysisBusy: false,
  liveAnalysisErrorShown: false,
  toastTimer: null,
};

const $ = (id) => document.getElementById(id);

function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function on(id, eventName, handler) {
  const element = $(id);
  if (element) element.addEventListener(eventName, handler);
}

function fmtTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", { hour12: false });
}

function fmtNumber(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "-";
}

function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "-";
  if (value < 60) return `${Math.round(value)} 秒`;
  const minutes = Math.floor(value / 60);
  const rest = Math.round(value % 60);
  return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分钟`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function showToast(message) {
  const toast = $("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

async function hydrateAdminSession() {
  const sessionTarget = document.querySelector(".admin-session-slot") || document.querySelector(".page-actions");
  if (!sessionTarget || $("adminSessionLogout")) return;
  try {
    const status = await api("/api/admin/auth/status");
    const button = document.createElement("button");
    button.id = "adminSessionLogout";
    button.className = "secondary-button admin-session-button";
    button.type = "button";
    button.innerHTML = '<span class="material-symbols-outlined" data-icon="↩" aria-hidden="true"></span><span>退出登录</span>';
    button.addEventListener("click", async () => {
      await api("/api/admin/auth/logout", { method: "POST" }).catch(() => null);
      window.location.href = "/admin/login.html";
    });
    sessionTarget.appendChild(button);
  } catch {
    // Middleware redirects unauthenticated page loads; ignore status failures here.
  }
}

function setBusy(button, busy) {
  if (!button) return;
  button.disabled = busy;
  button.dataset.originalText ??= button.innerHTML;
  button.innerHTML = busy
    ? '<span class="material-symbols-outlined">progress_activity</span>处理中'
    : button.dataset.originalText;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data?.detail || `HTTP ${response.status}`);
  }
  return data;
}

function userSafeError(message) {
  const text = String(message || "");
  if (/ultralytics|YOLO backend|requirements-yolo|pip install/i.test(text)) {
    return "视觉模型未安装，请先安装 YOLO 依赖和模型文件。";
  }
  if (/insufficient privileges|not authorized|权限|NetworkManager/i.test(text)) {
    return "盒子还没有配网权限，请重新运行安装脚本后再试。";
  }
  if (/secrets were required|no secrets|请输入正确的 Wi-Fi 密码|password|key-mgmt|802-11-wireless-security/i.test(text)) {
    return "请输入正确的 Wi-Fi 密码。";
  }
  if (/failed to fetch|networkerror|load failed|network request failed/i.test(text)) {
    return state.wifiConnecting ? "盒子正在切换网络，稍后用新地址打开。" : "连接中断，请刷新页面。";
  }
  if (/could not|cannot open|opened but no frame|ffmpeg|hevc|h265|rtsp|timeout/i.test(text)) {
    return "摄像头暂时无法稳定连接，请检查摄像头地址或切换 720p 子码流。";
  }
  return text || "操作失败，请稍后重试。";
}

function isDemoStreamUrl(value) {
  return String(value ?? "").trim().toLowerCase().startsWith("demo:");
}

function isLocalStreamUrl(value) {
  const streamUrl = String(value ?? "").trim().toLowerCase();
  return isDemoStreamUrl(streamUrl) || /^(local|webcam|device|camera):/.test(streamUrl) || /^\d+$/.test(streamUrl);
}

function normalizeStreamUrl(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  try {
    const url = new URL(text);
    return `${url.protocol}//${url.host}${url.pathname || "/"}${url.search}`.toLowerCase();
  } catch {
    return text.toLowerCase();
  }
}

function statusText(status) {
  if (status === "online") return "在线";
  if (status === "offline") return "离线";
  if (status === "error") return "需测试";
  return "未知";
}

function cameraDisplayStatus(camera) {
  if (!camera) return "未接入";
  if (camera.status === "online" || camera.last_seen_at) return "画面正常";
  if (!camera.enabled) return "已停用";
  if (camera.status === "error") return "需要重新测试";
  return statusText(camera.status);
}

function cameraDisplayName(camera) {
  if (!camera) return "摄像头";
  const raw = String(camera.name || "").trim();
  const room = String(camera.room || "").trim() || "客厅";
  if (!raw || /^RTSP\s*摄像头$/i.test(raw) || raw === "局域网摄像头") {
    return `${room}摄像头`;
  }
  return raw;
}

function cameraRank(camera) {
  return (camera.enabled ? 40 : 0) + (!isLocalStreamUrl(camera.stream_url) ? 30 : 0) + (camera.status === "online" ? 20 : 0);
}

function preferredCameraId(cameras) {
  return [...cameras].sort((a, b) => cameraRank(b) - cameraRank(a) || Number(b.id) - Number(a.id))[0]?.id || null;
}

function selectedCamera() {
  return state.cameras.find((camera) => Number(camera.id) === Number(state.selectedCameraId)) || null;
}

function physicalCameras() {
  return state.cameras.filter((camera) => !isDemoStreamUrl(camera.stream_url));
}

function defaultCameraHost() {
  if (state.cameraPresets?.default_host) return state.cameraPresets.default_host;
  const ip = state.device?.lan_ip || state.setupNetwork?.lan_ip || "";
  const parts = ip.split(".");
  return parts.length === 4 ? [...parts.slice(0, 3), "11"].join(".") : "192.168.1.11";
}

function parseRtspUrl(value) {
  try {
    const url = new URL(value);
    return {
      host: url.hostname,
      port: url.port || "554",
      path: `${url.pathname || "/"}${url.search || ""}`,
      username: decodeURIComponent(url.username || ""),
      password: decodeURIComponent(url.password || ""),
    };
  } catch {
    return null;
  }
}

function normalizeCameraNumber(value, fallback) {
  const text = String(value ?? "").trim();
  return /^[1-9]\d*$/.test(text) ? text : fallback;
}

function parseCameraStreamPath(value) {
  const path = String(value || "").trim().split("?")[0].replace(/^\/+/, "");
  const parts = path.split("/").filter(Boolean);
  if (parts.length >= 2) {
    return {
      channel: normalizeCameraNumber(parts[0], defaultCameraChannel),
      stream: normalizeCameraNumber(parts[1], defaultCameraStream),
    };
  }
  if (parts.length === 1) {
    const only = normalizeCameraNumber(parts[0], defaultCameraStream);
    return { channel: defaultCameraChannel, stream: only };
  }
  return { channel: defaultCameraChannel, stream: defaultCameraStream };
}

function setCameraStreamControls(path) {
  const parsed = parseCameraStreamPath(path);
  if ($("cameraChannel")) $("cameraChannel").value = parsed.channel;
  if ($("cameraStream")) $("cameraStream").value = parsed.stream;
}

function cameraStreamPath() {
  const channel = normalizeCameraNumber($("cameraChannel")?.value, defaultCameraChannel);
  const stream = normalizeCameraNumber($("cameraStream")?.value, defaultCameraStream);
  return `/${channel}/${stream}`;
}

function selectedCameraProfile() {
  const key = $("cameraProfile")?.value || "auto";
  return (state.cameraPresets?.profiles || []).find((profile) => profile.key === key)
    || { key: "sub_stream", label: "副码流", path: "/1/2", hint: "默认使用 1 频道副码流。" };
}

function renderCameraProfiles() {
  const select = $("cameraProfile");
  if (!select || !state.cameraPresets?.profiles) return;
  const current = select.value || "auto";
  select.innerHTML = state.cameraPresets.profiles.map((profile) => `
    <option value="${escapeHtml(profile.key)}" ${profile.key === current ? "selected" : ""}>${escapeHtml(profile.label)}</option>
  `).join("");
  if ([...select.options].some((option) => option.value === current)) select.value = current;
  applyCameraProfile();
}

function applyCameraProfile() {
  const profile = selectedCameraProfile();
  if ($("cameraChannel") && profile.key !== "custom") {
    setCameraStreamControls(profile.path || "/1/2");
  }
  setText("cameraProfileHint", profile.hint || "默认使用 1 频道副码流。");
  syncLanUrlPreview();
  updateCameraLimitState();
}

function syncCameraName() {
  const room = $("cameraRoom")?.value.trim() || "客厅";
  if ($("cameraName")) $("cameraName").value = `${room}摄像头`;
}

function prefillCameraForm() {
  if (pageName !== "cameras" || state.cameraFormPrefilled || !$("cameraHost")) return;
  if ($("cameraRoom")) $("cameraRoom").value ||= state.cameraPresets?.default_room || "客厅";
  syncCameraName();
  if ($("cameraHost")) $("cameraHost").value = "";
  if ($("cameraPort")) $("cameraPort").value ||= String(state.cameraPresets?.default_port || 554);
  if ($("cameraUsername")) $("cameraUsername").value ||= state.cameraPresets?.default_username || "admin";
  setCameraStreamControls(state.cameraPresets?.default_path || "/1/2");
  if ($("cameraPassword")) $("cameraPassword").value = "";
  state.cameraFormPrefilled = true;
  syncLanUrlPreview();
  updateCameraLimitState();
  resetCameraTestState();
}

async function loadDevice() {
  const device = await api("/api/device");
  state.device = device;
  state.detectorBackend = device.detector_backend || "basic";
  setText("detectorBackend", device.detector_backend || "-");
  setText("notifyChannel", device.notify_channel || "off");
  setText("dataDir", device.data_dir || "-");
  setText("yoloModel", device.yolo_model || "basic 模式未加载");
  setText("workerBadge", device.worker_running ? "服务正常" : "服务停止");
  if ($("workerBadge")) $("workerBadge").className = `status-pill ${device.worker_running ? "" : "bad"}`;
  setText("setupWorkerBadge", device.worker_running ? "服务运行中" : "服务已停止");
  if ($("setupWorkerBadge")) $("setupWorkerBadge").className = `status-pill ${device.worker_running ? "" : "bad"}`;
  setText("setupDeviceName", device.name || "本地盒子");
  setText("setupDeviceUrl", device.api_base_url || "-");
  renderYoloState();
  renderAlgorithmDemo();
  prefillCameraForm();
}

async function loadSetupNetwork() {
  const hasSetupNetworkUi = $("setupNetworkBadge") || $("setupNetworkName") || $("wifiSsidSelect");
  if (!hasSetupNetworkUi) return;
  const network = await api("/api/setup/network");
  state.setupNetwork = network;
  const hotspotMode = network.mode === "setup_hotspot";
  setText("setupNetworkBadge", network.connected ? "已联网" : hotspotMode ? "盒子热点" : "待配网");
  if ($("setupNetworkBadge")) $("setupNetworkBadge").className = `status-pill ${network.connected ? "" : hotspotMode ? "muted" : "bad"}`;
  setText("setupNetworkSummary", network.connected ? "盒子已经接入家庭网络" : "选择家里的 Wi-Fi，保存后回到“回家”App。");
  setText("setupNetworkName", network.connected ? (network.network_name || network.ssid || "家庭网络") : (network.hotspot_ssid || "GoHome"));
  setText("setupNetworkUrl", network.api_base_url || "-");
  setText("setupHotspotName", network.hotspot_ssid || "GoHome");
  await loadWifiNetworks().catch(() => null);
  updateWifiActionState();
}

async function loadWifiNetworks() {
  const select = $("wifiSsidSelect");
  if (!select) return;
  const result = await api("/api/setup/wifi/networks");
  if (!result.supported) {
    select.innerHTML = '<option value="">当前系统不支持页面扫描</option>';
    select.disabled = true;
    return;
  }
  if (!result.networks?.length) {
    select.innerHTML = '<option value="">没有扫描到 Wi-Fi</option>';
    return;
  }
  const current = state.setupNetwork?.ssid || "";
  select.innerHTML = result.networks.map((network) => `
    <option value="${escapeHtml(network.ssid)}" ${network.ssid === current ? "selected" : ""}>
      ${escapeHtml(network.ssid)} · ${network.signal || 0}%
    </option>
  `).join("");
  updateWifiActionState();
}

function updateWifiActionState() {
  const button = $("connectWifi");
  if (!button) return;
  const selected = $("wifiSsidSelect")?.value || "";
  const current = state.setupNetwork?.ssid || "";
  const connectedSameWifi = Boolean(current && selected && current === selected);
  if (connectedSameWifi) {
    button.innerHTML = '<span class="material-symbols-outlined">check_circle</span>已连接';
    button.classList.add("connected");
  } else {
    button.innerHTML = '<span class="material-symbols-outlined">wifi</span>连接';
    button.classList.remove("connected");
  }
}

async function connectWifi(button) {
  const ssid = $("wifiSsidSelect")?.value || "";
  const password = $("wifiPassword")?.value || "";
  if (!ssid) {
    showToast("请选择家庭 Wi-Fi");
    return;
  }
  if (state.setupNetwork?.ssid && state.setupNetwork.ssid === ssid && !password) {
    showToast("已经连接这个 Wi-Fi");
    updateWifiActionState();
    return;
  }
  setBusy(button, true);
  state.wifiConnecting = true;
  try {
    const result = await api("/api/setup/wifi/connect", {
      method: "POST",
      body: JSON.stringify({ ssid, password }),
    });
    state.setupNetwork = result.network;
    await loadSetupNetwork();
    showToast("家庭网络已连接");
    showWifiReconnectGuide(result.network);
  } catch (error) {
    if (/failed to fetch|networkerror|load failed|network request failed/i.test(error.message || "")) {
      showToast("盒子正在切换网络，稍后重新打开页面");
      showWifiReconnectGuide();
      return;
    }
    throw error;
  } finally {
    setBusy(button, false);
    state.wifiConnecting = false;
    updateWifiActionState();
  }
}

function showWifiReconnectGuide(network = state.setupNetwork) {
  const panel = $("wifiReconnectGuide");
  if (!panel) return;
  panel.classList.remove("hidden");
  if (network?.api_base_url) setText("setupNetworkUrl", network.api_base_url);
}

async function loadCameraPresets() {
  if (!($("cameraProfile") || $("cameraHost"))) return;
  state.cameraPresets = await api("/api/cameras/setup-presets");
  renderCameraProfiles();
  prefillCameraForm();
}

async function discoverCameras(button) {
  const list = $("cameraDiscoveryList");
  const hint = $("cameraDiscoveryHint");
  if (!list) return;
  setBusy(button, true);
  if (hint) hint.textContent = "扫描中";
  list.innerHTML = '<div class="empty-state compact">正在扫描局域网。</div>';
  try {
    const result = await api("/api/cameras/discover?limit=24");
    state.cameraDiscovery = result.cameras || [];
    renderCameraDiscovery();
  } finally {
    setBusy(button, false);
  }
}

function renderCameraDiscovery() {
  const list = $("cameraDiscoveryList");
  const hint = $("cameraDiscoveryHint");
  if (!list) return;
  if (hint) hint.textContent = state.cameraDiscovery.length ? `发现 ${state.cameraDiscovery.length} 台设备` : "未发现设备";
  if (!state.cameraDiscovery.length) {
    list.innerHTML = '<div class="empty-state compact">没有扫到摄像头。可直接填写摄像头 IP。</div>';
    return;
  }
  list.innerHTML = state.cameraDiscovery.map((camera) => `
    <button class="camera-discovery-item" type="button" data-host="${escapeHtml(camera.host)}" data-port="${escapeHtml(camera.port)}" data-path="${escapeHtml(camera.path || "/1/2")}">
      <span>${escapeHtml(camera.host)}</span>
      <strong>${escapeHtml((camera.open_ports || []).length ? `端口 ${(camera.open_ports || []).join(" / ")}` : `RTSP ${camera.port || 554}`)}</strong>
    </button>
  `).join("");
}

function applyDiscoveredCamera(button) {
  if (!button) return;
  setCameraMode("lan");
  if ($("cameraHost")) $("cameraHost").value = button.dataset.host || defaultCameraHost();
  if ($("cameraPort")) $("cameraPort").value = button.dataset.port || "554";
  setCameraStreamControls(button.dataset.path || "/1/2");
  if ($("cameraRoom")) $("cameraRoom").value ||= "客厅";
  syncCameraName();
  syncLanUrlPreview();
  updateCameraLimitState();
  resetCameraTestState();
  if ($("cameraPassword")) $("cameraPassword").focus();
  showToast("已填入摄像头 IP");
}

async function loadCameras(options = {}) {
  state.cameras = await api("/api/cameras");
  const current = selectedCamera();
  if (pageName === "cameras") {
    state.selectedCameraId = physicalCameras()[0]?.id || null;
  } else if (!current || !current.enabled || options.preferNetwork) {
    state.selectedCameraId = preferredCameraId(state.cameras);
  }
  renderCameraSelect();
  renderCameraList();
  renderSetupCameras();
  updateCameraLimitState();
  renderStream();
  if (pageName === "cameras") {
    stopLiveAnalysisLoop();
    resetCameraTestState();
    return;
  }
  if (state.selectedCameraId) {
    await loadSnapshot(state.selectedCameraId).catch(renderEmptySnapshot);
    await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
  } else {
    renderEmptySnapshot();
    renderEmptyEvaluation();
  }
  if (pageName === "algorithms") startLiveAnalysisLoop();
}

function updateCameraLimitState() {
  const count = physicalCameras().length;
  const remaining = Math.max(0, state.maxCameras - count);
  setText("cameraLimitHint", `已接入 ${count}/${state.maxCameras} 路摄像头，还可新增 ${remaining} 路。`);
  const submit = $("cameraForm")?.querySelector('button[type="submit"]');
  const target = normalizeStreamUrl(cameraPayloadPreviewUrl());
  const editingExisting = physicalCameras().some((camera) => normalizeStreamUrl(camera.stream_url) === target);
  if (submit) {
    submit.disabled = count >= state.maxCameras && !editingExisting;
    submit.innerHTML = submit.disabled
      ? '<span class="material-symbols-outlined">block</span>已达 3 路上限'
      : '<span class="material-symbols-outlined">check_circle</span>保存启用';
  }
}

function renderSetupCameras() {
  const list = $("setupCameraList");
  if (!list) return;
  const count = state.cameras.length;
  if (!count) {
    list.innerHTML = '<div class="empty-state">还没有摄像头。先添加客厅这一路。</div>';
    return;
  }
  list.innerHTML = `
    <div class="setup-count"><strong>${count}/3</strong><span>已接入摄像头</span></div>
    ${state.cameras.map((camera) => `
      <div class="setup-camera-item">
        <strong>${escapeHtml(cameraDisplayName(camera))} · ${escapeHtml(camera.room || "未设置")}</strong>
        <span>${escapeHtml(isDemoStreamUrl(camera.stream_url) ? "演示画面，可替换为真实摄像头" : cameraDisplayStatus(camera))}</span>
      </div>
    `).join("")}
  `;
}

function renderCameraSelect() {
  const select = $("cameraSelect");
  if (!select) return;
  select.innerHTML = state.cameras.length
    ? state.cameras.map((camera) => `
      <option value="${camera.id}" ${Number(camera.id) === Number(state.selectedCameraId) ? "selected" : ""}>
        ${escapeHtml(cameraDisplayName(camera))} · ${escapeHtml(camera.room || "未设置")}
      </option>
    `).join("")
    : '<option value="">还没有摄像头</option>';
}

function renderCameraList() {
  const list = $("cameraList");
  if (!list) return;
  const cameras = physicalCameras();
  if (!cameras.length) {
    list.innerHTML = '<div class="empty-state">还没有摄像头。添加后会在这里显示。</div>';
    return;
  }
  list.innerHTML = cameras.map((camera) => {
    const active = Number(camera.id) === Number(state.selectedCameraId);
    const typeLabel = isDemoStreamUrl(camera.stream_url) ? "演示" : isLocalStreamUrl(camera.stream_url) ? "本机" : "局域网";
    return `
      <article class="camera-row ${active ? "active" : ""} ${camera.enabled ? "" : "disabled"}">
        <div>
          <h3>${escapeHtml(cameraDisplayName(camera))} · ${escapeHtml(camera.room || "未设置房间")}
            <span class="camera-badge">${typeLabel}</span>
            ${camera.enabled ? "" : '<span class="camera-badge muted">已禁用</span>'}
          </h3>
          <p>${escapeHtml(cameraDisplayStatus(camera))}</p>
        </div>
        <div class="row-actions">
          <button class="secondary-button" type="button" data-action="test" data-id="${camera.id}">测试</button>
          <button class="ghost-button" type="button" data-action="toggle" data-id="${camera.id}" data-enabled="${camera.enabled ? "1" : "0"}">${camera.enabled ? "禁用" : "启用"}</button>
          <button class="ghost-button danger" type="button" data-action="delete" data-id="${camera.id}">删除</button>
        </div>
      </article>
    `;
  }).join("");
}

function buildLanRtspUrl() {
  const host = $("cameraHost")?.value.trim() || "";
  const port = $("cameraPort")?.value.trim() || "554";
  if (!host) return "";
  return `rtsp://${host}:${port}${cameraStreamPath()}`;
}

function cameraPayloadPreviewUrl() {
  if (state.cameraMode === "lan") return buildLanRtspUrl();
  return $("cameraUrl")?.value.trim() || "";
}

function syncLanUrlPreview() {
  if (state.cameraMode === "lan" && $("cameraUrl")) $("cameraUrl").value = buildLanRtspUrl();
}

function setCameraMode(mode) {
  state.cameraMode = mode;
  for (const [id, active] of [["modeLan", mode === "lan"], ["modeRtsp", mode === "rtsp"], ["quickLocal", mode === "local"]]) {
    if ($(id)) $(id).classList.toggle("active", active);
  }
  const lan = mode === "lan";
  const manual = mode === "rtsp";
  if ($("cameraAdvancedFields")) {
    $("cameraAdvancedFields").classList.toggle("hidden", !lan);
    $("cameraAdvancedFields").hidden = !lan;
  }
  for (const id of ["cameraHostField", "cameraPasswordQuickField", "cameraPortField", "cameraUserField", "cameraChannelField", "cameraStreamField"]) {
    if ($(id)) {
      $(id).classList.toggle("hidden", !lan);
      $(id).hidden = !lan;
    }
  }
  if ($("cameraUrlField")) {
    $("cameraUrlField").classList.toggle("hidden", !manual);
    $("cameraUrlField").hidden = !manual;
  }
  if (mode === "lan") {
    if ($("cameraRoom")) $("cameraRoom").value ||= "客厅";
    syncCameraName();
    if ($("cameraHost")) $("cameraHost").value ||= defaultCameraHost();
    if ($("cameraPort")) $("cameraPort").value ||= "554";
    if ($("cameraUsername")) $("cameraUsername").value ||= "admin";
    setCameraStreamControls(cameraStreamPath());
    syncLanUrlPreview();
  }
  if (mode === "rtsp") {
    if ($("cameraRoom")) $("cameraRoom").value ||= "客厅";
    syncCameraName();
    if ($("cameraUrl")) $("cameraUrl").value = buildLanRtspUrl();
  }
  if (mode === "local") {
    if ($("cameraRoom")) $("cameraRoom").value = "客厅";
    if ($("cameraName")) $("cameraName").value = "客厅演示摄像头";
    if ($("cameraUrl")) $("cameraUrl").value = "demo:living_room";
  }
  updateCameraLimitState();
}

function cameraPayloadFromForm() {
  syncCameraName();
  const name = $("cameraName").value.trim();
  const room = $("cameraRoom").value.trim();
  if (state.cameraMode === "lan") {
    const streamUrl = buildLanRtspUrl();
    if (!streamUrl) throw new Error("请填写摄像头 IP");
    const password = $("cameraPasswordQuick")?.value || $("cameraPassword")?.value || "";
    return {
      name: name || `${room || "客厅"}摄像头`,
      room,
      stream_url: streamUrl,
      username: $("cameraUsername").value.trim() || null,
      password: password || null,
      enabled: true,
    };
  }
  const streamUrl = $("cameraUrl").value.trim();
  if (!streamUrl) throw new Error("请填写视频地址");
  return {
    name: name || (state.cameraMode === "local" ? "客厅演示摄像头" : `${room || "客厅"}摄像头`),
    room,
    stream_url: streamUrl,
    username: null,
    password: null,
    enabled: true,
  };
}

async function testCameraConnection(button) {
  setBusy(button, true);
  resetCameraTestState("正在验证摄像头连接。");
  try {
    const payload = cameraPayloadFromForm();
    const result = await api("/api/cameras/test-connection", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (pageName === "cameras") {
      renderCameraTestResult("ok", "连接正常", `已抓到 ${result.width}x${result.height} 验证帧，保存后启用这路摄像头。`);
    } else {
      const snapshot = {
        ...(result.snapshot || {}),
        width: result.width,
        height: result.height,
        analysis: result.analysis || {},
      };
      renderSnapshot(snapshot);
    }
    showToast(`连接正常：${result.width}x${result.height}`);
  } catch (error) {
    resetCameraTestState("连接失败。请检查 IP、密码、端口或切换主副码流。", "bad");
    throw error;
  } finally {
    setBusy(button, false);
  }
}

async function saveCamera(payload) {
  const target = normalizeStreamUrl(payload.stream_url);
  const existing = state.cameras.find((camera) => normalizeStreamUrl(camera.stream_url) === target);
  if (!existing && !isDemoStreamUrl(payload.stream_url) && physicalCameras().length >= state.maxCameras) {
    throw new Error("最多只能接入 3 路摄像头");
  }
  const camera = existing
    ? await api(`/api/cameras/${existing.id}`, { method: "PATCH", body: JSON.stringify(payload) })
    : await api("/api/cameras", { method: "POST", body: JSON.stringify(payload) });
  state.selectedCameraId = camera.id;
  showToast(existing ? "摄像头已更新" : "摄像头已连接");
}

async function testCamera(cameraId, button) {
  setBusy(button, true);
  try {
    const result = await api(`/api/cameras/${cameraId}/test`, { method: "POST" });
    state.selectedCameraId = cameraId;
    await loadCameras();
    if (pageName === "cameras") {
      renderCameraTestResult("ok", "连接正常", `已抓到 ${result.width}x${result.height} 验证帧。`);
    } else {
      renderSnapshot(result.snapshot);
    }
    showToast(`连接正常：${result.width}x${result.height}`);
  } finally {
    setBusy(button, false);
  }
}

async function updateCamera(cameraId, payload) {
  return api(`/api/cameras/${cameraId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

async function deleteCamera(cameraId) {
  return api(`/api/cameras/${cameraId}`, { method: "DELETE" });
}

function renderStream() {
  const stream = $("mjpegStream");
  if (!stream) return;
  const empty = $("streamEmpty");
  const camera = selectedCamera();
  clearTimeout(state.streamMaskTimer);
  if (!camera) {
    stopLiveAnalysisLoop();
    stream.removeAttribute("src");
    if (empty) {
      empty.style.display = "grid";
      empty.querySelector("p").textContent = "请选择摄像头";
    }
    setText("streamStatus", "未选择摄像头");
    setText("streamCamera", "无摄像头");
    return;
  }
  if (empty) {
    empty.style.display = "grid";
    empty.querySelector("p").textContent = "视频流加载中";
  }
  stream.onerror = () => {
    clearTimeout(state.streamMaskTimer);
    if (empty) {
      empty.style.display = "grid";
      empty.querySelector("p").textContent = "视频流暂不可用";
    }
    setText("streamStatus", "视频流不可用");
  };
  stream.src = `/api/cameras/${camera.id}/stream.mjpg?fps=5&width=1280&height=720&quality=70&drop=4&t=${Date.now()}`;
  state.streamMaskTimer = setTimeout(() => {
    if (stream.getAttribute("src") && empty) empty.style.display = "none";
  }, 900);
  setText("streamStatus", "720p 实时视频");
  setText("streamCamera", `${cameraDisplayName(camera)} · ${camera.room || "未设置"}`);
}

function snapshotPeople(snapshot) {
  const people = snapshot?.analysis?.people;
  return Array.isArray(people) ? people : [];
}

function isPresenceCandidate(person) {
  const source = String(person?.source || "");
  return Boolean(person?.presence_candidate || source.startsWith("presence_"));
}

function presenceCandidateCount(snapshot) {
  return snapshotPeople(snapshot).filter(isPresenceCandidate).length;
}

function tagLabel(tag) {
  const labels = {
    black_screen: "黑屏/遮挡",
    low_motion: "低变化",
    person_detected: "检测到人",
    person_presence_candidate: "人体存在候选",
    no_person_detected: "暂未检测到人",
    fall_candidate: "疑似跌倒",
    fire_candidate: "疑似明火",
    meal_candidate: "用餐候选",
    stillness_candidate: "静止候选",
  };
  return labels[tag] || tag;
}

function imageFitRect(snapshot) {
  const stage = $("previewStage");
  const image = $("snapshotImage") || $("mjpegStream");
  if (!stage || !image) return null;
  const stageWidth = stage.clientWidth;
  const stageHeight = stage.clientHeight;
  const imageWidth = Number(snapshot?.width || image.naturalWidth || snapshot?.analysis?.image_width || 0);
  const imageHeight = Number(snapshot?.height || image.naturalHeight || snapshot?.analysis?.image_height || 0);
  if (!stageWidth || !stageHeight || !imageWidth || !imageHeight) return null;
  const scale = Math.min(stageWidth / imageWidth, stageHeight / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  return { left: (stageWidth - width) / 2, top: (stageHeight - height) / 2, width, height, imageWidth, imageHeight };
}

function renderDetectionOverlay(snapshot) {
  const overlay = $("detectionOverlay");
  if (!overlay) return;
  const rect = imageFitRect(snapshot);
  const people = snapshotPeople(snapshot);
  const boxes = people.length
    ? people.map((person, index) => {
        const [x1, y1, x2, y2] = person.bbox || [0, 0, 0, 0];
        const confidence = person.confidence ? ` · ${Math.round(person.confidence * 100)}%` : "";
        const mode = state.previewAlgorithm || "person";
        const presence = isPresenceCandidate(person);
        const kind = presence ? "presence" : person.fall_candidate ? "fall" : mode === "fall" ? "watch" : "person";
        const prefix = presence ? "人体存在" : mode === "person" ? "人形命中" : mode === "fall" ? "跌倒观察" : "人像";
        const label = `${prefix} ${index + 1}${confidence}`;
        return { bbox: [x1, y1, x2, y2], label: person.fall_candidate ? `${label} · 疑似跌倒` : label, kind };
      })
    : [];
  if (!snapshot || !rect || !boxes.length) {
    overlay.innerHTML = "";
    overlay.removeAttribute("style");
    return;
  }
  overlay.style.left = `${rect.left}px`;
  overlay.style.top = `${rect.top}px`;
  overlay.style.width = `${rect.width}px`;
  overlay.style.height = `${rect.height}px`;
  overlay.innerHTML = boxes.map((box) => {
    const [x1, y1, x2, y2] = box.bbox || [0, 0, 0, 0];
    const left = clamp((Number(x1) / rect.imageWidth) * 100, 0, 100);
    const top = clamp((Number(y1) / rect.imageHeight) * 100, 0, 100);
    const right = clamp((Number(x2) / rect.imageWidth) * 100, 0, 100);
    const bottom = clamp((Number(y2) / rect.imageHeight) * 100, 0, 100);
    const width = clamp(right - left, 0, 100 - left);
    const height = clamp(bottom - top, 0, 100 - top);
    return `
      <div class="detection-box ${escapeHtml(box.kind || "person")}" style="left:${left}%;top:${top}%;width:${width}%;height:${height}%">
        <span>${escapeHtml(box.label)}</span>
      </div>
    `;
  }).join("");
}

function renderSnapshot(snapshot) {
  state.latestSnapshot = snapshot;
  const analysis = snapshot?.analysis || {};
  const image = $("snapshotImage");
  if (image && snapshot.image_url) {
    image.onload = () => renderDetectionOverlay(snapshot);
    image.src = `${snapshot.image_url}?t=${Date.now()}`;
  }
  if ($("snapshotEmpty")) $("snapshotEmpty").style.display = "none";
  setText("snapshotTime", fmtTime(snapshot.captured_at));
  setText("streamFrameTime", fmtTime(snapshot.captured_at));
  setText("snapshotBrightness", fmtNumber(analysis.brightness ?? snapshot.brightness, 1));
  setText("snapshotContrast", fmtNumber(analysis.contrast, 1));
  setText("snapshotMotion", analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4));
  setText("snapshotPeople", snapshot.person_count ?? analysis.person_count ?? "-");
  setText("snapshotTags", snapshot.tags?.length ? snapshot.tags.map(tagLabel).join("，") : "正常");
  renderDetectionSummary(snapshot);
  renderDetectionOverlay(snapshot);
  renderAlgorithmHitStrip(snapshot);
  renderAlgorithmDemo(snapshot);
}

function renderDetectionSummary(snapshot) {
  const target = $("detectionSummary");
  if (!target) return;
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  const fallCandidate = Boolean(analysis.fall_candidate);
  const blackScreen = Boolean(analysis.black_screen);
  const backend = analysis.detector_backend || state.detectorBackend || "basic";
  const personCount = snapshot?.person_count ?? analysis.person_count ?? (people.length || "-");
  const baseTitle = fallCandidate
    ? "疑似跌倒"
    : blackScreen
      ? "画面异常"
      : people.length
        ? "检测到人"
        : backend === "demo"
          ? "演示检测"
          : "画面正常";
  const previewTitle = previewSummaryTitle(baseTitle, { analysis, people, blackScreen, fallCandidate });
  const title = previewTitle.title;
  const levelClass = previewTitle.level || (fallCandidate || blackScreen ? "bad" : people.length ? "" : "muted");
  const details = [
    `亮度 ${fmtNumber(analysis.brightness ?? snapshot?.brightness, 1)}`,
    `对比度 ${fmtNumber(analysis.contrast, 1)}`,
    `变化 ${analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4)}`,
    `人数 ${personCount}`,
  ];
  target.innerHTML = `<span class="status-pill ${levelClass}">${escapeHtml(title)}</span><p>${escapeHtml(details.join(" · "))}</p>`;
}

function previewSummaryTitle(baseTitle, context) {
  if (pageName !== "algorithms") return { title: baseTitle, level: "" };
  const mode = state.previewAlgorithm || "quality";
  if (mode === "quality") {
    return { title: context.blackScreen ? "画面异常" : "画面质量正常", level: context.blackScreen ? "bad" : "" };
  }
  if (mode === "person") {
    const presenceCount = context.people.filter(isPresenceCandidate).length;
    if (presenceCount && presenceCount === context.people.length) return { title: "人体存在候选", level: "muted" };
    return { title: context.people.length ? "检测到人" : "暂未检测到人", level: context.people.length ? "" : "muted" };
  }
  if (mode === "stillness") return { title: "久坐观察中", level: "muted" };
  if (mode === "fall") return { title: context.fallCandidate ? "疑似跌倒" : "跌倒风险演示", level: "bad" };
  if (mode === "meal") return { title: "用餐识别演示", level: "" };
  if (mode === "night") return { title: "夜间活动演示", level: "muted" };
  if (mode === "fire") {
    const fireScore = Number(context.analysis.fire_score || 0);
    return { title: fireScore >= 0.035 ? "火灾视觉线索" : "火灾应急演示", level: "bad" };
  }
  if (mode === "camera") return { title: context.blackScreen ? "摄像头异常" : "摄像头正常", level: context.blackScreen ? "bad" : "muted" };
  return { title: baseTitle, level: "" };
}

function backendLabel(snapshot = state.latestSnapshot) {
  const analysis = snapshot?.analysis || {};
  const backend = analysis.detector_backend || state.detectorBackend || "basic";
  const model = analysis.model_name || state.device?.yolo_model || "";
  if (analysis.presence_enhanced) return model ? `${model} + 存在增强` : "YOLO + 存在增强";
  if (backend === "yolo") return model || "YOLO";
  if (backend === "demo") return "演示视觉";
  return "基础视觉";
}

function selectedAlgorithmKey(mode = state.previewAlgorithm) {
  if (mode === "camera") return "quality";
  if (["meal", "night", "stillness"].includes(mode)) return "activity";
  return mode || "quality";
}

function algorithmHitState(snapshot) {
  const mode = state.previewAlgorithm || "quality";
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  const presenceCount = presenceCandidateCount(snapshot);
  const result = analysis.algorithm_results?.[selectedAlgorithmKey(mode)] || {};
  const personCount = Number(snapshot?.person_count ?? analysis.person_count ?? people.length ?? 0);
  const confidence = algorithmPeopleConfidence(snapshot);
  let hit = false;
  let level = "idle";
  let title = "等待检测";
  let detail = "选择摄像头后自动分析当前画面";
  let score = confidence ? `${confidence}%` : result.score !== undefined && result.score !== null ? `${Math.round(Number(result.score) * 100)}%` : "-";

  if (!snapshot) return { hit, level, title, detail, score, model: backendLabel(snapshot), latency: "-" };

  if (mode === "person") {
    hit = personCount > 0;
    level = hit ? presenceCount && presenceCount === personCount ? "watch" : "hit" : "idle";
    title = hit ? presenceCount && presenceCount === personCount ? `人体存在候选 ${personCount} 个` : `检测到 ${personCount} 人` : "暂未检测到人";
    detail = hit ? presenceCount ? "坐姿/半身增强框已叠加到画面" : "实时人像框已叠加到画面" : "当前帧没有人形框";
    score = confidence ? `${presenceCount ? "增强 " : ""}${confidence}%` : score;
  } else if (mode === "fall") {
    hit = Boolean(analysis.fall_candidate);
    level = hit ? "critical" : personCount > 0 ? "watch" : "idle";
    title = hit ? "疑似跌倒命中" : personCount > 0 ? "跌倒观察中" : "未检测到人";
    detail = hit ? "建议立即进入告警确认" : "需要连续帧复核姿态";
  } else if (mode === "fire") {
    hit = Boolean(analysis.fire_candidate);
    level = hit ? "critical" : "idle";
    title = hit ? "火灾线索命中" : "未命中火灾线索";
    detail = `火灾分数 ${fmtNumber(analysis.fire_score || 0, 4)}`;
    score = `${Math.round(clamp(Number(analysis.fire_score || 0) * 2800, 0, 98))}%`;
  } else if (mode === "meal") {
    hit = Boolean(analysis.meal_candidate);
    level = hit ? "hit" : personCount > 0 ? "watch" : "idle";
    title = hit ? "用餐动作命中" : personCount > 0 ? "动作观察中" : "未检测到人";
    detail = "结合人像、运动和时段判断";
  } else if (mode === "stillness") {
    hit = Boolean(analysis.stillness_candidate);
    level = hit ? "watch" : "idle";
    title = hit ? "静止候选" : "活动正常";
    detail = `变化 ${analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4)}`;
    score = algorithmMotionScore(snapshot, true) === null ? "-" : `${algorithmMotionScore(snapshot, true)}%`;
  } else if (mode === "night") {
    const brightness = Number(analysis.brightness ?? snapshot.brightness);
    hit = Number.isFinite(brightness) && brightness < 70 && Number(analysis.motion_score || 0) > 0.006;
    level = hit ? "watch" : "idle";
    title = hit ? "夜间活动命中" : "夜间规则待命";
    detail = `亮度 ${fmtNumber(brightness, 1)} · 变化 ${fmtNumber(analysis.motion_score, 4)}`;
  } else if (mode === "camera") {
    hit = Boolean(analysis.black_screen);
    level = hit ? "critical" : "hit";
    title = hit ? "摄像头异常" : "链路正常";
    detail = `亮度 ${fmtNumber(analysis.brightness ?? snapshot.brightness, 1)} · 对比度 ${fmtNumber(analysis.contrast, 1)}`;
  } else {
    hit = !analysis.black_screen;
    level = hit ? "hit" : "critical";
    title = hit ? "画面质量通过" : "画面质量异常";
    detail = `亮度 ${fmtNumber(analysis.brightness ?? snapshot.brightness, 1)} · 对比度 ${fmtNumber(analysis.contrast, 1)}`;
  }

  const latency = snapshot.live_elapsed_ms ?? snapshot.elapsed_ms ?? snapshot.analysis_elapsed_ms;
  return {
    hit,
    level,
    title,
    detail,
    score,
    model: backendLabel(snapshot),
    latency: latency === undefined || latency === null ? "轮询中" : `${latency}ms`,
  };
}

function renderAlgorithmHitStrip(snapshot = state.latestSnapshot) {
  const target = $("algorithmHitStrip");
  if (!target) return;
  const stateInfo = algorithmHitState(snapshot);
  target.dataset.level = stateInfo.level;
  const stage = $("previewStage");
  if (stage) {
    stage.classList.toggle("has-live-hit", ["hit", "critical", "watch"].includes(stateInfo.level));
    stage.dataset.hitLevel = stateInfo.level;
  }
  target.innerHTML = `
    <div class="algorithm-hit-card primary">
      <span>当前命中</span>
      <strong>${escapeHtml(stateInfo.title)}</strong>
      <small>${escapeHtml(stateInfo.detail)}</small>
    </div>
    <div class="algorithm-hit-card">
      <span>置信度</span>
      <strong>${escapeHtml(stateInfo.score)}</strong>
      <small>${escapeHtml(stateInfo.model)}</small>
    </div>
    <div class="algorithm-hit-card">
      <span>分析延迟</span>
      <strong>${escapeHtml(stateInfo.latency)}</strong>
      <small>${snapshot ? escapeHtml(fmtTime(snapshot.captured_at)) : "等待当前帧"}</small>
    </div>
  `;
}

function renderEmptySnapshot() {
  state.latestSnapshot = null;
  if ($("snapshotImage")) $("snapshotImage").removeAttribute("src");
  if ($("snapshotEmpty")) $("snapshotEmpty").style.display = "grid";
  if ($("detectionOverlay")) $("detectionOverlay").innerHTML = "";
  for (const id of ["snapshotTime", "streamFrameTime", "snapshotBrightness", "snapshotContrast", "snapshotMotion", "snapshotPeople", "snapshotTags"]) {
    setText(id, "-");
  }
  renderAlgorithmHitStrip(null);
  renderAlgorithmDemo(null);
}

function renderCameraTestResult(level, title, message) {
  const target = $("cameraTestResult");
  if (!target) return;
  const dotClass = level === "ok" ? "ok" : level === "bad" ? "bad" : "muted";
  target.innerHTML = `
    <span class="status-dot ${dotClass}"></span>
    <div>
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

function resetCameraTestState(message = "点击“测试连接”只验证拉流，不保存配置。", level = "muted") {
  if (pageName !== "cameras") return;
  const title = level === "bad" ? "测试失败" : "未测试";
  renderCameraTestResult(level, title, message);
}

async function loadSnapshot(cameraId) {
  const snapshot = await api(`/api/cameras/${cameraId}/snapshot/latest`);
  renderSnapshot(snapshot);
}

function liveAnalysisDelay() {
  const mode = state.previewAlgorithm || "person";
  if (mode === "person") return 1800;
  if (["fall", "fire"].includes(mode)) return 2200;
  return 2600;
}

function stopLiveAnalysisLoop() {
  clearTimeout(state.liveAnalysisTimer);
  state.liveAnalysisTimer = null;
  state.liveAnalysisBusy = false;
}

function scheduleLiveAnalysis(delay = liveAnalysisDelay()) {
  if (pageName !== "algorithms") return;
  clearTimeout(state.liveAnalysisTimer);
  state.liveAnalysisTimer = setTimeout(() => {
    loadLiveAnalysis().catch(() => null);
  }, delay);
}

function startLiveAnalysisLoop() {
  if (pageName !== "algorithms") return;
  clearTimeout(state.liveAnalysisTimer);
  if (!state.selectedCameraId) {
    renderAlgorithmHitStrip(null);
    return;
  }
  loadLiveAnalysis().catch(() => null);
}

async function loadLiveAnalysis() {
  if (pageName !== "algorithms" || !state.selectedCameraId) return;
  if (document.hidden) {
    scheduleLiveAnalysis(3200);
    return;
  }
  if (state.liveAnalysisBusy) return;
  state.liveAnalysisBusy = true;
  setText("streamStatus", "实时分析中");
  try {
    const result = await api(`/api/cameras/${state.selectedCameraId}/analysis/live?algorithm=${encodeURIComponent(state.previewAlgorithm || "person")}`, {
      method: "POST",
    });
    const snapshot = {
      ...(result.snapshot || {}),
      analysis: result.analysis || result.snapshot?.analysis || {},
      live_elapsed_ms: result.elapsed_ms,
    };
    state.liveAnalysisErrorShown = false;
    renderSnapshot(snapshot);
    await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
    setText("streamStatus", "实时识别中");
  } catch (error) {
    setText("streamStatus", "识别暂不可用");
    if (!state.liveAnalysisErrorShown) {
      showToast(userSafeError(error.message || "实时识别失败"));
      state.liveAnalysisErrorShown = true;
    }
  } finally {
    state.liveAnalysisBusy = false;
    scheduleLiveAnalysis();
  }
}

async function captureSelected(button) {
  if (!state.selectedCameraId) {
    showToast("请先选择摄像头");
    return;
  }
  setBusy(button, true);
  try {
    const result = await api(`/api/cameras/${state.selectedCameraId}/capture`, { method: "POST" });
    renderSnapshot(result.snapshot);
    await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
    showToast(`抓到 ${result.width}x${result.height} 验证帧`);
  } finally {
    setBusy(button, false);
  }
}

async function loadEvaluation(cameraId) {
  const evaluation = await api(`/api/cameras/${cameraId}/evaluation/latest`);
  renderEvaluation(evaluation);
}

function renderEvaluation(evaluation) {
  if (!$("ruleEvaluation")) return;
  const candidates = Array.isArray(evaluation?.candidates) ? evaluation.candidates : [];
  const evalState = evaluation?.state || {};
  const hasCandidates = candidates.length > 0;
  const candidateText = hasCandidates
    ? candidates.map((candidate) => candidate.summary).join("；")
    : "当前检测结果正常。";
  $("ruleEvaluation").innerHTML = `
    <div>
      <span class="status-pill ${hasCandidates ? "bad" : ""}">${hasCandidates ? `${candidates.length} 条提醒` : "状态正常"}</span>
      <p>${escapeHtml(candidateText)} · 无人 ${escapeHtml(fmtDuration(evalState.no_person_seconds))} · 无变化 ${escapeHtml(fmtDuration(evalState.no_motion_seconds))}</p>
    </div>
  `;
}

function renderEmptyEvaluation() {
  if (!$("ruleEvaluation")) return;
  $("ruleEvaluation").innerHTML = `
    <div>
      <span class="status-pill muted">等待检测</span>
      <p>还没有检测状态，抓帧或等待下一轮。</p>
    </div>
  `;
}

const previewAlgorithmCopy = {
  quality: "画面质量：亮度、对比度、运动变化。",
  person: "人形 / 无人：实时框选画面里的人像并显示置信度。",
  stillness: "久坐 / 静止：看时间窗和画面变化。",
  fall: "跌倒检测：识别疑似倒地姿态并触发告警通知。",
  meal: "用餐：结合时段、区域和姿态线索。",
  night: "夜间活动：结合时段和运动变化。",
  fire: "火灾：识别明火视觉线索，命中后触发应急联系人。",
  camera: "摄像头异常：离线、黑屏、遮挡、低质量。",
};

const algorithmDemoProfiles = {
  quality: {
    title: "画面质量",
    badge: "真实规则",
    summary: "循环观察亮度、对比度和画面变化，过滤黑屏、遮挡、花屏和低质量帧。",
  },
  person: {
    title: "人形 / 无人",
    badge: "模型识别",
    summary: "框选画面中的人形区域，持续判断“有人、无人、离开时间”。",
  },
  stillness: {
    title: "久坐 / 静止",
    badge: "时间窗",
    summary: "把连续低变化画面聚合成时间窗，用于判断久坐、发呆和长时间无活动。",
  },
  fall: {
    title: "跌倒检测",
    badge: "高优先级",
    summary: "识别人体低位横向姿态，命中后进入报警候选并触发应急流程。",
  },
  meal: {
    title: "用餐 / 动作识别",
    badge: "场景识别",
    summary: "结合餐桌区域、人物姿态和时间段，判断用餐、喝水、起身等生活动作。",
  },
  night: {
    title: "夜间活动",
    badge: "夜间规则",
    summary: "在低光照时间段观察移动轨迹，识别夜间起身、徘徊和异常活动。",
  },
  fire: {
    title: "火灾应急报警",
    badge: "应急通道",
    summary: "识别明火/强橙红闪烁视觉线索，命中后走更高优先级报警。",
  },
  camera: {
    title: "摄像头异常",
    badge: "链路诊断",
    summary: "检测离线、黑屏、遮挡、低质量和持续花屏，避免误判成老人异常。",
  },
};

function algorithmDemoVideoSrc(mode) {
  const safeMode = String(mode || "quality").replace(/[^a-z0-9_-]/gi, "");
  return `/admin/assets/algorithm-demos/${safeMode}.webm`;
}

function algorithmDemoMedia(mode) {
  const src = algorithmDemoVideoSrc(mode);
  return `
    <div class="algorithm-demo-media">
      <video class="algorithm-demo-video" src="${escapeHtml(src)}" muted autoplay loop playsinline preload="metadata" aria-label="算法循环动效"></video>
    </div>
  `;
}

function algorithmEvidenceLine(mode, snapshot) {
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  if (!snapshot) return "等待抓帧后显示真实指标。";
  if (mode === "quality" || mode === "camera") {
    return `真实指标：亮度 ${fmtNumber(analysis.brightness ?? snapshot.brightness, 1)}，对比度 ${fmtNumber(analysis.contrast, 1)}，变化 ${analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4)}。`;
  }
  if (mode === "person") {
    const confidence = people.map((person) => Number(person.confidence || 0)).filter(Boolean).sort((a, b) => b - a)[0];
    const presenceCount = people.filter(isPresenceCandidate).length;
    if (presenceCount) return `真实指标：人体存在候选 ${presenceCount} 个，增强置信度 ${confidence ? Math.round(confidence * 100) : "-"}%。`;
    return confidence ? `真实指标：检测到 ${people.length} 人，最高置信度 ${Math.round(confidence * 100)}%。` : `真实指标：当前人数 ${snapshot.person_count ?? analysis.person_count ?? 0}。`;
  }
  if (mode === "fire") {
    return `真实指标：火灾分数 ${fmtNumber(analysis.fire_score || 0, 4)}，亮度 ${fmtNumber(analysis.brightness ?? snapshot.brightness, 1)}。`;
  }
  if (mode === "fall") {
    return `真实指标：跌倒候选 ${analysis.fall_candidate ? "命中" : "未命中"}，人数 ${snapshot.person_count ?? analysis.person_count ?? 0}。`;
  }
  return `真实指标：变化 ${analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4)}，人数 ${snapshot.person_count ?? analysis.person_count ?? 0}。`;
}

function algorithmAccuracyLine(mode, snapshot) {
  const backend = state.detectorBackend || "basic";
  if (!snapshot) {
    return "准确率口径：抓帧后显示当前帧可信度；正式准确率需要用测试集评估。";
  }
  if (snapshot?.analysis?.model_status === "model_error") {
    return `准确率口径：模型未就绪，${snapshot.analysis.model_message || "请检查 YOLO 依赖和模型文件"}。`;
  }
  if (["quality", "stillness", "camera"].includes(mode)) {
    return "准确率口径：规则类检测看阈值和连续帧复核，当前数值可直接用于调参。";
  }
  if (backend === "yolo") {
    if (snapshot?.analysis?.presence_enhanced) {
      return "准确率口径：YOLO 高置信未命中，本帧启用坐姿/半身人体存在增强；正式报警仍需要连续帧复核。";
    }
    return "准确率口径：YOLO 模型已启用，以模型置信度和连续帧复核作为主要依据。";
  }
  if (snapshot?.analysis?.detector_backend === "demo") {
    return "准确率口径：当前为演示检测，适合讲解效果；正式识别需接入 YOLO / MediaPipe 模型。";
  }
  return "准确率口径：当前 basic 模式只做基础视觉信号，动效为演示示意；正式模型接入后显示模型置信度。";
}

function algorithmQualityScore(snapshot) {
  const analysis = snapshot?.analysis || {};
  if (!snapshot) return null;
  if (analysis.black_screen) return 18;
  const brightness = Number(analysis.brightness ?? snapshot.brightness);
  const contrast = Number(analysis.contrast);
  const motion = Number(analysis.motion_score);
  const brightnessScore = Number.isFinite(brightness) ? 100 - Math.min(90, Math.abs(brightness - 122) * .72) : 72;
  const contrastScore = Number.isFinite(contrast) ? clamp(contrast * 2.4, 0, 100) : 70;
  const motionScore = Number.isFinite(motion) ? clamp(motion * 5200, 28, 100) : 66;
  return Math.round(clamp(brightnessScore * .44 + contrastScore * .36 + motionScore * .2, 0, 98));
}

function algorithmMotionScore(snapshot, inverse = false) {
  const motion = Number(snapshot?.analysis?.motion_score);
  if (!Number.isFinite(motion)) return null;
  const normalized = clamp(motion / .035, 0, 1);
  return Math.round((inverse ? 1 - normalized : normalized) * 100);
}

function algorithmPeopleConfidence(snapshot) {
  const people = snapshotPeople(snapshot);
  const confidence = people
    .map((person) => Number(person.confidence || 0))
    .filter(Boolean)
    .sort((a, b) => b - a)[0];
  return confidence ? Math.round(confidence * 100) : null;
}

function algorithmDemoMetric(mode, snapshot) {
  if (!snapshot) return { label: "当前帧", value: "--", tone: "muted" };
  const analysis = snapshot.analysis || {};
  if (mode === "quality") {
    const score = algorithmQualityScore(snapshot);
    return { label: "画面通过率", value: `${score}%`, tone: score >= 65 ? "ok" : "bad" };
  }
  if (mode === "camera") {
    const score = algorithmQualityScore(snapshot);
    return { label: "链路健康度", value: `${score}%`, tone: score >= 65 ? "ok" : "bad" };
  }
  if (mode === "person") {
    const confidence = algorithmPeopleConfidence(snapshot);
    const presenceCount = presenceCandidateCount(snapshot);
    return confidence
      ? { label: presenceCount ? "存在置信度" : "模型置信度", value: `${confidence}%`, tone: presenceCount ? "muted" : "ok" }
      : { label: "当前人数", value: `${snapshot.person_count ?? analysis.person_count ?? 0}`, tone: "muted" };
  }
  if (mode === "stillness") {
    const score = algorithmMotionScore(snapshot, true);
    return score === null
      ? { label: "静止可信度", value: "--", tone: "muted" }
      : { label: "静止可信度", value: `${score}%`, tone: score >= 72 ? "ok" : "muted" };
  }
  if (mode === "fall") {
    const confidence = algorithmPeopleConfidence(snapshot);
    const score = analysis.fall_candidate ? Math.max(confidence || 0, 86) : confidence ? Math.min(confidence, 58) : 32;
    return { label: "跌倒候选", value: `${score}%`, tone: analysis.fall_candidate ? "bad" : "muted" };
  }
  if (mode === "meal") {
    const motionScore = algorithmMotionScore(snapshot, false);
    const hasPerson = Number(snapshot.person_count ?? analysis.person_count ?? 0) > 0;
    const score = Math.round(clamp((motionScore ?? 45) * .38 + (hasPerson ? 46 : 18), 0, 92));
    return { label: "动作线索", value: `${score}%`, tone: hasPerson ? "ok" : "muted" };
  }
  if (mode === "night") {
    const brightness = Number(analysis.brightness ?? snapshot.brightness);
    const lowLight = Number.isFinite(brightness) ? clamp((120 - brightness) / 100, 0, 1) : .42;
    const motion = clamp((algorithmMotionScore(snapshot, false) ?? 30) / 100, 0, 1);
    const score = Math.round(clamp((lowLight * .52 + motion * .48) * 100, 0, 96));
    return { label: "夜间活动", value: `${score}%`, tone: score >= 62 ? "ok" : "muted" };
  }
  if (mode === "fire") {
    const fireScore = Number(analysis.fire_score || 0);
    const score = Math.round(clamp(fireScore * 2800, analysis.fire_candidate ? 82 : 12, 98));
    return { label: "火焰线索", value: `${score}%`, tone: analysis.fire_candidate || fireScore >= .035 ? "bad" : "muted" };
  }
  return { label: "当前帧", value: "--", tone: "muted" };
}

function renderAlgorithmDemo(snapshot = state.latestSnapshot) {
  const target = $("algorithmDemo");
  if (!target || pageName !== "algorithms") return;
  const mode = state.previewAlgorithm || "quality";
  const profile = algorithmDemoProfiles[mode] || algorithmDemoProfiles.quality;
  const metric = algorithmDemoMetric(mode, snapshot);
  target.className = `algorithm-demo-card demo-mode-${mode}`;
  target.innerHTML = `
    <div class="algorithm-demo-head">
      <div>
        <span>循环动效示意</span>
        <strong>${escapeHtml(profile.title)}</strong>
      </div>
      <div class="algorithm-demo-head-side">
        <em>${escapeHtml(profile.badge)}</em>
        <div class="algorithm-demo-metric ${escapeHtml(metric.tone)}">
          <span>${escapeHtml(metric.label)}</span>
          <strong>${escapeHtml(metric.value)}</strong>
        </div>
      </div>
    </div>
    ${algorithmDemoMedia(mode)}
    <div class="algorithm-demo-copy">
      <p>${escapeHtml(profile.summary)}</p>
      <span>${escapeHtml(algorithmEvidenceLine(mode, snapshot))}</span>
      <span>${escapeHtml(algorithmAccuracyLine(mode, snapshot))}</span>
    </div>
  `;
  const video = target.querySelector(".algorithm-demo-video");
  if (video) {
    const markVideoError = () => {
      target.classList.add("video-error");
    };
    video.addEventListener("error", () => {
      markVideoError();
    }, { once: true });
    video.play?.().catch(markVideoError);
  }
}

function updatePreviewAlgorithmInfo() {
  const value = $("previewAlgorithm")?.value || "quality";
  state.previewAlgorithm = value;
  setText("previewModeInfo", previewAlgorithmCopy[value] || previewAlgorithmCopy.quality);
  renderAlgorithmHitStrip(state.latestSnapshot);
  renderAlgorithmDemo(state.latestSnapshot);
  renderDetectionOverlay(state.latestSnapshot);
  if (pageName === "algorithms") startLiveAnalysisLoop();
}

async function loadEvents() {
  const list = $("eventList");
  if (!list) return;
  const params = new URLSearchParams({ limit: "8" });
  if (state.eventFilter === "open") params.set("acknowledged", "false");
  if (state.eventFilter === "done") params.set("acknowledged", "true");
  const events = await api(`/api/events?${params.toString()}`);
  if (!events.length) {
    list.innerHTML = '<div class="empty-state">当前没有告警事件。</div>';
    return;
  }
  list.innerHTML = events.map((event) => `
    <article class="event-item ${event.acknowledged ? "done" : ""}">
      <div class="event-mark ${event.level === "critical" ? "critical" : ""}"></div>
      <div class="event-body">
        <div class="event-title-row">
          <strong>${escapeHtml(event.summary)}</strong>
          <span>${event.acknowledged ? "已处理" : "未处理"}</span>
        </div>
        <p>${escapeHtml(event.type)} · ${escapeHtml(event.camera_name || "未知摄像头")} · ${fmtTime(event.occurred_at)}</p>
        <div class="event-actions">
          ${event.snapshot_url ? `<button class="ghost-button" type="button" data-event-action="snapshot" data-url="${escapeHtml(event.snapshot_url)}">看截图</button>` : ""}
          ${event.acknowledged
            ? `<button class="ghost-button" type="button" data-event-action="reopen" data-id="${event.id}">恢复未处理</button>`
            : `<button class="secondary-button" type="button" data-event-action="ack" data-id="${event.id}">标记已处理</button>`}
          <button class="ghost-button" type="button" data-event-action="false_positive" data-id="${event.id}">误报</button>
        </div>
      </div>
    </article>
  `).join("");
}

function candidateStatusLabel(status) {
  if (status === "promoted") return "已提升";
  if (status === "suppressed") return "已抑制";
  if (status === "new") return "待处理";
  return status || "未知";
}

async function loadCandidates() {
  const list = $("candidateList");
  if (!list) return;
  let candidates = [];
  try {
    candidates = await api("/api/event-candidates?limit=12");
  } catch (error) {
    list.innerHTML = `<div class="empty-state">记录暂不可用：${escapeHtml(error.message || "加载失败")}。</div>`;
    throw error;
  }
  if (!candidates.length) {
    list.innerHTML = '<div class="empty-state">当前没有提醒记录。</div>';
    return;
  }
  list.innerHTML = candidates.map((candidate) => {
    const rule = candidate.payload?.rule || {};
    const observed = rule.observed?.no_person_seconds || rule.observed?.no_motion_seconds || null;
    const threshold = rule.threshold?.no_person_seconds || rule.threshold?.no_motion_seconds || null;
    const explanation = rule.reason
      || candidate.promoted_event_summary
      || candidate.summary
      || "提醒记录";
    const meta = [
      candidate.event_type,
      candidate.camera_name || candidate.camera_room || `摄像头 ${candidate.camera_id}`,
      fmtTime(candidate.updated_at || candidate.created_at),
    ].filter(Boolean).join(" · ");
    const detail = [
      observed ? `观测 ${fmtDuration(observed)}` : "",
      threshold ? `阈值 ${fmtDuration(threshold)}` : "",
      candidate.promoted_event_id ? `事件 #${candidate.promoted_event_id}` : "",
    ].filter(Boolean).join(" · ");
    return `
      <article class="event-item ${candidate.status === "promoted" ? "done" : ""}">
        <div class="event-mark ${candidate.status === "suppressed" ? "" : "critical"}"></div>
        <div class="event-body">
          <div class="event-title-row">
            <strong>${escapeHtml(explanation)}</strong>
            <span>${escapeHtml(candidateStatusLabel(candidate.status))}</span>
          </div>
          <p>${escapeHtml(meta)}</p>
          ${detail ? `<p>${escapeHtml(detail)}</p>` : ""}
        </div>
      </article>
    `;
  }).join("");
}

async function updateEvent(eventId, payload) {
  await api(`/api/events/${eventId}`, { method: "PATCH", body: JSON.stringify(payload) });
  await loadEvents();
}

async function clearDoneEvents() {
  const result = await api("/api/events?scope=acknowledged", { method: "DELETE" });
  showToast(`已清理 ${result.deleted} 条已处理告警`);
  await loadEvents();
}

async function loadRules() {
  const rules = await api("/api/rules");
  if ($("captureInterval")) $("captureInterval").value = rules.capture_interval_seconds;
  if ($("motionThreshold")) $("motionThreshold").value = rules.motion_threshold;
  if ($("blackBrightnessThreshold")) $("blackBrightnessThreshold").value = rules.black_brightness_threshold;
  if ($("blackContrastThreshold")) $("blackContrastThreshold").value = rules.black_contrast_threshold;
  if ($("yoloConfidence")) $("yoloConfidence").value = rules.yolo_confidence;
  if ($("noMotionSeconds")) $("noMotionSeconds").value = rules.no_motion_seconds;
  if ($("noPersonSecondsInput")) $("noPersonSecondsInput").value = rules.no_person_seconds;
  for (const [id, key] of [
    ["offlineEnabled", "offline_enabled"],
    ["blackEnabled", "black_screen_enabled"],
    ["noMotionEnabled", "no_motion_enabled"],
    ["personDetectionEnabled", "person_detection_enabled"],
    ["fallDetectionEnabled", "fall_detection_enabled"],
    ["activityDetectionEnabled", "activity_detection_enabled"],
    ["fireDetectionEnabled", "fire_detection_enabled"],
    ["notificationEnabled", "notification_enabled"],
  ]) {
    if ($(id)) $(id).checked = Boolean(rules[key]);
  }
}

function renderYoloState() {
  const yoloEnabled = state.detectorBackend === "yolo";
  if ($("yoloHint")) {
    const model = state.device?.yolo_model || "yolo11n.pt";
    $("yoloHint").textContent = yoloEnabled
      ? `视觉模型已启用：${model}。人像检测只跑 person 类，适合 Pi5 实时预览。`
      : "当前为基础检测；需要设置 GOHOME_DETECTOR_BACKEND=yolo 才会跑人像模型。";
  }
}

async function saveRules(button) {
  setBusy(button, true);
  try {
    await api("/api/rules", {
      method: "PUT",
      body: JSON.stringify({
        capture_interval_seconds: Number($("captureInterval").value),
        motion_threshold: Number($("motionThreshold").value),
        black_brightness_threshold: Number($("blackBrightnessThreshold").value),
        black_contrast_threshold: Number($("blackContrastThreshold").value),
        yolo_confidence: $("yoloConfidence") ? Number($("yoloConfidence").value) : undefined,
        no_motion_seconds: Number($("noMotionSeconds").value),
        no_person_seconds: Number($("noPersonSecondsInput").value),
        offline_enabled: $("offlineEnabled").checked,
        black_screen_enabled: $("blackEnabled").checked,
        no_motion_enabled: $("noMotionEnabled").checked,
        person_detection_enabled: $("personDetectionEnabled").checked,
        fall_detection_enabled: $("fallDetectionEnabled").checked,
        activity_detection_enabled: Boolean($("activityDetectionEnabled")?.checked),
        fire_detection_enabled: Boolean($("fireDetectionEnabled")?.checked),
        notification_enabled: $("notificationEnabled").checked,
      }),
    });
    await loadRules();
    showToast("算法配置已保存");
  } finally {
    setBusy(button, false);
  }
}

async function refreshAll() {
  try {
    await Promise.all([
      loadDevice(),
      loadSetupNetwork().catch(() => null),
      loadCameraPresets().catch(() => null),
      loadRules().catch(() => null),
    ]);
    await loadCameras();
    await loadCandidates().catch(() => null);
  } catch (error) {
    showToast(userSafeError(error.message || "无法连接 edge-agent"));
  }
}

function bindEvents() {
  on("refreshAll", "click", refreshAll);
  on("captureSelected", "click", (event) => captureSelected(event.currentTarget).catch((error) => showToast(userSafeError(error.message))));
  on("saveRules", "click", (event) => saveRules(event.currentTarget).catch((error) => showToast(userSafeError(error.message))));
  on("refreshWifiNetworks", "click", (event) => {
    setBusy(event.currentTarget, true);
    loadWifiNetworks()
      .catch((error) => showToast(userSafeError(error.message)))
      .finally(() => setBusy(event.currentTarget, false));
  });
  on("connectWifi", "click", (event) => connectWifi(event.currentTarget).catch((error) => showToast(userSafeError(error.message))));
  on("wifiSsidSelect", "change", updateWifiActionState);
  on("discoverCameras", "click", (event) => discoverCameras(event.currentTarget).catch((error) => showToast(userSafeError(error.message))));
  on("testCameraConnection", "click", (event) => testCameraConnection(event.currentTarget).catch((error) => showToast(userSafeError(error.message))));
  on("clearDoneEvents", "click", () => clearDoneEvents().catch((error) => showToast(userSafeError(error.message))));
  on("eventFilter", "change", (event) => {
    state.eventFilter = event.target.value;
    loadEvents().catch((error) => showToast(userSafeError(error.message)));
  });
  on("cameraSelect", "change", async (event) => {
    state.selectedCameraId = Number(event.currentTarget.value);
    renderStream();
    await loadSnapshot(state.selectedCameraId).catch(renderEmptySnapshot);
    await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
    startLiveAnalysisLoop();
  });
  on("modeLan", "click", () => setCameraMode("lan"));
  on("modeRtsp", "click", () => setCameraMode("rtsp"));
  on("quickLocal", "click", () => setCameraMode("local"));
  on("previewAlgorithm", "change", updatePreviewAlgorithmInfo);
  on("cameraProfile", "change", applyCameraProfile);
  on("cameraRoom", "input", () => {
    syncCameraName();
    updateCameraLimitState();
    resetCameraTestState();
  });
  on("cameraPassword", "input", resetCameraTestState);
  on("cameraPasswordQuick", "input", () => {
    if ($("cameraPassword")) $("cameraPassword").value = $("cameraPasswordQuick").value;
    resetCameraTestState();
  });
  for (const id of ["cameraHost", "cameraPort", "cameraChannel", "cameraStream"]) {
    on(id, "input", () => {
      syncLanUrlPreview();
      updateCameraLimitState();
      resetCameraTestState();
    });
    on(id, "change", () => {
      syncLanUrlPreview();
      updateCameraLimitState();
      resetCameraTestState();
    });
  }
  on("cameraUrl", "input", updateCameraLimitState);
  const form = $("cameraForm");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = event.submitter;
      setBusy(button, true);
      try {
        await saveCamera(cameraPayloadFromForm());
        await loadCameras({ preferNetwork: true });
      } catch (error) {
        showToast(userSafeError(error.message));
      } finally {
        setBusy(button, false);
      }
    });
  }
  const cameraList = $("cameraList");
  if (cameraList) {
    cameraList.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const cameraId = Number(button.dataset.id);
      state.selectedCameraId = cameraId;
      try {
        if (button.dataset.action === "test") {
          await testCamera(cameraId, button);
        }
        if (button.dataset.action === "toggle") {
          const enabled = button.dataset.enabled !== "1";
          await updateCamera(cameraId, { enabled });
          showToast(enabled ? "摄像头已启用" : "摄像头已禁用");
          await loadCameras();
        }
        if (button.dataset.action === "delete") {
          if (!window.confirm("删除这个摄像头？历史截图和告警不会删除。")) return;
          await deleteCamera(cameraId);
          showToast("摄像头已删除");
          await loadCameras();
        }
      } catch (error) {
        showToast(userSafeError(error.message));
      }
    });
  }
  const discoveryList = $("cameraDiscoveryList");
  if (discoveryList) {
    discoveryList.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-host]");
      applyDiscoveredCamera(button);
    });
  }
  const eventList = $("eventList");
  if (eventList) {
    eventList.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-event-action]");
      if (!button) return;
      const action = button.dataset.eventAction;
      try {
        if (action === "snapshot") {
          window.open(`${button.dataset.url}?t=${Date.now()}`, "_blank", "noopener");
          return;
        }
        const eventId = Number(button.dataset.id);
        if (action === "ack") await updateEvent(eventId, { acknowledged: true, resolution: "handled" });
        if (action === "reopen") await updateEvent(eventId, { acknowledged: false });
        if (action === "false_positive") await updateEvent(eventId, { acknowledged: true, resolution: "false_positive" });
        showToast("事件状态已更新");
      } catch (error) {
        showToast(error.message);
      }
    });
  }
  window.addEventListener("resize", () => renderDetectionOverlay(state.latestSnapshot));
}

document.addEventListener("DOMContentLoaded", () => {
  hydrateAdminSession();
  bindEvents();
  if (pageName === "cameras") setCameraMode("lan");
  updatePreviewAlgorithmInfo();
  refreshAll();
  if (pageName === "cameras" && $("cameraDiscoveryList")) {
    setTimeout(() => discoverCameras($("discoverCameras")).catch(() => renderCameraDiscovery()), 400);
  }
  state.refreshTimer = setInterval(() => {
    if (pageName === "home" || pageName === "algorithms") {
      if (state.selectedCameraId) {
        loadSnapshot(state.selectedCameraId).catch(() => null);
        loadEvaluation(state.selectedCameraId).catch(() => null);
      }
      loadCandidates().catch(() => null);
    }
  }, 6000);
});
