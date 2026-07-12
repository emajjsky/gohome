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
  previewAlgorithm: "unified",
  maxCameras: 3,
  detectorBackend: "basic",
  latestSnapshot: null,
  latestEvaluation: null,
  cameraFormPrefilled: false,
  wifiConnecting: false,
  refreshTimer: null,
  streamMaskTimer: null,
  streamReconnectTimer: null,
  streamReconnectAttempts: 0,
  liveAnalysisTimer: null,
  liveAnalysisBusy: false,
  liveAnalysisErrorShown: false,
  candidateRecords: [],
  observationLogs: [],
  cloudVerifications: null,
  eventLogRecords: [],
  eventLogStatusFilter: "all",
  eventLogTypeFilter: "all",
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

function fmtPercent(value, digits = 0) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(digits)}%` : "-";
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
  if (!$("cameraHost")) return;
  state.cameraPresets = await api("/api/cameras/setup-presets");
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

function renderStream({ retry = false } = {}) {
  const stream = $("mjpegStream");
  if (!stream) return;
  const empty = $("streamEmpty");
  const camera = selectedCamera();
  clearTimeout(state.streamMaskTimer);
  clearTimeout(state.streamReconnectTimer);
  if (!retry) state.streamReconnectAttempts = 0;
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
    state.streamReconnectAttempts += 1;
    const cameraId = camera.id;
    const delay = Math.min(8000, 800 * (2 ** Math.min(state.streamReconnectAttempts - 1, 3)));
    state.streamReconnectTimer = setTimeout(() => {
      if (selectedCamera()?.id === cameraId) renderStream({ retry: true });
    }, delay);
  };
  stream.onload = () => {
    state.streamReconnectAttempts = 0;
    if (empty) empty.style.display = "none";
    setText("streamStatus", "实时视频已连接");
  };
  const streamProfile = pageName === "algorithms"
    ? { fps: 8, width: 768, height: 432, quality: 56, drop: 8, label: "低延迟实时视频" }
    : { fps: 6, width: 1280, height: 720, quality: 64, drop: 4, label: "720p 低延迟视频" };
  stream.src = `/api/cameras/${camera.id}/stream.mjpg?fps=${streamProfile.fps}&width=${streamProfile.width}&height=${streamProfile.height}&quality=${streamProfile.quality}&drop=${streamProfile.drop}&t=${Date.now()}`;
  state.streamMaskTimer = setTimeout(() => {
    if (stream.getAttribute("src") && empty) empty.style.display = "none";
  }, 900);
  setText("streamStatus", streamProfile.label);
  setText("streamCamera", `${cameraDisplayName(camera)} · ${camera.room || "未设置"}`);
}

function snapshotPeople(snapshot) {
  const people = snapshot?.analysis?.people;
  return Array.isArray(people) ? people : [];
}

function snapshotPets(snapshot) {
  const pets = snapshot?.analysis?.pets;
  return Array.isArray(pets) ? pets : [];
}

function snapshotPoses(snapshot) {
  const poses = snapshot?.analysis?.poses;
  return Array.isArray(poses)
    ? poses.filter((pose) => pose?.person_evidence_eligible !== false && !pose?.rejection_stage)
    : [];
}

function snapshotPoseEdges(snapshot) {
  const edges = snapshot?.analysis?.pose_skeleton_edges;
  return Array.isArray(edges) && edges.length
    ? edges
    : [
      ["left_shoulder", "right_shoulder"],
      ["left_shoulder", "left_elbow"],
      ["left_elbow", "left_wrist"],
      ["right_shoulder", "right_elbow"],
      ["right_elbow", "right_wrist"],
      ["left_shoulder", "left_hip"],
      ["right_shoulder", "right_hip"],
      ["left_hip", "right_hip"],
      ["left_hip", "left_knee"],
      ["left_knee", "left_ankle"],
      ["right_hip", "right_knee"],
      ["right_knee", "right_ankle"],
    ];
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
    person_detected: "有人",
    person_presence_candidate: "人体存在候选",
    pet_detected: "检测到宠物",
    pose_detected: "骨架确认",
    pose_tracked: "骨架跟踪",
    pose_validated_person: "骨架确认人形",
    pose_low_body: "低位姿态",
    pose_fall_candidate: "骨架跌倒观察",
    pose_hand_near_face: "手部接近面部",
    no_person_detected: "暂未检测到人",
    fall_candidate: "跌倒观察候选",
    fire_candidate: "火灾视觉线索",
    meal_candidate: "用餐观察候选",
    stillness_candidate: "静止观察候选",
    daze_candidate: "久坐观察候选",
  };
  return labels[tag] || tag;
}

function algorithmVisibleTags(snapshot, mode = state.previewAlgorithm || "quality") {
  const analysis = snapshot?.analysis || {};
  const sourceTags = [
    ...new Set([
      ...(Array.isArray(snapshot?.tags) ? snapshot.tags : []),
      ...(Array.isArray(analysis.tags) ? analysis.tags : []),
    ]),
  ];
  const allowlist = {
    unified: [
      "black_screen", "low_motion", "person_detected", "no_person_detected", "person_presence_candidate",
      "pose_detected", "pose_tracked", "pose_validated_person", "pose_low_body", "pose_fall_candidate",
      "pose_hand_near_face", "fall_candidate", "fire_candidate", "meal_candidate", "stillness_candidate",
      "daze_candidate",
    ],
    quality: ["black_screen", "low_motion"],
    person: ["person_detected", "no_person_detected", "person_presence_candidate", "pose_detected", "pose_tracked", "pose_validated_person"],
    stillness: ["stillness_candidate", "daze_candidate", "low_motion", "person_detected", "pose_detected", "pose_tracked"],
    fall: ["fall_candidate", "pose_fall_candidate", "pose_low_body", "person_detected", "pose_detected", "pose_tracked"],
    meal: ["meal_candidate", "pose_hand_near_face", "person_detected", "pose_detected", "pose_tracked"],
    night: ["person_detected", "low_motion"],
    fire: ["fire_candidate"],
    camera: ["black_screen", "low_motion"],
  };
  const allowed = new Set(allowlist[mode] || allowlist.quality);
  return sourceTags.filter((tag) => allowed.has(tag));
}

function algorithmNormalTagLabel(mode = state.previewAlgorithm || "quality", snapshot = state.latestSnapshot) {
  const analysis = snapshot?.analysis || {};
  if (!snapshot) return "-";
  if (mode === "unified") {
    if (analysis.black_screen) return "画面异常";
    if (analysis.fire_candidate || analysis.fire_event_candidate) return "火灾线索复核中";
    if (["suspect", "confirming", "confirmed"].includes(latestFallRuntime().stage)) return "跌倒过程复核中";
    return Number(snapshot.person_count ?? analysis.person_count ?? 0) > 0 ? "人物活动正常" : "当前无人";
  }
  if (mode === "person") return Number(snapshot.person_count ?? analysis.person_count ?? 0) > 0 ? "有人" : "无人";
  if (mode === "fall") return "未出现跌倒候选";
  if (mode === "meal") return "未形成用餐候选";
  if (mode === "stillness") return "活动正常";
  if (mode === "night") return "夜间规则待命";
  if (mode === "fire") return "未确认火灾线索";
  if (mode === "camera") return analysis.black_screen ? "摄像头异常" : "链路正常";
  return analysis.black_screen ? "质量异常" : "质量正常";
}

function overlayPeopleForMode(snapshot, mode = state.previewAlgorithm || "quality") {
  if (!["unified", "person", "fall", "meal", "stillness", "night"].includes(mode)) return [];
  const people = snapshotPeople(snapshot);
  if (mode === "unified") return people;
  if (mode === "fall") {
    return people.filter((person) => person.fall_candidate || String(person.source || "").startsWith("fall_") || String(person.method || "").includes("fall"));
  }
  if (mode === "person") return people;
  return people.filter((person) => person.pose_validated || person.source === "pose_person" || !isPresenceCandidate(person));
}

function shouldRenderPoseForMode(mode = state.previewAlgorithm || "quality") {
  return ["unified", "person", "fall", "meal", "stillness"].includes(mode);
}

const postureLabels = {
  standing: "站姿",
  sitting: "坐姿",
  lying: "躺姿",
  squatting: "蹲姿",
  low_body: "低位姿态",
  seated_or_half_body: "坐姿/半身",
  upper_body: "上半身",
  unknown: "姿态识别中",
};

const sceneLabels = {
  bed: "床",
  couch: "沙发",
  chair: "椅子",
  dining_table: "餐桌",
  tv: "电视",
};

function postureLabel(value) {
  const key = String(value || "unknown");
  return postureLabels[key] || key;
}

function sceneLabel(item) {
  const key = String(item?.label || "");
  return item?.label_zh || sceneLabels[key] || key || "场景目标";
}

function bboxIou(first, second) {
  if (!Array.isArray(first) || !Array.isArray(second) || first.length < 4 || second.length < 4) return 0;
  const [ax1, ay1, ax2, ay2] = first.map(Number);
  const [bx1, by1, bx2, by2] = second.map(Number);
  const intersection = Math.max(0, Math.min(ax2, bx2) - Math.max(ax1, bx1)) * Math.max(0, Math.min(ay2, by2) - Math.max(ay1, by1));
  const union = Math.max(1, (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection);
  return intersection / union;
}

function matchingPose(person, poses) {
  const trackId = String(person?.track_id || "");
  if (trackId) {
    const tracked = poses.find((pose) => String(pose?.track_id || "") === trackId);
    if (tracked) return tracked;
  }
  let best = null;
  let bestOverlap = 0;
  for (const pose of poses) {
    const overlap = bboxIou(person?.bbox, pose?.bbox);
    if (overlap > bestOverlap) {
      best = pose;
      bestOverlap = overlap;
    }
  }
  return bestOverlap >= 0.12 ? best : null;
}

function unifiedSceneTargets(snapshot) {
  const analysis = snapshot?.analysis || {};
  const zones = (analysis.scene_zones || []).filter((zone) => zone?.stable && Array.isArray(zone?.bbox));
  const objects = (analysis.scene_objects || []).filter((item) => Array.isArray(item?.bbox));
  const transient = objects.filter((item) => !zones.some((zone) => zone.label === item.label && bboxIou(zone.bbox, item.bbox) >= 0.35));
  return [
    ...zones.map((zone) => ({ ...zone, stable: true })),
    ...transient.map((item) => ({ ...item, stable: false })),
  ];
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
  const mode = state.previewAlgorithm || "quality";
  const people = overlayPeopleForMode(snapshot, mode);
  const pets = mode === "unified" ? snapshotPets(snapshot) : [];
  const poses = shouldRenderPoseForMode(mode) ? snapshotPoses(snapshot) : [];
  const fallRuntime = latestFallRuntime();
  const fallActive = ["suspect", "confirming", "confirmed"].includes(fallRuntime.stage);
  const sceneTargets = mode === "unified"
    ? unifiedSceneTargets(snapshot)
    : mode === "fall"
      ? (snapshot?.analysis?.scene_zones || []).filter((zone) => zone.stable && zone.zone_kind === "normal_lying_surface")
      : [];
  const sceneBoxes = sceneTargets.map((item) => ({
    bbox: item.bbox,
    label: item.stable
      ? `${sceneLabel(item)} · 场景已学习`
      : `${sceneLabel(item)}${item.confidence ? ` · ${Math.round(Number(item.confidence) * 100)}%` : ""}`,
    kind: "scene",
  }));
  const personBoxes = people.length
    ? people.map((person, index) => {
        const [x1, y1, x2, y2] = person.bbox || [0, 0, 0, 0];
        const confidence = person.confidence ? ` · ${Math.round(person.confidence * 100)}%` : "";
        const candidateScore = !person.confidence && person.candidate_score ? ` · 候选分 ${Math.round(person.candidate_score * 100)}%` : "";
        const presence = isPresenceCandidate(person);
        const poseValidated = Boolean(person.pose_validated || person.source === "pose_person");
        const tracked = person.pose_tracking_state === "cached";
        const matchesFallTarget = fallActive && bboxIou(person.bbox, fallRuntime.target?.bbox) >= 0.18;
        const kind = presence && !poseValidated ? "presence" : matchesFallTarget ? "fall" : "person";
        const pose = matchingPose(person, poses);
        const posture = pose ? ` · ${postureLabel(pose.posture)}` : "";
        const trackId = person.track_id || pose?.track_id;
        const identity = trackId ? `人物 ${String(trackId).split("-").pop()}` : `人物 ${index + 1}`;
        const prefix = presence && !poseValidated ? "人体候选" : identity;
        const label = `${prefix}${posture}${confidence}${candidateScore}`;
        return { bbox: [x1, y1, x2, y2], label: matchesFallTarget ? `${label} · 跌倒过程复核` : label, kind: tracked ? "tracked" : kind };
      })
    : [];
  const petBoxes = pets.map((pet) => ({
    bbox: pet.bbox,
    label: `${pet.label_zh || (pet.type === "dog" ? "狗" : "猫")}${pet.confidence ? ` · ${Math.round(Number(pet.confidence) * 100)}%` : ""}${pet.scene_zone_label_zh ? ` · ${pet.scene_zone_label_zh}` : ""}`,
    kind: "pet",
  }));
  const boxes = [...sceneBoxes, ...petBoxes, ...personBoxes];
  if (!snapshot || !rect) {
    overlay.innerHTML = "";
    overlay.removeAttribute("style");
    return;
  }
  overlay.style.left = `${rect.left}px`;
  overlay.style.top = `${rect.top}px`;
  overlay.style.width = `${rect.width}px`;
  overlay.style.height = `${rect.height}px`;
  const poseMarkup = renderPoseSkeleton(snapshot, rect);
  const boxMarkup = boxes.map((box) => {
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
  const analysis = snapshot?.analysis || {};
  const alerts = [];
  if (analysis.black_screen) alerts.push({ level: "critical", text: "摄像头画面异常" });
  if (analysis.fire_event_candidate || analysis.fire_candidate) alerts.push({ level: "critical", text: analysis.fire_event_candidate ? "火灾事件候选" : "火灾线索复核中" });
  if (fallActive) alerts.push({ level: "critical", text: fallRuntime.stage === "confirmed" ? "跌倒事件已确认" : "跌倒过程复核中" });
  const alertMarkup = alerts.length
    ? `<div class="perception-frame-alerts">${alerts.map((alert) => `<span class="${escapeHtml(alert.level)}">${escapeHtml(alert.text)}</span>`).join("")}</div>`
    : '<div class="perception-frame-alerts"><span class="normal">安全状态正常</span></div>';
  overlay.innerHTML = `${poseMarkup}${boxMarkup}${alertMarkup}`;
}

function renderPoseSkeleton(snapshot, rect) {
  const poses = snapshotPoses(snapshot);
  if (!poses.length || !rect?.imageWidth || !rect?.imageHeight) return "";
  const edges = snapshotPoseEdges(snapshot);
  const lines = [];
  const points = [];
  const cached = poses.length > 0 && poses.every((pose) => pose.tracking_state === "cached");
  for (const [poseIndex, pose] of poses.entries()) {
    const byName = {};
    for (const point of pose.keypoints || []) {
      if (point?.name && point.visible && Number(point.confidence || 0) >= 0.22) {
        byName[point.name] = point;
      }
    }
    for (const [fromName, toName] of edges) {
      const from = byName[fromName];
      const to = byName[toName];
      if (!from || !to) continue;
      lines.push(`<line class="pose-skeleton-line pose-${poseIndex % 3}" x1="${Number(from.x)}" y1="${Number(from.y)}" x2="${Number(to.x)}" y2="${Number(to.y)}"></line>`);
    }
    for (const point of Object.values(byName)) {
      const core = ["nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip"].includes(point.name) ? " core" : "";
      points.push(`<circle class="pose-keypoint${core} pose-${poseIndex % 3}" cx="${Number(point.x)}" cy="${Number(point.y)}" r="${core ? 4.2 : 3.2}"></circle>`);
    }
  }
  return `
    <svg class="pose-skeleton${cached ? " cached" : ""}" viewBox="0 0 ${rect.imageWidth} ${rect.imageHeight}" preserveAspectRatio="none" aria-hidden="true">
      ${lines.join("")}
      ${points.join("")}
    </svg>
  `;
}

function renderPerceptionTargetList(snapshot) {
  const target = $("perceptionTargetList");
  if (!target) return;
  if (!snapshot) {
    target.innerHTML = '<div class="empty-state">等待人物、姿态与场景目标。</div>';
    setText("sceneMapStatus", "场景学习中");
    return;
  }
  const analysis = snapshot.analysis || {};
  const poses = snapshotPoses(snapshot);
  const people = snapshotPeople(snapshot);
  const pets = snapshotPets(snapshot);
  const scenes = unifiedSceneTargets(snapshot);
  const fallRuntime = latestFallRuntime();
  const fallActive = ["suspect", "confirming", "confirmed"].includes(fallRuntime.stage);
  const rows = [];
  for (const [index, person] of people.entries()) {
    const pose = matchingPose(person, poses);
    const trackId = person.track_id || pose?.track_id;
    const identity = trackId ? `人物 ${String(trackId).split("-").pop()}` : `人物 ${index + 1}`;
    const confidence = person.confidence || pose?.confidence;
    const stateText = pose ? postureLabel(pose.posture) : isPresenceCandidate(person) ? "人体候选" : "姿态识别中";
    const sceneText = pose?.scene_zone_label_zh || person.scene_zone_label_zh || "";
    const needsFallReview = fallActive && bboxIou(person.bbox, fallRuntime.target?.bbox) >= 0.18;
    rows.push(`
      <div class="perception-target-row person-target">
        <span class="perception-target-icon" aria-hidden="true">人</span>
        <div><strong>${escapeHtml(identity)} · ${escapeHtml(stateText)}</strong><span>${escapeHtml([sceneText, confidence ? `置信 ${Math.round(Number(confidence) * 100)}%` : ""].filter(Boolean).join(" · ") || "持续跟踪当前人物")}</span></div>
        <em>${needsFallReview ? "跌倒复核" : "跟踪中"}</em>
      </div>
    `);
  }
  for (const pet of pets) {
    const label = pet.label_zh || (pet.type === "dog" ? "狗" : "猫");
    const confidence = pet.confidence ? `置信 ${Math.round(Number(pet.confidence) * 100)}%` : "";
    const sceneText = pet.scene_zone_label_zh || "";
    rows.push(`
      <div class="perception-target-row pet-target">
        <span class="perception-target-icon" aria-hidden="true">宠</span>
        <div><strong>${escapeHtml(label)}</strong><span>${escapeHtml([sceneText, confidence].filter(Boolean).join(" · ") || "宠物活动")}</span></div>
        <em>独立识别</em>
      </div>
    `);
  }
  for (const scene of scenes.slice(0, 6)) {
    rows.push(`
      <div class="perception-target-row scene-target">
        <span class="perception-target-icon" aria-hidden="true">景</span>
        <div><strong>${escapeHtml(sceneLabel(scene))}</strong><span>${scene.stable ? `已稳定学习 · ${escapeHtml(String(scene.hits || 0))} 帧` : `当前帧识别${scene.confidence ? ` · ${Math.round(Number(scene.confidence) * 100)}%` : ""}`}</span></div>
        <em>${scene.stable ? "场景" : "目标"}</em>
      </div>
    `);
  }
  if (!rows.length) {
    rows.push('<div class="empty-state">当前画面没有识别到人物、宠物或场景目标。</div>');
  }
  target.innerHTML = rows.join("");
  const sceneStatus = String(analysis.scene_map_status || "empty");
  setText("sceneMapStatus", sceneStatus === "stable" ? "场景已学习" : sceneStatus === "learning" ? "场景学习中" : "等待场景目标");
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
  const personCount = snapshot.person_count ?? analysis.person_count ?? "-";
  const petCount = analysis.pet_count ?? snapshotPets(snapshot).length;
  setText("snapshotPeople", petCount ? `${personCount} / 宠${petCount}` : personCount);
  setText("snapshotPoseCount", analysis.pose_count ?? snapshotPoses(snapshot).length);
  setText("snapshotSceneCount", unifiedSceneTargets(snapshot).length);
  setText("snapshotFireState", analysis.fire_event_candidate ? "事件候选" : analysis.fire_candidate ? "线索复核" : "正常");
  setText("snapshotQualityState", analysis.black_screen ? "异常" : "正常");
  const visibleTags = algorithmVisibleTags(snapshot);
  setText("snapshotTags", visibleTags.length ? visibleTags.map(tagLabel).join("，") : algorithmNormalTagLabel(state.previewAlgorithm, snapshot));
  renderDetectionSummary(snapshot);
  renderDetectionOverlay(snapshot);
  renderPerceptionTargetList(snapshot);
  renderAlgorithmHitStrip(snapshot);
}

function renderDetectionSummary(snapshot) {
  const target = $("detectionSummary");
  if (!target) return;
  if (pageName === "algorithms") {
    const stateInfo = algorithmHitState(snapshot);
    const levelClass = stateInfo.level === "critical" ? "bad" : stateInfo.level === "idle" ? "muted" : stateInfo.level;
    target.innerHTML = `<span class="status-pill ${escapeHtml(levelClass)}">统一感知</span><p><strong>${escapeHtml(stateInfo.title)}</strong> · ${escapeHtml(stateInfo.detail)}</p>`;
    return;
  }
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  const pets = snapshotPets(snapshot);
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
        : pets.length
          ? `检测到 ${pets.length} 只宠物`
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
    ...(pets.length ? [`宠物 ${pets.length}`] : []),
  ];
  target.innerHTML = `<span class="status-pill ${levelClass}">${escapeHtml(title)}</span><p>${escapeHtml(details.join(" · "))}</p>`;
}

function renderAlgorithmPreviewMeta(snapshot) {
  if (pageName !== "algorithms") return;
  const container = document.querySelector(".preview-meta");
  if (!container) return;
  const slots = Array.from(container.children).filter((item) => item instanceof HTMLElement);
  const items = algorithmPreviewMetaItems(state.previewAlgorithm || "quality", snapshot);
  for (const [index, slot] of slots.entries()) {
    const item = items[index] || { label: "-", value: "-" };
    const label = slot.querySelector("span");
    const value = slot.querySelector("strong");
    if (label) label.textContent = item.label;
    if (value) value.textContent = item.value;
  }
}

function algorithmPreviewMetaItems(mode, snapshot) {
  const analysis = snapshot?.analysis || {};
  const temporal = analysis.activity_temporal || analysis.activity?.temporal || {};
  const peopleCount = snapshot ? snapshot.person_count ?? analysis.person_count ?? 0 : "-";
  const poseCount = snapshot ? analysis.pose_count ?? snapshotPoses(snapshot).length : "-";
  const tags = snapshot ? algorithmVisibleTags(snapshot, mode) : [];
  const tagText = tags.length ? tags.map(tagLabel).join("，") : algorithmNormalTagLabel(mode, snapshot);
  const capturedAt = snapshot ? fmtTime(snapshot.captured_at) : "-";
  if (!snapshot) {
    return [
      { label: "检测帧", value: "-" },
      { label: "算法状态", value: "等待检测" },
      { label: "指标一", value: "-" },
      { label: "指标二", value: "-" },
      { label: "指标三", value: "-" },
      { label: "标签", value: "-" },
    ];
  }
  if (mode === "person") {
    return [
      { label: "检测帧", value: capturedAt },
      { label: "人数", value: String(peopleCount) },
      { label: "骨架", value: String(poseCount) },
      { label: "最高置信", value: algorithmPeopleConfidence(snapshot) ? `${algorithmPeopleConfidence(snapshot)}%` : "-" },
      { label: "候选复核", value: analysis.presence_enhanced ? "待骨架确认" : "无需" },
      { label: "标签", value: tagText },
    ];
  }
  if (mode === "fall") {
    const fallScore = maxMetricScore([analysis.fall_score, analysis.pose_fall_score]);
    const fallRuntime = latestFallRuntime();
    const threshold = fallRuntime.threshold || analysis.thresholds || {};
    const stableZones = (analysis.scene_zones || []).filter((zone) => zone.stable && zone.zone_kind === "normal_lying_surface");
    const stage = fallStageInfo(fallRuntime.stage, { personCount: peopleCount });
    return [
      { label: "检测帧", value: capturedAt },
      { label: "倒地分数", value: fallScore === null ? "-" : `${Math.round(fallScore * 100)}%` },
      { label: "自动场景", value: stableZones.length ? stableZones.map((zone) => zone.label_zh || zone.label).join("、") : "学习中" },
      { label: "时序状态", value: stage.title },
      { label: "复核进度", value: `${fallRuntime.confirmFrames || 0}/${threshold.confirm_frames || 2} 帧` },
      { label: "持续时间", value: `${Math.round(fallRuntime.durationSeconds || 0)}/${threshold.confirm_seconds ?? 4} 秒` },
    ];
  }
  if (mode === "meal") {
    return [
      { label: "检测帧", value: capturedAt },
      { label: "人数", value: String(peopleCount) },
      { label: "手部窗口", value: fmtPercent(temporal.hand_near_face_ratio, 0) },
      { label: "动作窗口", value: fmtPercent(temporal.active_motion_ratio, 0) },
      { label: "用餐分数", value: analysis.meal_score === undefined || analysis.meal_score === null ? "-" : `${Math.round(Number(analysis.meal_score) * 100)}%` },
      { label: "标签", value: tagText },
    ];
  }
  if (mode === "stillness") {
    const stillnessScore = analysis.daze_score ?? analysis.stillness_score;
    return [
      { label: "检测帧", value: capturedAt },
      { label: "窗口帧", value: temporal.sample_count ? `${temporal.sample_count}` : "-" },
      { label: "低变化", value: fmtPercent(temporal.low_motion_ratio, 0) },
      { label: "坐姿/半身", value: fmtPercent(temporal.seated_or_upper_body_ratio, 0) },
      { label: "静止分数", value: stillnessScore === undefined || stillnessScore === null ? "-" : `${Math.round(Number(stillnessScore) * 100)}%` },
      { label: "标签", value: tagText },
    ];
  }
  if (mode === "night") {
    return [
      { label: "检测帧", value: capturedAt },
      { label: "亮度", value: fmtNumber(analysis.brightness ?? snapshot.brightness, 1) },
      { label: "变化", value: analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4) },
      { label: "人数", value: String(peopleCount) },
      { label: "夜间活动", value: algorithmDemoMetric("night", snapshot).value },
      { label: "标签", value: tagText },
    ];
  }
  if (mode === "fire") {
    const features = analysis.fire_features || {};
    return [
      { label: "检测帧", value: capturedAt },
      { label: "火灾分数", value: fmtNumber(analysis.fire_score || 0, 4) },
      { label: "动态", value: fmtNumber(analysis.fire_temporal_score, 4) },
      { label: "暖色占比", value: fmtPercent(features.warm_ratio, 1) },
      { label: "连通区域", value: features.component_candidate ? "通过" : "未通过" },
      { label: "标签", value: tagText },
    ];
  }
  if (mode === "camera") {
    return [
      { label: "检测帧", value: capturedAt },
      { label: "链路状态", value: analysis.black_screen ? "异常" : "正常" },
      { label: "亮度", value: fmtNumber(analysis.brightness ?? snapshot.brightness, 1) },
      { label: "对比度", value: fmtNumber(analysis.contrast, 1) },
      { label: "变化", value: analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4) },
      { label: "标签", value: tagText },
    ];
  }
  return [
    { label: "检测帧", value: capturedAt },
    { label: "质量分数", value: algorithmQualityScore(snapshot) === null ? "-" : `${algorithmQualityScore(snapshot)}%` },
    { label: "亮度", value: fmtNumber(analysis.brightness ?? snapshot.brightness, 1) },
    { label: "对比度", value: fmtNumber(analysis.contrast, 1) },
    { label: "变化", value: analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4) },
    { label: "标签", value: tagText },
  ];
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
  if (mode === "fall") return { title: context.fallCandidate ? "倒地候选复核中" : "姿态复核中", level: context.fallCandidate ? "watch" : "muted" };
  if (mode === "meal") return { title: "用餐识别演示", level: "" };
  if (mode === "night") return { title: "夜间活动演示", level: "muted" };
  if (mode === "fire") {
    const fireScore = Number(context.analysis.fire_score || 0);
    return fireScore >= 0.035
      ? { title: "火灾线索观察", level: "muted" }
      : { title: "未确认火灾线索", level: "muted" };
  }
  if (mode === "camera") return { title: context.blackScreen ? "摄像头异常" : "摄像头正常", level: context.blackScreen ? "bad" : "muted" };
  return { title: baseTitle, level: "" };
}

function backendLabel(snapshot = state.latestSnapshot) {
  const analysis = snapshot?.analysis || {};
  const backend = analysis.detector_backend || state.detectorBackend || "basic";
  const model = analysis.model_name || state.device?.yolo_model || "";
  const poseModel = analysis.pose_model_name || state.device?.pose_model || "";
  if (analysis.pose_count > 0 && poseModel) return `${model || "YOLO"} + ${poseModel}`;
  if (analysis.pose_model_status === "unavailable") return "姿态模型未安装";
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
  const pets = snapshotPets(snapshot);
  const presenceCount = presenceCandidateCount(snapshot);
  const poses = snapshotPoses(snapshot);
  const result = analysis.algorithm_results?.[selectedAlgorithmKey(mode)] || {};
  const personCount = Number(snapshot?.person_count ?? analysis.person_count ?? people.length ?? 0);
  const confidence = algorithmPeopleConfidence(snapshot);
  const poseConfidence = algorithmPoseConfidence(snapshot);
  let hit = false;
  let level = "idle";
  let title = "等待检测";
  let detail = "选择摄像头后自动分析当前画面";
  let score = confidence ? `${confidence}%` : result.score !== undefined && result.score !== null ? `${Math.round(Number(result.score) * 100)}%` : "-";
  let scoreLabel = "本算法指标";

  if (!snapshot) return { hit, level, title, detail, score, scoreLabel, model: backendLabel(snapshot), latency: "-" };

  if (mode === "unified") {
    const fallRuntime = latestFallRuntime();
    const fallCandidate = ["suspect", "confirming", "confirmed"].includes(fallRuntime.stage);
    const fireCandidate = Boolean(analysis.fire_candidate || analysis.fire_event_candidate);
    const cameraAbnormal = Boolean(analysis.black_screen);
    hit = personCount > 0 || poses.length > 0 || pets.length > 0;
    level = fallCandidate || fireCandidate || cameraAbnormal ? "critical" : hit ? "hit" : "idle";
    title = fallCandidate
      ? fallStageInfo(fallRuntime.stage, { personCount }).title
      : fireCandidate ? "火灾线索复核中" : cameraAbnormal ? "摄像头画面异常" : personCount > 0 || poses.length > 0 ? `检测到 ${personCount || poses.length} 人` : pets.length ? `当前未看到人，检测到 ${pets.length} 只宠物` : "当前画面无人";
    const postureSummary = [...new Set(poses.map((pose) => postureLabel(pose.posture)).filter(Boolean))].join("、");
    const sceneSummary = [...new Set(unifiedSceneTargets(snapshot).map(sceneLabel).filter(Boolean))].join("、");
    detail = [postureSummary ? `姿态 ${postureSummary}` : "姿态待识别", sceneSummary ? `场景 ${sceneSummary}` : "场景学习中"].join(" · ");
    scoreLabel = "当前目标";
    score = `${personCount || poses.length || 0} 人 / ${pets.length} 只宠物`;
  } else if (mode === "person") {
    scoreLabel = poses.length ? "骨架置信" : "人形置信";
    hit = personCount > 0 || poses.length > 0;
    level = hit ? presenceCount && presenceCount === personCount ? "watch" : "hit" : "idle";
    const poseState = analysis.pose_tracking_state || "";
    const poseLabel = poseState === "cached" ? "骨架跟踪" : "骨架";
    title = poses.length ? `${poseLabel} ${poses.length} 组 / 人体 ${personCount}` : hit ? presenceCount && presenceCount === personCount ? `人体存在候选 ${personCount} 个` : `检测到 ${personCount} 人` : "暂未检测到人";
    detail = poses.length ? poseState === "cached" ? "短暂沿用上一组可信骨架稳定画面" : "骨架关键点和人像框已叠加到画面" : hit ? presenceCount ? "坐姿/半身增强框已叠加到画面" : "实时人像框已叠加到画面" : "当前帧没有人形框";
    score = poseConfidence ? `骨架 ${poseConfidence}%` : confidence ? `${presenceCount ? "增强 " : ""}${confidence}%` : score;
  } else if (mode === "fall") {
    scoreLabel = "倒地分数";
    const runtime = latestFallRuntime();
    const stage = fallStageInfo(runtime.stage, { analysis, personCount, poses });
    hit = runtime.stage === "confirmed" || runtime.stage === "confirming" || runtime.stage === "suspect";
    level = stage.level;
    title = stage.title;
    detail = stage.detail;
    const fallScore = maxMetricScore([
      analysis.fall_score,
      analysis.pose_fall_score,
      result?.score,
    ]);
    score = fallScore === null ? score : `${Math.round(fallScore * 100)}%`;
    if (runtime.confirmFrames !== null) {
      const threshold = runtime.threshold || {};
      detail = `${detail} · ${runtime.confirmFrames || 0}/${threshold.confirm_frames || 2} 帧 · ${Math.round(runtime.durationSeconds || 0)}/${threshold.confirm_seconds ?? 4} 秒`;
    }
  } else if (mode === "fire") {
    scoreLabel = "火灾视觉分数";
    const fireScore = Number(analysis.fire_score || 0);
    const temporalScore = Number(analysis.fire_temporal_score || 0);
    hit = fireScore >= 0.035;
    level = hit ? "watch" : "idle";
    title = analysis.fire_event_candidate ? "火灾事件候选" : hit ? "火灾视觉线索" : "未确认火灾线索";
    detail = analysis.fire_event_candidate
      ? "已满足动态火焰候选，等待连续帧确认"
      : hit ? `仅视觉线索，动态变化 ${fmtNumber(temporalScore, 4)}` : "当前帧未达到火灾视觉阈值";
    score = `${Math.round(clamp(Number(analysis.fire_score || 0) * 2800, 0, 98))}%`;
  } else if (mode === "meal") {
    scoreLabel = "用餐窗口";
    hit = Boolean(analysis.meal_candidate);
    level = hit ? "watch" : personCount > 0 ? "watch" : "idle";
    title = hit ? "用餐观察候选" : personCount > 0 ? "动作观察中" : "未检测到人";
    detail = hit ? "观察候选，不作为安全告警" : "结合骨架手部、运动变化和时间窗口判断";
    if (analysis.meal_score !== undefined && analysis.meal_score !== null) score = `${Math.round(Number(analysis.meal_score) * 100)}%`;
  } else if (mode === "stillness") {
    scoreLabel = "静止窗口";
    hit = Boolean(analysis.stillness_candidate || analysis.daze_candidate);
    level = hit ? "watch" : "idle";
    title = analysis.daze_candidate ? "久坐观察候选" : hit ? "静止观察候选" : "活动正常";
    const temporal = analysis.activity_temporal || analysis.activity?.temporal || {};
    detail = temporal.sample_count
      ? `窗口 ${temporal.sample_count} 帧 · 低变化 ${Math.round(Number(temporal.low_motion_ratio || 0) * 100)}%`
      : `变化 ${analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4)}`;
    score = algorithmDemoMetric("stillness", snapshot).value;
  } else if (mode === "night") {
    scoreLabel = "夜间活动";
    const brightness = Number(analysis.brightness ?? snapshot.brightness);
    hit = Number.isFinite(brightness) && brightness < 70 && Number(analysis.motion_score || 0) > 0.006;
    level = hit ? "watch" : "idle";
    title = hit ? "夜间活动命中" : "夜间规则待命";
    detail = `亮度 ${fmtNumber(brightness, 1)} · 变化 ${fmtNumber(analysis.motion_score, 4)}`;
    score = algorithmDemoMetric("night", snapshot).value;
  } else if (mode === "camera") {
    scoreLabel = "链路健康";
    hit = Boolean(analysis.black_screen);
    level = hit ? "critical" : "hit";
    title = hit ? "摄像头异常" : "链路正常";
    detail = `亮度 ${fmtNumber(analysis.brightness ?? snapshot.brightness, 1)} · 对比度 ${fmtNumber(analysis.contrast, 1)}`;
    score = algorithmQualityScore(snapshot) === null ? "-" : `${algorithmQualityScore(snapshot)}%`;
  } else {
    scoreLabel = "画面质量";
    hit = !analysis.black_screen;
    level = hit ? "hit" : "critical";
    title = hit ? "画面质量通过" : "画面质量异常";
    detail = `亮度 ${fmtNumber(analysis.brightness ?? snapshot.brightness, 1)} · 对比度 ${fmtNumber(analysis.contrast, 1)}`;
    score = algorithmQualityScore(snapshot) === null ? "-" : `${algorithmQualityScore(snapshot)}%`;
  }

  const latency = snapshot.live_elapsed_ms ?? snapshot.elapsed_ms ?? snapshot.analysis_elapsed_ms;
  return {
    hit,
    level,
    title,
    detail,
    score,
    scoreLabel,
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
      <span>安全状态</span>
      <strong>${escapeHtml(stateInfo.title)}</strong>
      <small>${escapeHtml(stateInfo.detail)}</small>
    </div>
    <div class="algorithm-hit-card">
      <span>${escapeHtml(stateInfo.scoreLabel)}</span>
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
  for (const id of ["snapshotTime", "streamFrameTime", "snapshotBrightness", "snapshotContrast", "snapshotMotion", "snapshotPeople", "snapshotTags", "snapshotPoseCount", "snapshotSceneCount", "snapshotFireState", "snapshotQualityState"]) {
    setText(id, "-");
  }
  renderPerceptionTargetList(null);
  renderAlgorithmHitStrip(null);
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
  if (mode === "unified") return 7000;
  if (["fall", "meal", "stillness"].includes(mode)) return 9000;
  if (mode === "person" || mode === "night") return 7000;
  if (mode === "fire") return 5200;
  return 6000;
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
      live_elapsed_ms: result.analysis_elapsed_ms ?? result.elapsed_ms,
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
  if (pageName === "algorithms" && state.latestSnapshot) {
    renderAlgorithmHitStrip(state.latestSnapshot);
    renderAlgorithmPreviewMeta(state.latestSnapshot);
    renderDetectionSummary(state.latestSnapshot);
    renderDetectionOverlay(state.latestSnapshot);
    renderPerceptionTargetList(state.latestSnapshot);
  }
}

function renderEvaluation(evaluation) {
  state.latestEvaluation = evaluation || null;
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
  state.latestEvaluation = null;
  if (!$("ruleEvaluation")) return;
  $("ruleEvaluation").innerHTML = `
    <div>
      <span class="status-pill muted">等待检测</span>
      <p>还没有检测状态，抓帧或等待下一轮。</p>
    </div>
  `;
}

function latestFallRuntime() {
  const stateData = state.latestEvaluation?.state || {};
  const threshold = stateData.fall_threshold || {};
  const target = stateData.fall_target || null;
  const stage = String(stateData.fall_stage || stateData.fall_state || "clear");
  const confirmFrames = stateData.fall_confirm_count === undefined || stateData.fall_confirm_count === null
    ? null
    : Number(stateData.fall_confirm_count);
  return {
    stage,
    target,
    threshold,
    confirmFrames,
    durationSeconds: Number(stateData.fall_confirm_seconds || 0),
    clearFrames: Number(stateData.fall_clear_count || 0),
    alertEmitted: Boolean(stateData.fall_alert_emitted),
    sceneSuppressed: Boolean(stateData.fall_scene_suppressed),
    transitionConfirmed: Boolean(stateData.fall_transition_confirmed),
    transition: stateData.fall_transition || {},
  };
}

function fallStageInfo(stage, context = {}) {
  const labels = {
    clear: {
      title: "未命中跌倒证据",
      detail: context.personCount > 0 ? "画面有人，但未出现低位倒地姿态" : "当前没有可复核人体",
      level: "idle",
    },
    visual_only: {
      title: "疑似姿态观察",
      detail: "出现弱倒地线索，但未达到告警阈值",
      level: "watch",
    },
    awaiting_transition: {
      title: "等待下降过程证据",
      detail: "当前只有单帧卧姿，没有观察到此前站坐和快速下降过程",
      level: "watch",
    },
    normal_lying_zone: {
      title: "正常卧躺区域",
      detail: "人体与自动识别的床或沙发重合，不进入跌倒告警",
      level: "idle",
    },
    suspect: {
      title: "疑似跌倒，开始复核",
      detail: "已捕捉到倒地姿态，等待连续帧确认",
      level: "watch",
    },
    confirming: {
      title: "连续复核中",
      detail: "同一人体轨迹持续出现倒地证据",
      level: "watch",
    },
    confirmed: {
      title: "已确认疑似跌倒",
      detail: "事件和截图已进入上传队列",
      level: "critical",
    },
    recovered: {
      title: "跌倒状态已恢复",
      detail: "连续恢复帧已清除本次复核状态",
      level: "hit",
    },
  };
  return labels[stage] || labels.clear;
}

const previewAlgorithmCopy = {
  quality: "画面质量：亮度、对比度、运动变化。",
  person: "人形 / 无人：实时框选画面里的人像并显示置信度。",
  stillness: "久坐 / 静止：看时间窗和画面变化。",
  fall: "跌倒检测：自动识别床和沙发，结合站坐、快速下降、低位持续和恢复过程确认。",
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
    badge: "状态机",
    summary: "捕捉低位倒地线索后进入连续复核，达到帧数、持续时间和置信度阈值才触发事件。",
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
    if (presenceCount) {
      const modelConfidence = people
        .filter((person) => isPresenceCandidate(person) && person.confidence_kind === "model")
        .map((person) => Number(person.model_confidence || person.confidence || 0))
        .filter(Boolean)
        .sort((a, b) => b - a)[0];
      return modelConfidence
        ? `真实指标：YOLO 低置信候选 ${presenceCount} 个，最高模型置信度 ${Math.round(modelConfidence * 100)}%，等待骨架复核。`
        : `真实指标：启发式存在候选 ${presenceCount} 个，不作为人数和模型置信度结论。`;
    }
    return confidence ? `真实指标：检测到 ${people.length} 人，最高置信度 ${Math.round(confidence * 100)}%。` : `真实指标：当前人数 ${snapshot.person_count ?? analysis.person_count ?? 0}。`;
  }
  if (mode === "fire") {
    return `真实指标：火灾分数 ${fmtNumber(analysis.fire_score || 0, 4)}，动态 ${fmtNumber(analysis.fire_temporal_score, 4)}，亮度 ${fmtNumber(analysis.brightness ?? snapshot.brightness, 1)}。`;
  }
  if (mode === "fall") {
    const zones = (analysis.scene_zones || []).filter((zone) => zone.stable && zone.zone_kind === "normal_lying_surface");
    const lyingPose = (analysis.poses || []).find((pose) => pose.normal_lying_zone);
    if (lyingPose) {
      return `真实指标：当前卧姿位于自动识别的${lyingPose.scene_zone_label_zh || "床/沙发"}区域，只保留观察记录，不进入跌倒告警。`;
    }
    return `真实指标：倒地候选 ${analysis.fall_candidate ? "需要时序复核" : "未出现"}，自动场景 ${zones.length ? zones.map((zone) => zone.label_zh || zone.label).join("、") : "学习中"}。`;
  }
  if (mode === "stillness") {
    const temporal = analysis.activity_temporal || analysis.activity?.temporal || {};
    if (temporal.sample_count) {
      return `真实指标：窗口 ${temporal.sample_count} 帧，低变化 ${Math.round(Number(temporal.low_motion_ratio || 0) * 100)}%，坐姿 ${Math.round(Number(temporal.seated_or_upper_body_ratio || 0) * 100)}%。`;
    }
  }
  if (mode === "meal") {
    const temporal = analysis.activity_temporal || analysis.activity?.temporal || {};
    if (temporal.sample_count) {
      return `真实指标：窗口 ${temporal.sample_count} 帧，手部靠近 ${Math.round(Number(temporal.hand_near_face_ratio || 0) * 100)}%，动作 ${Math.round(Number(temporal.active_motion_ratio || 0) * 100)}%。`;
    }
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
      return "准确率口径：YOLO 高置信未命中，低置信候选必须经过 RTMPose 骨架确认后才计入人数。";
    }
    return "准确率口径：YOLO 模型已启用，以模型置信度和连续帧复核作为主要依据。";
  }
  if (snapshot?.analysis?.detector_backend === "demo") {
    return "准确率口径：当前为演示检测，适合讲解效果；正式识别需接入 YOLO / RTMPose 模型。";
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

function algorithmPoseConfidence(snapshot) {
  const poses = snapshotPoses(snapshot);
  const confidence = poses
    .map((pose) => Number(pose.confidence || 0))
    .filter(Boolean)
    .sort((a, b) => b - a)[0];
  return confidence ? Math.round(confidence * 100) : null;
}

function maxMetricScore(values) {
  const scores = values
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value) && value > 0);
  return scores.length ? Math.max(...scores) : null;
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
    const temporal = analysis.activity_temporal || analysis.activity?.temporal || {};
    const score = analysis.daze_score !== undefined && analysis.daze_score !== null
      ? Math.round(Number(analysis.daze_score) * 100)
      : analysis.stillness_score !== undefined && analysis.stillness_score !== null
        ? Math.round(Number(analysis.stillness_score) * 100)
        : algorithmMotionScore(snapshot, true);
    return score === null
      ? { label: "时序静止", value: "--", tone: "muted" }
      : { label: temporal.sample_count ? "时序静止" : "静止可信度", value: `${score}%`, tone: score >= 72 ? "ok" : "muted" };
  }
  if (mode === "fall") {
    const confidence = algorithmPeopleConfidence(snapshot);
    const fallScore = maxMetricScore([analysis.fall_score, analysis.pose_fall_score]);
    const score = fallScore === null
      ? analysis.fall_candidate ? Math.max(confidence || 0, 68) : confidence ? Math.min(confidence, 58) : 32
      : Math.round(fallScore * 100);
    return { label: "倒地复核", value: `${score}%`, tone: analysis.fall_candidate ? "watch" : "muted" };
  }
  if (mode === "meal") {
    const temporal = analysis.activity_temporal || analysis.activity?.temporal || {};
    if (analysis.meal_score !== undefined && analysis.meal_score !== null) {
      return { label: temporal.sample_count ? "时序用餐" : "动作线索", value: `${Math.round(Number(analysis.meal_score) * 100)}%`, tone: analysis.meal_candidate ? "watch" : "muted" };
    }
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
    const score = Math.round(clamp(fireScore * 2800, 0, 98));
    return { label: "视觉线索", value: `${score}%`, tone: fireScore >= .035 ? "muted" : "muted" };
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
        <span>算法示意</span>
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
  const value = $("previewAlgorithm")?.value || (pageName === "algorithms" ? "unified" : state.previewAlgorithm || "quality");
  state.previewAlgorithm = value;
  setText("previewModeInfo", previewAlgorithmCopy[value] || previewAlgorithmCopy.quality);
  renderAlgorithmHitStrip(state.latestSnapshot);
  renderAlgorithmDemo(state.latestSnapshot);
  renderAlgorithmPreviewMeta(state.latestSnapshot);
  renderCandidatePanel();
  renderObservationPanel();
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

function eventTypeLabel(type) {
  const labels = {
    black_screen: "黑屏 / 遮挡",
    no_motion: "长时间无变化",
    no_person: "长时间无人",
    fall_candidate: "疑似跌倒",
    fire_candidate: "疑似火灾",
    camera_offline: "摄像头离线",
  };
  return labels[type] || type || "提醒";
}

function eventCategoryLabel(category, type) {
  const value = category || ({
    fall_candidate: "safety_alert",
    fire_candidate: "safety_alert",
    black_screen: "device_alert",
    camera_offline: "device_alert",
    no_motion: "life_observation",
    no_person: "life_observation",
  }[type] || "system_event");
  const labels = {
    safety_alert: "安全告警",
    device_alert: "设备异常",
    life_observation: "生活观察",
    system_event: "系统记录",
  };
  return labels[value] || "系统记录";
}

function eventLogLifecycle(record) {
  const local = record?.local_event || {};
  const cloud = record?.cloud_event || null;
  const incidentStatus = String(cloud?.incident?.status || "");
  const verificationStatus = String(cloud?.verification?.status || "");
  const syncStatus = String(record?.sync?.status || "local_only");
  if (syncStatus === "failed") return { key: "sync_error", label: "同步异常", tone: "bad" };
  if (!cloud && ["pending", "uploading", "local_only"].includes(syncStatus)) {
    return { key: "verifying", label: syncStatus === "uploading" ? "正在上传" : "等待上传", tone: "watch" };
  }
  if (["acknowledged", "resolved"].includes(incidentStatus)) {
    return { key: "closed", label: incidentStatus === "resolved" ? "已恢复" : "App 已确认", tone: "muted" };
  }
  if (incidentStatus === "confirmed" || verificationStatus === "confirmed") return { key: "confirmed", label: "已确认风险", tone: "bad" };
  if (incidentStatus === "rejected" || verificationStatus === "rejected") return { key: "rejected", label: "已排除", tone: "muted" };
  if (incidentStatus === "uncertain" || verificationStatus === "uncertain" || verificationStatus === "failed") {
    return { key: "attention", label: "需 App 确认", tone: "watch" };
  }
  if (incidentStatus === "verifying" || ["pending", "verifying", "retrying"].includes(verificationStatus)) {
    return { key: "verifying", label: verificationStatus === "retrying" ? "等待模型重试" : "云端复核中", tone: "watch" };
  }
  if (cloud?.acknowledged) return { key: "closed", label: "App 已处理", tone: "muted" };
  if (local.acknowledged) return { key: "closed", label: "本地历史已处理", tone: "muted" };
  return { key: "synced", label: cloud ? "云端已接收" : "本地已记录", tone: "" };
}

function eventLogSyncStage(record) {
  const eventJob = record?.sync?.event_upload || null;
  const mediaJob = record?.sync?.media_upload || null;
  const statuses = [eventJob?.status, mediaJob?.status].filter(Boolean);
  if (statuses.includes("failed")) return { label: "上传失败", state: "failed" };
  if (statuses.includes("uploading")) return { label: "正在上传", state: "active" };
  if (statuses.includes("pending")) return { label: "等待上传", state: "pending" };
  if (statuses.length && statuses.every((status) => status === "completed")) return { label: "证据已上传", state: "done" };
  return { label: "无需附件", state: "done" };
}

function eventLogVerificationReason(record) {
  const verification = record?.cloud_event?.verification || {};
  const result = verification.result || {};
  return result.reason || verification.error || "";
}

function eventLogStage(label, detail, stateName) {
  return `<div class="event-chain-stage ${escapeHtml(stateName || "pending")}"><span></span><div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(detail)}</small></div></div>`;
}

function renderEventLog() {
  const target = $("eventTimeline");
  if (!target) return;
  const records = state.eventLogRecords || [];
  const lifecycles = records.map((record) => eventLogLifecycle(record));
  setText("eventLogTotal", records.length);
  setText("eventLogAttention", lifecycles.filter((item) => ["confirmed", "attention"].includes(item.key)).length);
  setText("eventLogSynced", records.filter((record) => Boolean(record.cloud_event)).length);
  setText("eventLogFailed", lifecycles.filter((item) => item.key === "sync_error").length);
  const filtered = records.filter((record) => {
    const local = record.local_event || {};
    const lifecycle = eventLogLifecycle(record);
    const statusMatch = state.eventLogStatusFilter === "all"
      || lifecycle.key === state.eventLogStatusFilter
      || (state.eventLogStatusFilter === "attention" && ["confirmed", "attention"].includes(lifecycle.key));
    const typeMatch = state.eventLogTypeFilter === "all" || local.type === state.eventLogTypeFilter;
    return statusMatch && typeMatch;
  });
  if (!filtered.length) {
    target.innerHTML = '<div class="empty-state">当前筛选条件下没有正式安全事件。</div>';
    return;
  }
  target.innerHTML = filtered.map((record) => {
    const local = record.local_event || {};
    const cloud = record.cloud_event || null;
    const lifecycle = eventLogLifecycle(record);
    const syncStage = eventLogSyncStage(record);
    const evidence = local.payload?.evidence || {};
    const pills = evidencePills({ event_type: local.type, payload: local.payload || {} });
    if (Number(evidence.metrics?.pet_count || 0) > 0) pills.push(`宠物 ${Number(evidence.metrics.pet_count)} 只`);
    const cloudStage = cloud ? { label: "云端已接收", state: "done" } : { label: "等待云端入库", state: syncStage.state === "failed" ? "failed" : "pending" };
    const resultReason = eventLogVerificationReason(record);
    const incidentId = cloud?.incident?.incident_id || "";
    const uploadError = record.sync?.event_upload?.last_error || record.sync?.media_upload?.last_error || "";
    return `
      <article class="event-log-card ${escapeHtml(lifecycle.tone || "")}">
        <header>
          <div>
            <span class="event-type-mark">${escapeHtml(eventTypeLabel(local.type))}</span>
            <h2>${escapeHtml(local.summary || eventTypeLabel(local.type))}</h2>
            <p>${escapeHtml([local.camera_name || local.room || "盒子", fmtTime(local.occurred_at), `本地 #${local.id}`, cloud?.event_id ? `云端 #${cloud.event_id}` : ""].filter(Boolean).join(" · "))}</p>
          </div>
          <span class="status-pill ${escapeHtml(lifecycle.tone || "")}">${escapeHtml(lifecycle.label)}</span>
        </header>
        <div class="event-chain">
          ${eventLogStage("盒子已触发", "规则形成正式事件", "done")}
          ${eventLogStage(syncStage.label, uploadError || (local.snapshot_url ? "事件与截图证据" : "事件结构化数据"), syncStage.state)}
          ${eventLogStage(cloudStage.label, cloud ? "edge_event_id 已匹配" : "保持本地事件等待同步", cloudStage.state)}
          ${eventLogStage(lifecycle.label, resultReason || (incidentId ? `事故 ${incidentId}` : "等待后续状态"), ["confirmed", "attention"].includes(lifecycle.key) ? "failed" : ["rejected", "closed", "synced"].includes(lifecycle.key) ? "done" : "active")}
        </div>
        ${pills.length ? `<div class="candidate-evidence">${pills.slice(0, 6).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
        <footer>
          <span>${incidentId ? `Incident ${escapeHtml(incidentId)}` : "云端状态会自动回写到此处"}</span>
          <div class="event-log-actions">
            ${local.snapshot_url ? `<button class="ghost-button" type="button" data-event-log-action="snapshot" data-url="${escapeHtml(local.snapshot_url)}">查看证据</button>` : ""}
            ${cloud && !["rejected", "closed"].includes(lifecycle.key) ? `<button class="ghost-button danger-text" type="button" data-event-log-action="false_positive" data-id="${local.id}">标记算法误报</button>` : ""}
          </div>
        </footer>
        <details class="event-log-details">
          <summary>查看技术日志</summary>
          <dl>
            <div><dt>事件类型</dt><dd>${escapeHtml(local.type || "-")}</dd></div>
            <div><dt>本地候选</dt><dd>${escapeHtml(local.candidate_status || "-")}</dd></div>
            <div><dt>事件上传</dt><dd>${escapeHtml(record.sync?.event_upload?.status || "-")}</dd></div>
            <div><dt>证据上传</dt><dd>${escapeHtml(record.sync?.media_upload?.status || "-")}</dd></div>
            <div><dt>模型状态</dt><dd>${escapeHtml(cloud?.verification?.status || "无需复核")}</dd></div>
            <div><dt>App 处理</dt><dd>${escapeHtml(cloud?.acknowledged ? "已处理" : "未处理")}</dd></div>
          </dl>
        </details>
      </article>
    `;
  }).join("");
}

