const pageName = document.body.dataset.page || "home";
const defaultCameraChannel = "1";
const defaultCameraStream = "2";
const livePosePollIntervalMs = 200;

const state = {
  device: null,
  setupNetwork: null,
  cameraPresets: null,
  cameraDiscovery: [],
  cameras: [],
  selectedCameraId: null,
  cameraMode: "lan",
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
  streamStartedAt: 0,
  streamLastRecoveryAt: 0,
  liveAnalysisTimer: null,
  liveAnalysisBusy: false,
  liveAnalysisErrorShown: false,
  liveAnalysisGeneration: 0,
  lastAnalysisCapturedAt: 0,
  lastAnalysisFrameId: "",
  lastAnalysisSourceKey: "",
  lastAnalysisFrameSequence: null,
  liveEvaluationUpdatedAt: 0,
  candidateRecords: [],
  observationLogs: [],
  cloudVerifications: null,
  cameraConfigAuthority: null,
  bindingClosesAt: 0,
  runtimeStatus: null,
  eventLogRecords: [],
  eventLogStatusFilter: "all",
  eventLogTypeFilter: "all",
  toastTimer: null,
  videoPrivacyMode: "original",
  videoPrivacyUpdatedAt: "",
  videoPrivacyLoaded: false,
  privacyCalibrations: [],
  privacyTimer: null,
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

function showToast(message) {
  const toast = $("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function normalizeVideoPrivacyMode(value) {
  return ["original", "person_blur", "skeleton"].includes(String(value || ""))
    ? String(value)
    : "original";
}

function ensureVideoPrivacyControl() {
  if (document.querySelector(".admin-privacy-panel")) return;
  const sidebar = document.querySelector(".admin-sidebar");
  if (!sidebar) return;
  const panel = document.createElement("section");
  panel.className = "admin-privacy-panel";
  panel.setAttribute("aria-label", "家庭画面隐私");
  panel.innerHTML = `
    <div class="admin-privacy-head">
      <strong>画面隐私</strong>
      <span id="videoPrivacySyncState">家庭同步</span>
    </div>
    <div class="segmented-control privacy-mode-control" aria-label="隐私画面模式">
      <button type="button" data-privacy-mode="original">原画</button>
      <button type="button" data-privacy-mode="person_blur">模糊</button>
      <button type="button" data-privacy-mode="skeleton">骨架</button>
    </div>
    <div id="privacyCalibrationList" class="privacy-calibration-list"></div>`;
  const controls = sidebar.querySelector(".admin-sidebar-controls");
  controls?.insertAdjacentElement("afterend", panel);
  if (!controls) sidebar.querySelector(".admin-nav")?.insertAdjacentElement("afterend", panel);
}

function renderVideoPrivacyMode() {
  const calibrationRequired = state.privacyCalibrations.some((item) => item.enabled && !item.ready);
  document.querySelectorAll("[data-privacy-mode]").forEach((button) => {
    const active = button.dataset.privacyMode === state.videoPrivacyMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.disabled = button.dataset.privacyMode === "skeleton" && calibrationRequired;
  });
  setText("videoPrivacySyncState", state.videoPrivacyLoaded ? "已同步" : "家庭同步");
  const target = $("privacyCalibrationList");
  if (!target) return;
  target.innerHTML = state.privacyCalibrations
    .filter((item) => item.enabled)
    .map((item) => {
      const status = item.ready
        ? "已校准"
        : item.status === "calibrating"
          ? `${Number(item.calibration_observations || 0)}/${Number(item.calibration_required_frames || 8)}`
          : item.status === "revalidating"
            ? "复验中"
            : "未校准";
      return `
        <div class="privacy-calibration-row">
          <span><strong>${escapeHtml(item.room || item.name || "摄像头 " + item.camera_id)}</strong><small>${escapeHtml(status)}</small></span>
          ${item.ready ? '<i class="status-dot ok" aria-hidden="true"></i>' : `<button type="button" data-calibrate-camera="${Number(item.camera_id)}">校准</button>`}
        </div>`;
    })
    .join("");
  target.querySelectorAll("[data-calibrate-camera]").forEach((button) => {
    button.addEventListener("click", () => calibratePrivacyCamera(button.dataset.calibrateCamera, button)
      .catch((error) => showToast(userSafeError(error.message))));
  });
}

async function loadVideoPrivacyMode({ refreshStream = true } = {}) {
  const payload = await api("/api/admin/video-privacy");
  const nextMode = normalizeVideoPrivacyMode(payload?.minimum_mode);
  const changed = nextMode !== state.videoPrivacyMode;
  state.videoPrivacyMode = nextMode;
  state.videoPrivacyUpdatedAt = String(payload?.updated_at || "");
  state.privacyCalibrations = Array.isArray(payload?.calibrations) ? payload.calibrations : [];
  state.videoPrivacyLoaded = true;
  renderVideoPrivacyMode();
  if (changed && refreshStream && state.selectedCameraId) renderStream({ retry: true });
  return payload;
}

async function calibratePrivacyCamera(cameraId, button) {
  setBusy(button, true);
  try {
    await api(`/api/admin/cameras/${Number(cameraId)}/privacy-calibration`, { method: "POST" });
    await loadVideoPrivacyMode({ refreshStream: false });
    showToast("空房校准已完成");
  } finally {
    setBusy(button, false);
  }
}

async function updateVideoPrivacyMode(mode, button) {
  const nextMode = normalizeVideoPrivacyMode(mode);
  if (nextMode === state.videoPrivacyMode) return;
  setBusy(button, true);
  try {
    const payload = await api("/api/admin/video-privacy", {
      method: "PUT",
      body: JSON.stringify({ minimum_mode: nextMode }),
    });
    state.videoPrivacyMode = normalizeVideoPrivacyMode(payload?.minimum_mode);
    state.videoPrivacyUpdatedAt = String(payload?.updated_at || "");
    state.privacyCalibrations = Array.isArray(payload?.calibrations) ? payload.calibrations : state.privacyCalibrations;
    state.videoPrivacyLoaded = true;
    renderVideoPrivacyMode();
    renderStream({ retry: true });
  } finally {
    setBusy(button, false);
  }
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
    if (response.status === 401 && !window.location.pathname.endsWith("/admin/login.html")) {
      const next = `${window.location.pathname}${window.location.search}`;
      window.location.replace(`/admin/login.html?next=${encodeURIComponent(next)}`);
    }
    const error = new Error(data?.detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
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
  state.cameraConfigAuthority = device.camera_config_authority || null;
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
  renderDeviceBinding();
  renderCameraConfigAuthority();
  prefillCameraForm();
}

function renderPairingCountdown() {
  const target = $("pairingWindowState");
  if (!target) return;
  const remaining = Math.max(0, Math.ceil((state.bindingClosesAt - Date.now()) / 1000));
  target.textContent = remaining > 0 ? `已开启 ${fmtDuration(remaining)}` : "未开启";
}

function syncStatusPresentation(sync) {
  if (!sync.configured) return { label: "未连接", tone: "muted", detail: "云端同步尚未配置" };
  if (!sync.running) return { label: "同步停止", tone: "bad", detail: "同步进程未运行" };
  if (sync.last_error) {
    const failures = Math.max(1, Number(sync.consecutive_failures || 1));
    return {
      label: failures >= 3 ? "同步异常" : "正在重试",
      tone: failures >= 3 ? "bad" : "warning",
      detail: `${fmtTime(sync.last_error_at)} · ${String(sync.last_error)}`,
    };
  }

  const syncedAt = Date.parse(sync.last_sync_at || "");
  if (!Number.isFinite(syncedAt)) {
    return { label: "等待同步", tone: "warning", detail: "等待首次云端确认" };
  }
  const ageSeconds = Math.max(0, (Date.now() - syncedAt) / 1000);
  if (ageSeconds > 60) {
    return {
      label: "同步延迟",
      tone: "warning",
      detail: `最近成功同步：${fmtTime(sync.last_sync_at)}`,
    };
  }
  if (sync.last_result?.report_ok === false) {
    return {
      label: "等待云端确认",
      tone: "warning",
      detail: `最近同步：${fmtTime(sync.last_sync_at)}`,
    };
  }
  return {
    label: `已同步 ${new Date(syncedAt).toLocaleTimeString("zh-CN", { hour12: false })}`,
    tone: "success",
    detail: sync.last_recovered_at
      ? `已恢复 · 最近成功同步：${fmtTime(sync.last_sync_at)}`
      : `最近成功同步：${fmtTime(sync.last_sync_at)}`,
  };
}

function renderDeviceBinding() {
  if (pageName !== "home" || !state.device) return;
  const binding = state.device.binding || { status: "unbound" };
  const isBound = binding.status === "bound";
  const sync = state.device.config_sync_agent || {};
  const status = $("bindingStatus");
  setText("bindingStatus", isBound ? "已绑定" : "未绑定");
  if (status) status.className = `status-pill ${isBound ? "success" : "warning"}`;
  setText("bindingFamily", isBound ? (binding.family_name || "已绑定家庭") : "未绑定家庭");
  setText(
    "bindingOwner",
    isBound
      ? `${binding.owner_display_name || "家庭创建者"} · ${binding.owner_account || "账号已保护"}`
      : "可由家庭创建者通过回家 App 绑定"
  );
  setText("bindingTime", isBound ? fmtTime(binding.bound_at) : "-");
  const syncStatus = syncStatusPresentation(sync);
  setText("bindingCloudSync", syncStatus.label);
  const syncTarget = $("bindingCloudSync");
  if (syncTarget) {
    syncTarget.className = `cloud-sync-status ${syncStatus.tone}`;
    syncTarget.title = syncStatus.detail;
  }
  state.bindingClosesAt = Date.parse(state.device.pairing?.closes_at || "") || 0;
  renderPairingCountdown();
  const button = $("openPairingWindow");
  if (button) {
    button.hidden = isBound;
  }
}

async function openPairingWindow(button) {
  setBusy(button, true);
  try {
    const result = await api("/api/admin/pairing-window", { method: "POST" });
    state.device.pairing = result.pairing;
    state.bindingClosesAt = Date.parse(result.pairing?.closes_at || "") || 0;
    renderPairingCountdown();
    showToast("安全配对已开启 10 分钟，请返回 App 重新搜索盒子");
  } finally {
    setBusy(button, false);
  }
}

function cameraConfigIsCloudManaged() {
  return state.cameraConfigAuthority?.mode === "cloud_managed";
}

function renderCameraConfigAuthority() {
  if (pageName !== "cameras") return;
  const managed = cameraConfigIsCloudManaged();
  setText(
    "cameraSourceHint",
    managed
      ? "正式摄像头列表由回家 App 统一管理；本页只用于局域网扫描和连接测试。"
      : "盒子尚未绑定云端，可在本页完成安装调试。"
  );
  updateCameraLimitState();
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
    if (pageName === "algorithms") {
      renderEmptySnapshot();
    } else {
      await loadSnapshot(state.selectedCameraId).catch(renderEmptySnapshot);
    }
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
  const managed = cameraConfigIsCloudManaged();
  setText(
    "cameraLimitHint",
    managed
      ? `云端已同步 ${count} 路摄像头；增删和启停请在回家 App 操作。`
      : `已接入 ${count}/${state.maxCameras} 路摄像头，还可新增 ${remaining} 路。`
  );
  const submit = $("cameraForm")?.querySelector('button[type="submit"]');
  const target = normalizeStreamUrl(cameraPayloadPreviewUrl());
  const editingExisting = physicalCameras().some((camera) => normalizeStreamUrl(camera.stream_url) === target);
  if (submit) {
    submit.disabled = managed || (count >= state.maxCameras && !editingExisting);
    submit.innerHTML = submit.disabled
      ? managed
        ? '<span class="material-symbols-outlined">cloud_sync</span>请在 App 配置'
        : '<span class="material-symbols-outlined">block</span>已达 3 路上限'
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
          ${cameraConfigIsCloudManaged()
            ? '<span class="camera-badge">云端同步</span>'
            : `<button class="ghost-button" type="button" data-action="toggle" data-id="${camera.id}" data-enabled="${camera.enabled ? "1" : "0"}">${camera.enabled ? "禁用" : "启用"}</button>
               <button class="ghost-button danger" type="button" data-action="delete" data-id="${camera.id}">删除</button>`}
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
  if (cameraConfigIsCloudManaged()) {
    throw new Error("摄像头配置由回家 App 统一管理");
  }
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

function frameSequenceForCamera(frameId, cameraId) {
  const prefix = `${cameraId}-`;
  const value = String(frameId || "");
  if (!value.startsWith(prefix)) return null;
  const sequence = value.slice(prefix.length);
  return /^\d+$/.test(sequence) ? Number(sequence) : null;
}

function ensureLiveStreamLifecycle(cameraId, tracking, frameId) {
  const stream = $("mjpegStream");
  if (!stream || selectedCamera()?.id !== cameraId || !stream.getAttribute("src")) return;

  const sourceKey = String(tracking?.source_key || "").trim();
  const frameSequence = frameSequenceForCamera(frameId, cameraId);
  const sourceChanged = Boolean(
    sourceKey
    && state.lastAnalysisSourceKey
    && sourceKey !== state.lastAnalysisSourceKey
  );
  const sequenceRegressed = Number.isFinite(frameSequence)
    && Number.isFinite(state.lastAnalysisFrameSequence)
    && frameSequence < state.lastAnalysisFrameSequence;
  const imageUnavailable = stream.complete
    && stream.naturalWidth === 0
    && Date.now() - state.streamStartedAt >= 2500;

  if (sourceKey) state.lastAnalysisSourceKey = sourceKey;
  if (Number.isFinite(frameSequence)) state.lastAnalysisFrameSequence = frameSequence;
  if (!sourceChanged && !sequenceRegressed && !imageUnavailable) return;

  const now = Date.now();
  if (now - state.streamLastRecoveryAt < 800) return;
  state.streamLastRecoveryAt = now;
  renderStream({ retry: true });
}

function renderStream({ retry = false } = {}) {
  const stream = $("mjpegStream");
  if (!stream) return;
  const empty = $("streamEmpty");
  const camera = selectedCamera();
  clearTimeout(state.streamMaskTimer);
  clearTimeout(state.streamReconnectTimer);
  if (!retry) state.streamReconnectAttempts = 0;
  if (pageName === "algorithms" && !retry) {
    stream.style.display = "block";
    state.lastAnalysisCapturedAt = 0;
    state.lastAnalysisFrameId = "";
    state.lastAnalysisSourceKey = "";
    state.lastAnalysisFrameSequence = null;
  }
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
    ? { fps: 15, width: 960, height: 540, quality: 70, label: "同步姿态视频" }
    : { fps: 15, width: 1280, height: 720, quality: 64, label: "720p 低延迟视频" };
  const streamPath = pageName === "algorithms"
    ? `/api/cameras/${camera.id}/continual-pose/stream.mjpg`
    : `/api/cameras/${camera.id}/stream.mjpg`;
  stream.src = `${streamPath}?fps=${streamProfile.fps}&width=${streamProfile.width}&height=${streamProfile.height}&quality=${streamProfile.quality}&privacy_mode=${encodeURIComponent(state.videoPrivacyMode)}&t=${Date.now()}`;
  state.streamStartedAt = Date.now();
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

function snapshotDisplayPoses(snapshot) {
  const continual = snapshot?.analysis?.continual_pose;
  if (["observed", "tracked", "coasting"].includes(continual?.state)) {
    return Array.isArray(continual.poses) ? continual.poses : [];
  }
  return snapshotPoses(snapshot);
}

function isPresenceCandidate(person) {
  const source = String(person?.source || "");
  return Boolean(person?.presence_candidate || source.startsWith("presence_"));
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
    meal_candidate: "用餐观察候选",
    stillness_candidate: "静止观察候选",
    daze_candidate: "久坐观察候选",
  };
  return labels[tag] || tag;
}

function algorithmVisibleTags(snapshot, mode = "unified") {
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
      "pose_hand_near_face", "fall_candidate", "meal_candidate", "stillness_candidate",
      "daze_candidate",
    ],
    quality: ["black_screen", "low_motion"],
    person: ["person_detected", "no_person_detected", "person_presence_candidate", "pose_detected", "pose_tracked", "pose_validated_person"],
    stillness: ["stillness_candidate", "daze_candidate", "low_motion", "person_detected", "pose_detected", "pose_tracked"],
    fall: ["fall_candidate", "pose_fall_candidate", "pose_low_body", "person_detected", "pose_detected", "pose_tracked"],
    meal: ["meal_candidate", "pose_hand_near_face", "person_detected", "pose_detected", "pose_tracked"],
    night: ["person_detected", "low_motion"],
    camera: ["black_screen", "low_motion"],
  };
  const allowed = new Set(allowlist[mode] || allowlist.quality);
  return sourceTags.filter((tag) => allowed.has(tag));
}

function algorithmNormalTagLabel(mode = "unified", snapshot = state.latestSnapshot) {
  const analysis = snapshot?.analysis || {};
  if (!snapshot) return "-";
  if (mode === "unified") {
    return unifiedSafetyState(snapshot).title;
  }
  if (mode === "person") return Number(snapshot.person_count ?? analysis.person_count ?? 0) > 0 ? "有人" : "无人";
  if (mode === "fall") return "未出现跌倒候选";
  if (mode === "meal") return "未形成用餐候选";
  if (mode === "stillness") return "活动正常";
  if (mode === "night") return "夜间规则待命";
  if (mode === "camera") return analysis.black_screen ? "摄像头异常" : "链路正常";
  return analysis.black_screen ? "质量异常" : "质量正常";
}

function unifiedSafetyState(snapshot) {
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  const poses = snapshotPoses(snapshot);
  const pets = snapshotPets(snapshot);
  const personCount = Number(snapshot?.person_count ?? analysis.person_count ?? people.length ?? 0);
  const fallRuntime = latestFallRuntime();
  const fallReview = ["suspect", "confirming"].includes(fallRuntime.stage);
  const postureSummary = [...new Set(poses.map((pose) => postureLabel(pose.posture)).filter(Boolean))].join("、");
  const sceneSummary = [...new Set(unifiedSceneTargets(snapshot).map(sceneLabel).filter(Boolean))].join("、");
  const context = [
    postureSummary ? `姿态 ${postureSummary}` : "",
    sceneSummary ? `场景 ${sceneSummary}` : "",
  ].filter(Boolean).join(" · ");

  if (!snapshot) return { level: "idle", title: "等待检测", detail: "等待当前视频帧" };
  if (analysis.black_screen) return { level: "critical", title: "摄像头画面异常", detail: "画面亮度或对比度异常" };
  if (fallRuntime.stage === "confirmed") {
    return { level: "critical", title: "跌倒事件已触发", detail: fallStageInfo(fallRuntime.stage, { personCount }).detail };
  }
  if (fallReview) {
    return { level: "watch", title: "跌倒过程复核中", detail: fallStageInfo(fallRuntime.stage, { personCount }).detail };
  }
  if (personCount > 0 || poses.length > 0) {
    return { level: "hit", title: `人物活动正常`, detail: context || `持续跟踪 ${personCount || poses.length} 人` };
  }
  if (pets.length > 0) return { level: "hit", title: "当前未看到人", detail: `检测到 ${pets.length} 只宠物` };
  return {
    level: "idle",
    title: "当前画面无人",
    detail: sceneSummary ? `场景 ${sceneSummary}` : "持续巡检中",
  };
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

function renderPerceptionTargetList(snapshot) {
  const target = $("perceptionTargetList");
  if (!target) return;
  if (!snapshot) {
    target.innerHTML = '<div class="empty-state">等待人物、姿态与场景目标。</div>';
    setText("sceneMapStatus", "场景学习中");
    return;
  }
  const analysis = snapshot.analysis || {};
  const poses = snapshotDisplayPoses(snapshot);
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
    image.src = String(snapshot.image_url).startsWith("data:")
      ? snapshot.image_url
      : `${snapshot.image_url}?t=${Date.now()}`;
  }
  if ($("snapshotEmpty")) $("snapshotEmpty").style.display = "none";
  setText("snapshotTime", fmtTime(snapshot.captured_at));
  setText("snapshotBrightness", fmtNumber(analysis.brightness ?? snapshot.brightness, 1));
  setText("snapshotContrast", fmtNumber(analysis.contrast, 1));
  setText("snapshotMotion", analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4));
  const personCount = snapshot.person_count ?? analysis.person_count ?? "-";
  const petCount = analysis.pet_count ?? snapshotPets(snapshot).length;
  setText("snapshotPeople", petCount ? `${personCount} / 宠${petCount}` : personCount);
  setText("snapshotPoseCount", analysis.pose_count ?? snapshotPoses(snapshot).length);
  setText("snapshotSceneCount", unifiedSceneTargets(snapshot).length);
  setText("snapshotQualityState", analysis.black_screen ? "异常" : "正常");
  const visibleTags = algorithmVisibleTags(snapshot);
  setText("snapshotTags", visibleTags.length ? visibleTags.map(tagLabel).join("，") : algorithmNormalTagLabel("unified", snapshot));
  renderDetectionSummary(snapshot);
  renderPerceptionTargetList(snapshot);
  renderAlgorithmHitStrip(snapshot);
  renderContinualPoseStatus(snapshot);
}

function renderContinualPoseStatus(snapshot) {
  const tracking = snapshot?.analysis?.continual_pose || {};
  const trackingState = String(tracking.state || "empty");
  const sourceLabels = {
    observed: "连续姿态",
    tracked: "连续姿态",
    coasting: "短暂补偿",
    expired: "跟踪已清除",
    empty: "等待人物",
  };
  setText("continualPoseSource", sourceLabels[trackingState] || "等待连续感知");
  const hasAge = tracking.age_seconds !== null && tracking.age_seconds !== undefined && Number.isFinite(Number(tracking.age_seconds));
  const hasError = tracking.quality?.forward_backward_error !== null
    && tracking.quality?.forward_backward_error !== undefined
    && Number.isFinite(Number(tracking.quality.forward_backward_error));
  setText("continualPoseAge", hasAge ? `${Math.round(Number(tracking.age_seconds) * 1000)} ms` : "-");
  setText("continualPosePoints", tracking.quality?.tracked_point_count ?? "-");
  setText("continualPoseError", hasError ? Number(tracking.quality.forward_backward_error).toFixed(2) : "-");
  const target = $("continualPoseStatus");
  if (target) target.dataset.state = trackingState;
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
  const title = baseTitle;
  const levelClass = fallCandidate || blackScreen ? "bad" : people.length ? "" : "muted";
  const details = [
    `亮度 ${fmtNumber(analysis.brightness ?? snapshot?.brightness, 1)}`,
    `对比度 ${fmtNumber(analysis.contrast, 1)}`,
    `变化 ${analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4)}`,
    `人数 ${personCount}`,
    ...(pets.length ? [`宠物 ${pets.length}`] : []),
  ];
  target.innerHTML = `<span class="status-pill ${levelClass}">${escapeHtml(title)}</span><p>${escapeHtml(details.join(" · "))}</p>`;
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

function algorithmHitState(snapshot) {
  if (!snapshot) {
    return {
      hit: false,
      level: "idle",
      title: "等待检测",
      detail: "选择摄像头后自动分析当前画面",
      score: "-",
      scoreLabel: "当前目标",
      model: backendLabel(snapshot),
      latency: "-",
    };
  }
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  const pets = snapshotPets(snapshot);
  const poses = snapshotPoses(snapshot);
  const personCount = Number(snapshot?.person_count ?? analysis.person_count ?? people.length ?? 0);
  const safetyState = unifiedSafetyState(snapshot);
  const latency = snapshot.live_elapsed_ms ?? snapshot.elapsed_ms ?? snapshot.analysis_elapsed_ms;
  const frameAge = snapshot.frame_age_ms;
  const continualDisplay = Boolean(analysis.continual_pose);
  return {
    hit: personCount > 0 || poses.length > 0 || pets.length > 0,
    level: safetyState.level,
    title: safetyState.title,
    detail: safetyState.detail,
    score: `${personCount || poses.length || 0} 人 / ${pets.length} 只宠物`,
    scoreLabel: "当前目标",
    model: backendLabel(snapshot),
    latency: continualDisplay
      ? Number.isFinite(Number(frameAge)) ? `${(Number(frameAge) / 1000).toFixed(1)}s` : "-"
      : latency === undefined || latency === null
        ? "分析中"
        : `${latency}ms${Number.isFinite(Number(frameAge)) ? ` · 帧龄 ${(Number(frameAge) / 1000).toFixed(1)}s` : ""}`,
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
      <span>${snapshot?.analysis?.continual_pose ? "画面帧龄" : "分析延迟"}</span>
      <strong>${escapeHtml(stateInfo.latency)}</strong>
      <small>${snapshot ? escapeHtml(fmtTime(snapshot.captured_at)) : "等待当前帧"}</small>
    </div>
  `;
}

function runtimeModeLabel(mode) {
  const labels = {
    idle: "巡检",
    active: "感知",
    risk: "高频",
  };
  return labels[String(mode || "")] || "-";
}

function renderRuntimeStatus(payload = state.runtimeStatus) {
  renderStreamHealth(payload);
  if (pageName !== "algorithms") return;
  const scheduler = payload?.inference_scheduler || {};
  const cameras = Array.isArray(scheduler.cameras) ? scheduler.cameras : [];
  const selected = cameras.find((camera) => Number(camera.camera_id) === Number(state.selectedCameraId)) || cameras[0] || {};
  const resource = scheduler.resource || {};
  const streams = payload?.camera_streams || {};
  const poseRunning = payload?.continual_pose_running;
  const video = runtimeVideoMetrics(payload, state.selectedCameraId);
  const fps = Number(video.outputFps);
  const inferenceFps = Number(video.modelFps);
  const temp = Number(resource.temperature_c);
  setText("runtimeMode", runtimeModeLabel(selected.mode));
  setText("runtimeFps", Number.isFinite(fps) && fps > 0 ? fps.toFixed(1) : "-");
  setText("runtimeTemp", Number.isFinite(temp) ? `${temp.toFixed(0)}°` : "-");
  setText("runtimeStreams", streams.managed_stream_count === undefined ? "-" : `${streams.managed_stream_count} 路`);
  setText(
    "runtimePose",
    poseRunning
      ? `Hailo ${Number.isFinite(inferenceFps) && inferenceFps > 0 ? inferenceFps.toFixed(1) : "-"} Hz`
      : "姿态待命",
  );
}

function runtimeVideoMetrics(payload, cameraId) {
  const streams = Array.isArray(payload?.camera_streams?.streams) ? payload.camera_streams.streams : [];
  const stream = streams.find((item) => Number(item.camera_id) === Number(cameraId)) || {};
  const trackers = Array.isArray(payload?.continual_pose?.cameras) ? payload.continual_pose.cameras : [];
  const tracker = trackers.find((item) => Number(item.camera_id) === Number(cameraId)) || {};
  const relay = payload?.live_relay_agent || {};
  const renderer = relay?.privacy_renderer || {};
  const privacy = renderer?.cameras?.[String(cameraId)] || {};
  const relayCamera = relay?.cameras?.[String(cameraId)] || {};
  const stageLatency = privacy?.stage_latency_ms || {};
  const segmentation = renderer?.person_segmentation || {};
  const synchronization = renderer?.synchronization_rejections?.[String(cameraId)] || {};
  const segmentationAssist = renderer?.segmentation_assists?.[String(cameraId)] || {};
  const mode = String(relay.privacy_mode || "original");
  const sourceFps = Number(stream.source_fps);
  const privacyFps = Number(privacy.output_fps);
  const poseFps = Number(tracker.display_output_fps);
  const modelFps = Number(tracker.model_anchor_fps);
  const segmentationLatencyMs = Number(segmentation.last_latency_ms);
  const renderLatencyP95Ms = Number(stageLatency?.total?.p95);
  const jpegLatencyP95Ms = Number(stageLatency?.jpeg_encode?.p95);
  const cloudAcceptedFps = Number(relayCamera.accepted_fps);
  const sourceToCloudP95Ms = Number(relayCamera.source_to_cloud_ms_p95);
  return {
    mode,
    sourceFps,
    poseFps,
    modelFps,
    segmentationStatus: String(segmentation.status || ""),
    segmentationLatencyMs,
    renderLatencyP95Ms,
    jpegLatencyP95Ms,
    cloudAcceptedFps,
    sourceToCloudP95Ms,
    synchronizationIssue: Number(synchronization.last_age_ms) <= 2500
      ? String(synchronization.last_reason || "")
      : "",
    segmentationAssisted: Number(segmentationAssist.last_age_ms) <= 2500,
    outputFps: mode === "original"
      ? sourceFps
      : Number.isFinite(privacyFps) && privacyFps > 0
        ? privacyFps
        : poseFps,
  };
}

function renderStreamHealth(payload = state.runtimeStatus) {
  const streams = Array.isArray(payload?.camera_streams?.streams)
    ? payload.camera_streams.streams
    : [];
  const selected = streams.find((stream) => Number(stream.camera_id) === Number(state.selectedCameraId));
  if (!selected) {
    setText("streamFrameTime", state.selectedCameraId ? "等待源流" : "未选择摄像头");
    setText("streamFpsBadge", "-- FPS");
    $("streamFpsBadge")?.classList.remove("is-live");
    return;
  }
  const video = runtimeVideoMetrics(payload, state.selectedCameraId);
  const fps = Number(video.outputFps);
  const sourceFps = Number(video.sourceFps);
  const modelFps = Number(video.modelFps);
  const segmentationLatencyMs = Number(video.segmentationLatencyMs);
  const renderLatencyP95Ms = Number(video.renderLatencyP95Ms);
  const jpegLatencyP95Ms = Number(video.jpegLatencyP95Ms);
  const cloudAcceptedFps = Number(video.cloudAcceptedFps);
  const sourceToCloudP95Ms = Number(video.sourceToCloudP95Ms);
  const ageMs = Number(selected.latest_frame_age_ms);
  if (selected.state === "retrying") {
    setText("streamFrameTime", "源流重连中");
    setText("streamFpsBadge", "重连中");
    $("streamFpsBadge")?.classList.remove("is-live");
    return;
  }
  if (selected.state === "stale") {
    setText("streamFrameTime", `源流延迟 ${Number.isFinite(ageMs) ? Math.round(ageMs) : "-"} ms`);
    setText("streamFpsBadge", "源流延迟");
    $("streamFpsBadge")?.classList.remove("is-live");
    return;
  }
  const modeLabel = video.mode === "skeleton" ? "骨架" : video.mode === "person_blur" ? "模糊" : "原画";
  const fpsLabel = Number.isFinite(fps) && fps > 0 ? `${modeLabel} ${fps.toFixed(1)} FPS` : `${modeLabel}预热`;
  const sourceLabel = Number.isFinite(sourceFps) && sourceFps > 0 && video.mode !== "original"
    ? ` · 源流 ${sourceFps.toFixed(1)} FPS`
    : "";
  const modelLabel = Number.isFinite(modelFps) && modelFps > 0
    ? ` · Hailo ${modelFps.toFixed(1)} Hz`
    : "";
  const segmentationLabel = video.mode === "original"
    ? ""
    : video.synchronizationIssue
      ? " · 帧同步异常"
      : video.segmentationAssisted
        ? " · 轮廓补偿"
      : video.segmentationStatus === "degraded"
      ? " · 人体分割异常"
      : Number.isFinite(segmentationLatencyMs) && segmentationLatencyMs > 0
        ? ` · 分割 ${segmentationLatencyMs.toFixed(0)} ms`
        : " · 分割预热";
  const ageLabel = Number.isFinite(ageMs) ? ` · 帧龄 ${Math.round(ageMs)} ms` : "";
  const renderLabel = Number.isFinite(renderLatencyP95Ms) && renderLatencyP95Ms > 0
    ? ` · 合成 P95 ${renderLatencyP95Ms.toFixed(0)} ms`
    : "";
  const jpegLabel = Number.isFinite(jpegLatencyP95Ms) && jpegLatencyP95Ms > 0
    ? ` · JPEG P95 ${jpegLatencyP95Ms.toFixed(0)} ms`
    : "";
  const cloudLabel = Number.isFinite(cloudAcceptedFps) && cloudAcceptedFps > 0
    ? ` · 云端 ${cloudAcceptedFps.toFixed(1)} FPS${Number.isFinite(sourceToCloudP95Ms) && sourceToCloudP95Ms > 0 ? ` / P95 ${sourceToCloudP95Ms.toFixed(0)} ms` : ""}`
    : " · 云端预热";
  const frameMetric = $("streamFrameTime");
  setText("streamFrameTime", `${fpsLabel}${sourceLabel}${cloudLabel}${ageLabel}`);
  if (frameMetric) {
    frameMetric.title = `${fpsLabel}${sourceLabel}${modelLabel}${segmentationLabel}${renderLabel}${jpegLabel}${cloudLabel}${ageLabel}`;
  }
  setText("streamFpsBadge", Number.isFinite(fps) && fps > 0 ? `${fps.toFixed(1)} FPS` : "-- FPS");
  $("streamFpsBadge")?.classList.toggle("is-live", Number.isFinite(fps) && fps > 0);
}

async function loadRuntimeStatus() {
  if (!["home", "algorithms"].includes(pageName)) return;
  const payload = await api("/api/rules/runtime");
  state.runtimeStatus = payload;
  renderRuntimeStatus(payload);
}

function renderEmptySnapshot() {
  state.latestSnapshot = null;
  if ($("snapshotImage")) $("snapshotImage").removeAttribute("src");
  if ($("snapshotEmpty")) $("snapshotEmpty").style.display = "grid";
  for (const id of ["snapshotTime", "streamFrameTime", "snapshotBrightness", "snapshotContrast", "snapshotMotion", "snapshotPeople", "snapshotTags", "snapshotPoseCount", "snapshotSceneCount", "snapshotFireState", "snapshotQualityState"]) {
    setText(id, "-");
  }
  renderPerceptionTargetList(null);
  renderAlgorithmHitStrip(null);
  renderContinualPoseStatus(null);
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
  return livePosePollIntervalMs;
}

function stopLiveAnalysisLoop() {
  clearTimeout(state.liveAnalysisTimer);
  state.liveAnalysisTimer = null;
  state.liveAnalysisGeneration += 1;
}

function scheduleLiveAnalysis(delay = liveAnalysisDelay(), generation = state.liveAnalysisGeneration) {
  if (pageName !== "algorithms") return;
  clearTimeout(state.liveAnalysisTimer);
  state.liveAnalysisTimer = setTimeout(() => {
    if (generation === state.liveAnalysisGeneration) loadLiveAnalysis(generation).catch(() => null);
  }, delay);
}

function startLiveAnalysisLoop() {
  if (pageName !== "algorithms") return;
  clearTimeout(state.liveAnalysisTimer);
  state.liveAnalysisGeneration += 1;
  const generation = state.liveAnalysisGeneration;
  state.lastAnalysisCapturedAt = 0;
  state.lastAnalysisFrameId = "";
  if (!state.selectedCameraId) {
    renderAlgorithmHitStrip(null);
    return;
  }
  loadLiveAnalysis(generation).catch(() => null);
}

async function loadLiveAnalysis(generation = state.liveAnalysisGeneration) {
  if (pageName !== "algorithms" || !state.selectedCameraId) return;
  if (document.hidden) {
    scheduleLiveAnalysis(3200, generation);
    return;
  }
  if (generation !== state.liveAnalysisGeneration) return;
  if (state.liveAnalysisBusy) {
    scheduleLiveAnalysis(100, generation);
    return;
  }
  const cameraId = state.selectedCameraId;
  let nextDelay = liveAnalysisDelay();
  state.liveAnalysisBusy = true;
  try {
    const statusResult = await api(`/api/cameras/${cameraId}/continual-pose/live?include_frame=false`);
    if (
      generation !== state.liveAnalysisGeneration
      || cameraId !== state.selectedCameraId
    ) return;
    const result = statusResult;
    if (!result.snapshot) return;
    const snapshot = {
      ...(result.snapshot || {}),
      analysis: result.analysis || result.snapshot?.analysis || {},
      live_elapsed_ms: result.analysis_elapsed_ms ?? result.elapsed_ms ?? 0,
      frame_id: result.frame_id || result.snapshot?.frame_id || result.tracking?.frame_id || "",
    };
    const frameId = String(snapshot.frame_id || "").trim();
    const tracking = result.tracking || snapshot.analysis?.continual_pose || {};
    ensureLiveStreamLifecycle(cameraId, tracking, frameId);
    const capturedAt = Date.parse(snapshot.captured_at || result.captured_at || "");
    const duplicateFrame = Boolean(frameId && frameId === state.lastAnalysisFrameId);
    const duplicateTimestamp = !frameId && Number.isFinite(capturedAt) && capturedAt <= state.lastAnalysisCapturedAt;
    if (duplicateFrame || duplicateTimestamp) return;
    if (frameId) state.lastAnalysisFrameId = frameId;
    if (Number.isFinite(capturedAt)) {
      state.lastAnalysisCapturedAt = capturedAt;
      snapshot.frame_age_ms = Math.max(0, Date.now() - capturedAt);
    }
    if (Number.isFinite(Number(snapshot.frame_age_ms)) && Number(snapshot.frame_age_ms) > 2500) {
      const staleTracking = snapshot.analysis?.continual_pose || result.tracking || {};
      snapshot.analysis = {
        ...snapshot.analysis,
        people: [],
        person_count: 0,
        poses: [],
        pose_count: 0,
        continual_pose: {
          ...staleTracking,
          state: "expired",
          reason: staleTracking.reason || "display_stale",
          poses: [],
        },
      };
      snapshot.person_count = 0;
    }
    state.liveAnalysisErrorShown = false;
    renderSnapshot(snapshot);
    if (Date.now() - state.liveEvaluationUpdatedAt >= 3000) {
      state.liveEvaluationUpdatedAt = Date.now();
      loadEvaluation(cameraId).catch(renderEmptyEvaluation);
    }
  } catch (error) {
    nextDelay = error?.status === 401 ? 3000 : 800;
    setText("continualPoseSource", "姿态暂不可用");
    if ($("continualPoseStatus")) $("continualPoseStatus").dataset.state = "expired";
    if (!state.liveAnalysisErrorShown) {
      showToast(userSafeError(error.message || "实时识别失败"));
      state.liveAnalysisErrorShown = true;
    }
  } finally {
    state.liveAnalysisBusy = false;
    if (generation === state.liveAnalysisGeneration) scheduleLiveAnalysis(nextDelay, generation);
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
    renderDetectionSummary(state.latestSnapshot);
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
  if (
    local.type === "camera_offline"
    && (local.payload?.resolution === "camera_reconnected" || local.camera_status === "online")
  ) {
    return { key: "closed", label: "当前已恢复", tone: "muted" };
  }
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
    const displaySummary = local.type === "camera_offline" && local.camera_status === "online"
      ? `${local.camera_name || "摄像头"} 曾发生连接中断，当前已恢复`
      : (local.summary || eventTypeLabel(local.type));
    const thumbnail = local.snapshot_url
      ? `<button class="event-evidence-thumb" type="button" data-event-log-action="snapshot" data-url="${escapeHtml(local.snapshot_url)}"><img src="${escapeHtml(local.snapshot_url)}" alt=""><span>证据帧</span></button>`
      : '<div class="event-evidence-thumb empty"><span>无证据帧</span></div>';
    return `
      <article class="event-log-card ${escapeHtml(lifecycle.tone || "")}">
        <header>
          <div>
            <span class="event-type-mark">${escapeHtml(eventTypeLabel(local.type))}</span>
            <h2>${escapeHtml(displaySummary)}</h2>
            <p>${escapeHtml([local.camera_name || local.room || "盒子", fmtTime(local.occurred_at), `本地 #${local.id}`, cloud?.event_id ? `云端 #${cloud.event_id}` : ""].filter(Boolean).join(" · "))}</p>
          </div>
          <span class="status-pill ${escapeHtml(lifecycle.tone || "")}">${escapeHtml(lifecycle.label)}</span>
        </header>
        <div class="event-log-media-row">
          ${thumbnail}
          <div class="event-chain">
            ${eventLogStage("盒子触发", "规则事件", "done")}
            ${eventLogStage(syncStage.label, uploadError || (local.snapshot_url ? "事件 + 截图" : "结构化数据"), syncStage.state)}
            ${eventLogStage(cloudStage.label, cloud ? "ID 已匹配" : "等待入库", cloudStage.state)}
            ${eventLogStage(lifecycle.label, resultReason || (incidentId ? `事故 ${incidentId}` : "等待状态"), ["confirmed", "attention"].includes(lifecycle.key) ? "failed" : ["rejected", "closed", "synced"].includes(lifecycle.key) ? "done" : "active")}
          </div>
        </div>
        ${pills.length ? `<div class="candidate-evidence">${pills.slice(0, 6).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
        <footer>
          <span>${incidentId ? `事件 ${escapeHtml(incidentId)}` : "云端状态会自动回写到此处"}</span>
          <div class="event-log-actions">
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

const algorithmRecordScope = Object.freeze({
  candidateTypes: ["fall_candidate", "black_screen", "camera_offline", "no_person", "no_motion"],
  observationTypes: ["no_person", "no_motion"],
  candidateTitle: "最近安全记录",
  observationTitle: "最近生活观察",
  observationSubtitle: "统一时间线",
  candidateEmpty: "当前没有需要处理的安全记录。",
  observationEmpty: "当前没有持续无人或低活动观察。",
});

function matchesTypeScope(recordType, allowedTypes) {
  return allowedTypes.length > 0 && allowedTypes.includes(String(recordType || ""));
}

function renderCandidatePanel(candidates = state.candidateRecords) {
  const list = $("candidateList");
  if (!list) return;
  const scope = algorithmRecordScope;
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
        <div class="cinema-card-meta">
          <span>${escapeHtml(category)}</span>
          <span>${escapeHtml(meta || `#${candidate.id || "-"}`)}</span>
          ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
        </div>
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
  const scope = algorithmRecordScope;
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
        <div class="cinema-card-meta">
          <span>${escapeHtml(meta)}</span>
          <span>${escapeHtml(log.status === "open" ? fmtTime(log.last_seen_at) : fmtTime(log.ended_at))}</span>
        </div>
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
        <div class="cinema-card-meta">
          <span>${escapeHtml([record.room, fmtTime(record.updated_at || record.occurred_at), record.job?.model].filter(Boolean).join(" · "))}</span>
          <span>${escapeHtml(reason)}</span>
        </div>
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
    await loadRuntimeStatus().catch(() => null);
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
  document.querySelectorAll("[data-privacy-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      updateVideoPrivacyMode(button.dataset.privacyMode, button)
        .catch((error) => showToast(userSafeError(error.message)));
    });
  });
  on("refreshAll", "click", refreshAll);
  on("openPairingWindow", "click", (event) => openPairingWindow(event.currentTarget).catch((error) => showToast(userSafeError(error.message))));
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
    stopLiveAnalysisLoop();
    state.selectedCameraId = Number(event.currentTarget.value);
    renderStream();
    if (pageName === "algorithms") {
      renderEmptySnapshot();
    } else {
      await loadSnapshot(state.selectedCameraId).catch(renderEmptySnapshot);
    }
    await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
    await loadRuntimeStatus().catch(() => null);
    startLiveAnalysisLoop();
  });
  on("modeLan", "click", () => setCameraMode("lan"));
  on("modeRtsp", "click", () => setCameraMode("rtsp"));
  on("quickLocal", "click", () => setCameraMode("local"));
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
}