async function loadEventLog() {
  if (!$("eventTimeline")) return;
  const payload = await api("/api/event-log?limit=120");
  state.eventLogRecords = Array.isArray(payload.records) ? payload.records : [];
  const cloudStatus = $("eventLogCloudStatus");
  if (cloudStatus) {
    cloudStatus.textContent = payload.cloud_ok ? "云端状态已同步" : "云端暂不可用";
    cloudStatus.className = `status-pill ${payload.cloud_ok ? "" : "watch"}`;
    cloudStatus.title = payload.cloud_error || "";
  }
  renderEventLog();
}

function evidencePills(candidate) {
  const evidence = candidate?.payload?.evidence || {};
  const metrics = evidence.metrics || {};
  const observed = evidence.rule?.observed || candidate?.payload?.rule?.observed || {};
  const model = evidence.model || {};
  const pills = [];
  const pushMetric = (label, value, digits = 2) => {
    if (value === null || value === undefined || value === "") return;
    pills.push(`${label} ${typeof value === "number" ? fmtNumber(value, digits) : value}`);
  };
  const maxMetric = (...values) => {
    const numbers = values
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value));
    return numbers.length ? Math.max(...numbers) : null;
  };
  const pushPill = (value) => {
    if (value) pills.push(value);
  };
  if (candidate.event_type === "fall_candidate") {
    pushMetric("人数", metrics.person_count, 0);
    pushMetric("骨架", metrics.pose_count, 0);
    pushMetric("跌倒", maxMetric(metrics.fall_score, metrics.pose_fall_score, observed.fall_score, observed.pose_fall_score), 2);
    pushMetric("连续帧", observed.confirm_frames, 0);
    const evidenceTypes = observed.evidence?.types || [];
    if (Array.isArray(evidenceTypes) && evidenceTypes.length) {
      pushPill(`依据 ${evidenceTypes.slice(0, 2).join(" / ")}`);
    }
  } else if (candidate.event_type === "fire_candidate") {
    pushMetric("火灾", metrics.fire_score, 4);
    pushMetric("变化", metrics.motion_score, 4);
    pushMetric("动态", metrics.fire_temporal_score ?? observed.temporal_score, 4);
    pushMetric("连续帧", observed.confirm_frames, 0);
  } else if (candidate.event_type === "no_motion") {
    pushMetric("人数", metrics.person_count, 0);
    pushPill(observed.no_motion_seconds ? `静止 ${fmtDuration(observed.no_motion_seconds)}` : "");
    pushMetric("变化", metrics.motion_score, 4);
  } else if (candidate.event_type === "no_person") {
    pushPill(observed.no_person_seconds ? `无人 ${fmtDuration(observed.no_person_seconds)}` : "");
    pushMetric("人数", metrics.person_count, 0);
  } else if (candidate.event_type === "black_screen") {
    pushMetric("亮度", metrics.brightness, 1);
    pushMetric("对比", metrics.contrast, 1);
  } else {
    pushMetric("人数", metrics.person_count, 0);
    pushMetric("变化", metrics.motion_score, 4);
  }
  if (model.model_name || model.pose_model_name) {
    pills.push(model.pose_model_name ? `${model.model_name || "YOLO"} + ${model.pose_model_name}` : model.model_name);
  }
  return pills.slice(0, 5);
}

function algorithmRecordScope(mode = state.previewAlgorithm || "quality") {
  const scopes = {
    unified: {
      candidateTypes: ["fall_candidate", "fire_candidate", "black_screen", "camera_offline", "no_person", "no_motion"],
      observationTypes: ["no_person", "no_motion"],
      candidateTitle: "最近安全记录",
      observationTitle: "最近生活观察",
      observationSubtitle: "统一时间线",
      candidateEmpty: "当前没有需要处理的安全记录。",
      observationEmpty: "当前没有持续无人或低活动观察。",
    },
    quality: {
      candidateTypes: ["black_screen"],
      observationTypes: ["no_motion"],
      candidateTitle: "质量相关记录",
      observationTitle: "质量观察",
      observationSubtitle: "低变化区间",
      candidateEmpty: "当前没有画面质量相关告警。",
      observationEmpty: "当前没有画面质量相关观察区间。",
    },
    person: {
      candidateTypes: ["no_person"],
      observationTypes: ["no_person"],
      candidateTitle: "无人相关记录",
      observationTitle: "无人观察",
      observationSubtitle: "离开时间区间",
      candidateEmpty: "当前没有无人相关后台记录。",
      observationEmpty: "当前没有无人观察区间。",
    },
    stillness: {
      candidateTypes: ["no_motion"],
      observationTypes: ["no_motion"],
      candidateTitle: "静止相关记录",
      observationTitle: "静止观察",
      observationSubtitle: "无变化区间",
      candidateEmpty: "当前没有静止相关后台记录。",
      observationEmpty: "当前没有静止观察区间。",
    },
    fall: {
      candidateTypes: ["fall_candidate"],
      observationTypes: [],
      candidateTitle: "跌倒相关记录",
      observationTitle: "跌倒观察",
      observationSubtitle: "实时复核为主",
      candidateEmpty: "当前没有跌倒候选记录。",
      observationEmpty: "跌倒属于安全告警，不单独生成生活观察区间。",
    },
    meal: {
      candidateTypes: [],
      observationTypes: [],
      candidateTitle: "用餐相关记录",
      observationTitle: "用餐观察",
      observationSubtitle: "实时窗口候选",
      candidateEmpty: "用餐目前只在实时画面中形成观察候选，不生成安全告警。",
      observationEmpty: "当前版本还没有把用餐候选沉淀为后台观察区间。",
    },
    night: {
      candidateTypes: [],
      observationTypes: [],
      candidateTitle: "夜间相关记录",
      observationTitle: "夜间观察",
      observationSubtitle: "实时规则候选",
      candidateEmpty: "夜间活动目前按实时规则复核，暂无独立后台记录。",
      observationEmpty: "当前没有夜间活动观察区间。",
    },
    fire: {
      candidateTypes: ["fire_candidate"],
      observationTypes: [],
      candidateTitle: "火灾相关记录",
      observationTitle: "火灾观察",
      observationSubtitle: "安全告警为主",
      candidateEmpty: "当前没有火灾候选记录。",
      observationEmpty: "火灾属于安全告警，不生成生活观察区间。",
    },
    camera: {
      candidateTypes: ["black_screen", "camera_offline"],
      observationTypes: [],
      candidateTitle: "摄像头相关记录",
      observationTitle: "摄像头观察",
      observationSubtitle: "链路诊断",
      candidateEmpty: "当前没有摄像头异常记录。",
      observationEmpty: "摄像头异常属于设备记录，不生成生活观察区间。",
    },
  };
  return scopes[mode] || scopes.quality;
}