document.addEventListener("DOMContentLoaded", () => {
  hydrateAdminSession();
  ensureVideoPrivacyControl();
  bindEvents();
  if (pageName === "cameras") setCameraMode("lan");
  loadVideoPrivacyMode({ refreshStream: false })
    .catch(() => null)
    .finally(() => refreshAll());
  if (pageName === "cameras" && $("cameraDiscoveryList")) {
    setTimeout(() => discoverCameras($("discoverCameras")).catch(() => renderCameraDiscovery()), 400);
  }
  state.refreshTimer = setInterval(() => {
    if (pageName === "home") loadDevice().catch(() => null);
    if (pageName === "home" && state.selectedCameraId) {
      loadSnapshot(state.selectedCameraId).catch(() => null);
      loadEvaluation(state.selectedCameraId).catch(() => null);
    }
    if (pageName === "home" || pageName === "algorithms") {
      loadRuntimeStatus().catch(() => null);
      loadCandidates().catch(() => null);
      loadObservationLogs().catch(() => null);
      loadUploadQueueSummary().catch(() => null);
      loadCloudVerifications().catch(() => null);
    }
    if (pageName === "events") loadEventLog().catch(() => null);
  }, 6000);
  state.privacyTimer = setInterval(() => {
    if (!document.hidden) loadVideoPrivacyMode().catch(() => null);
  }, 5000);
  setInterval(renderPairingCountdown, 1000);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopLiveAnalysisLoop();
      return;
    }
    if (pageName === "algorithms") startLiveAnalysisLoop();
  });
});