function matchesTypeScope(recordType, allowedTypes) {
  return allowedTypes.length > 0 && allowedTypes.includes(String(recordType || ""));
}

function renderCandidatePanel(candidates = state.candidateRecords) {
  const list = $("candidateList");
  if (!list) return;
  const scope = algorithmRecordScope();
  setText("candidatePanelTitle", scope.candidateTitle);
  const filtered = candidates.filter((candidate) => matchesTypeScope(candidate.event_type, scope.candidateTypes));
  if (!filtered.length) {
    list.innerHTML = `<div class="empty-state">${escapeHtml(scope.candidateEmpty)}</div>`;
    return;
  }
  list.innerHTML = filtered.map((candidate) => {
    const rule = candidate.payload?.rule || {};
    const evidence = candidate.payload?.evidence || {};
    const observed = rule.observed?.no_person_seconds || rule.observed?.no_motion_seconds || null;
    const threshold = rule.threshold?.no_person_seconds || rule.threshold?.no_motion_seconds || null;
    const explanation = rule.reason
      || candidate.promoted_event_summary
      || candidate.summary
      || `${eventTypeLabel(candidate.event_type)}记录`;
    const meta = [
      eventTypeLabel(candidate.event_type),
      candidate.camera_name || candidate.camera_room || `摄像头 ${candidate.camera_id}`,
      fmtTime(candidate.updated_at || candidate.created_at),
    ].filter(Boolean).join(" · ");
    const detail = [
      observed ? `观测 ${fmtDuration(observed)}` : "",
      threshold ? `阈值 ${fmtDuration(threshold)}` : "",
      candidate.promoted_event_id ? `事件 #${candidate.promoted_event_id}` : "",
      evidence.schema_version ? "证据包已生成" : "",
    ].filter(Boolean).join(" · ");
    const pills = evidencePills(candidate);
    const category = eventCategoryLabel(evidence.event_category, candidate.event_type);
    return `
      <article class="candidate-card ${candidate.status === "promoted" ? "done" : ""}" data-category="${escapeHtml(evidence.event_category || "")}">
        <div class="candidate-card-head">
          <strong>${escapeHtml(explanation)}</strong>
          <span>${escapeHtml(candidateStatusLabel(candidate.status))}</span>
        </div>
        <p>${escapeHtml(category)} · ${escapeHtml(meta || `记录 #${candidate.id || "-"}`)}</p>
        ${detail ? `<p>${escapeHtml(detail)}</p>` : ""}
        ${pills.length ? `<div class="candidate-evidence">${pills.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
      </article>
    `;
  }).join("");
}

async function loadCandidates() {
  const list = $("candidateList");
  if (!list) return;
  let candidates = [];
  try {
    candidates = await api("/api/event-candidates?limit=12&status=active");
  } catch (error) {
    list.innerHTML = `<div class="empty-state">记录暂不可用：${escapeHtml(error.message || "加载失败")}。</div>`;
    throw error;
  }
  state.candidateRecords = candidates;
  renderCandidatePanel(candidates);
}

function observationStatusLabel(status) {
  if (status === "open") return "进行中";
  if (status === "closed") return "已恢复";
  return status || "未知";
}

function observationPills(log) {
  const payload = log?.payload || {};
  const evidence = payload.evidence || {};
  const metrics = evidence.metrics || {};
  const observed = evidence.rule?.observed || payload.rule?.observed || {};
  const pills = [];
  const duration = Number(log?.duration_seconds || observed.no_motion_seconds || observed.no_person_seconds || 0);
  if (duration > 0) pills.push(`持续 ${fmtDuration(duration)}`);
  if (log?.sample_count) pills.push(`采样 ${log.sample_count} 次`);
  if (log?.observation_type === "no_motion" && metrics.motion_score !== undefined) {
    pills.push(`变化 ${fmtNumber(metrics.motion_score, 4)}`);
  }
  if (metrics.person_count !== undefined) pills.push(`人数 ${fmtNumber(metrics.person_count, 0)}`);
  return pills.slice(0, 4);
}

function renderObservationPanel(logs = state.observationLogs) {
  const list = $("observationList");
  if (!list) return;
  const scope = algorithmRecordScope();
  setText("observationPanelTitle", scope.observationTitle);
  setText("observationPanelSubtitle", scope.observationSubtitle);
  const filtered = logs.filter((log) => matchesTypeScope(log.observation_type, scope.observationTypes));
  if (!filtered.length) {
    list.innerHTML = `<div class="empty-state">${escapeHtml(scope.observationEmpty)}</div>`;
    return;
  }
  list.innerHTML = filtered.map((log) => {
    const payload = log.payload || {};
    const rule = payload.rule || {};
    const explanation = rule.reason || log.summary || `${eventTypeLabel(log.observation_type)}记录`;
    const meta = [
      eventTypeLabel(log.observation_type),
      log.camera_name || log.camera_room || `摄像头 ${log.camera_id}`,
      fmtTime(log.started_at),
    ].filter(Boolean).join(" · ");
    const pills = observationPills(log);
    return `
      <article class="candidate-card observation-card ${log.status === "closed" ? "done" : ""}" data-category="life_observation">
        <div class="candidate-card-head">
          <strong>${escapeHtml(explanation)}</strong>
          <span>${escapeHtml(observationStatusLabel(log.status))}</span>
        </div>
        <p>${escapeHtml(meta)}</p>
        ${log.status === "open" ? `<p>最后更新 ${escapeHtml(fmtTime(log.last_seen_at))}</p>` : `<p>恢复时间 ${escapeHtml(fmtTime(log.ended_at))}</p>`}
        ${pills.length ? `<div class="candidate-evidence">${pills.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
      </article>
    `;
  }).join("");
}

function verificationStatusLabel(status) {
  const labels = {
    pending: "等待复核",
    verifying: "复核中",
    retrying: "等待重试",
    confirmed: "已确认",
    rejected: "已排除",
    uncertain: "需人工确认",
    failed: "复核失败",
    unavailable: "不可用",
  };
  return labels[String(status || "")] || status || "未知";
}

function verificationResultPills(record) {
  const verification = record?.verification || {};
  const result = verification.result || record?.job?.response_payload?.parsed || {};
  const pills = [];
  if (result.person_count !== undefined) pills.push(`人数 ${result.person_count}`);
  const postureLabels = { standing: "站立", sitting: "坐姿", squatting: "蹲姿", bending: "弯腰", lying: "躺姿", fallen: "倒地", unknown: "未识别" };
  const surfaceLabels = { floor: "地面", bed: "床", sofa: "沙发", chair: "椅子", unknown: "未知" };
  if (result.posture) pills.push(`姿态 ${postureLabels[result.posture] || result.posture}`);
  if (result.surface) pills.push(`位置 ${surfaceLabels[result.surface] || result.surface}`);
  if (result.confidence !== undefined) pills.push(`置信 ${Math.round(Number(result.confidence) * 100)}%`);
  if (verification.attempt_count || record?.job?.attempt_count) {
    pills.push(`尝试 ${verification.attempt_count || record.job.attempt_count} 次`);
  }
  return pills.slice(0, 5);
}

function renderCloudVerifications(payload = state.cloudVerifications) {
  const list = $("verificationList");
  if (!list) return;
  if (!payload?.ok) {
    setText("verificationPanelStatus", payload?.configured === false ? "云端未配置" : "连接失败");
    list.innerHTML = `<div class="empty-state">${escapeHtml(payload?.reason || "暂时无法读取云端复核日志。")}</div>`;
    return;
  }
  setText("verificationPanelStatus", payload.enabled && payload.configured ? "模型已连接" : "模型未启用");
  const records = Array.isArray(payload.records) ? payload.records : [];
  if (!records.length) {
    list.innerHTML = '<div class="empty-state">当前没有需要云端模型复核的安全事件。</div>';
    return;
  }
  list.innerHTML = records.map((record) => {
    const verification = record.verification || {};
    const result = verification.result || record.job?.response_payload?.parsed || {};
    const error = verification.error || record.job?.error_message || "";
    const unavailableReasons = {
      missing_event_evidence: "事件缺少可供模型复核的截图证据。",
      model_not_configured: "云端视觉复核模型尚未配置。",
    };
    const reason = result.reason
      || error
      || unavailableReasons[verification.reason]
      || (verification.status === "pending" ? "事件证据已上传，等待模型处理。" : "模型任务已记录。" );
    const pills = verificationResultPills(record);
    const status = verification.status || record.job?.output_status;
    return `
      <article class="candidate-card verification-card ${status === "confirmed" ? "verified" : status === "failed" ? "verification-failed" : ""}">
        <div class="candidate-card-head">
          <strong>${escapeHtml(record.summary || eventTypeLabel(record.event_type))}</strong>
          <span>${escapeHtml(verificationStatusLabel(status))}</span>
        </div>
        <p>${escapeHtml([record.room, fmtTime(record.updated_at || record.occurred_at), record.job?.model].filter(Boolean).join(" · "))}</p>
        <p>${escapeHtml(reason)}</p>
        ${pills.length ? `<div class="candidate-evidence">${pills.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
      </article>
    `;
  }).join("");
}

async function loadCloudVerifications() {
  if (!$("verificationList")) return;
  const payload = await api("/api/cloud-verifications?limit=12");
  state.cloudVerifications = payload;
  renderCloudVerifications(payload);
}

async function loadObservationLogs() {
  const list = $("observationList");
  if (!list) return;
  let logs = [];
  try {
    logs = await api("/api/observation-logs?limit=8");
  } catch (error) {
    list.innerHTML = `<div class="empty-state">观察日志暂不可用：${escapeHtml(error.message || "加载失败")}。</div>`;
    throw error;
  }
  state.observationLogs = logs;
  renderObservationPanel(logs);
}

async function loadUploadQueueSummary() {
  const target = $("uploadQueueSummary");
  if (!target) return;
  try {
    const summary = await api("/api/upload-jobs/summary");
    const pending = Number(summary.pending || 0);
    const failed = Number(summary.failed || 0);
    const critical = Number(summary.pending_critical || 0);
    if (!pending && !failed) {
      target.textContent = "后台留证记录";
      return;
    }
    target.textContent = `待上传 ${pending}${failed ? ` / 失败 ${failed}` : ""}${critical ? ` / 高优先 ${critical}` : ""}`;
  } catch (_error) {
    target.textContent = "上传队列暂不可用";
  }
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
    await loadObservationLogs().catch(() => null);
    await loadUploadQueueSummary().catch(() => null);
    await loadCloudVerifications().catch(() => null);
    await loadEventLog().catch(() => null);
  } catch (error) {
    showToast(userSafeError(error.message || "无法连接 edge-agent"));
  }
}

function bindEvents() {
  on("refreshAll", "click", refreshAll);
  on("refreshEventLog", "click", (event) => {
    setBusy(event.currentTarget, true);
    loadEventLog()
      .catch((error) => showToast(userSafeError(error.message)))
      .finally(() => setBusy(event.currentTarget, false));
  });
  on("eventLogStatusFilter", "change", (event) => {
    state.eventLogStatusFilter = event.currentTarget.value;
    renderEventLog();
  });
  on("eventLogTypeFilter", "change", (event) => {
    state.eventLogTypeFilter = event.currentTarget.value;
    renderEventLog();
  });
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
  const eventTimeline = $("eventTimeline");
  if (eventTimeline) {
    eventTimeline.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-event-log-action]");
      if (!button) return;
      if (button.dataset.eventLogAction === "snapshot") {
        window.open(`${button.dataset.url}?t=${Date.now()}`, "_blank", "noopener");
        return;
      }
      if (button.dataset.eventLogAction === "false_positive") {
        if (!window.confirm("确认这是算法误报？该反馈会同步云端、关闭对应提醒，并保留完整证据用于后续优化。")) return;
        setBusy(button, true);
        try {
          await api(`/api/events/${Number(button.dataset.id)}/false-positive`, { method: "POST" });
          showToast("误报反馈已同步云端");
          await loadEventLog();
        } catch (error) {
          showToast(userSafeError(error.message));
        } finally {
          setBusy(button, false);
        }
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
      loadObservationLogs().catch(() => null);
      loadUploadQueueSummary().catch(() => null);
      loadCloudVerifications().catch(() => null);
    }
    if (pageName === "events") loadEventLog().catch(() => null);
  }, 6000);
});
