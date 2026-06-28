const pageName = document.body.dataset.page || "home";

const state = {
  cameras: [],
  selectedCameraId: null,
  cameraMode: "lan",
  detectorBackend: "basic",
  eventFilter: "open",
  latestSnapshot: null,
  refreshTimer: null,
  streamMaskTimer: null,
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

function isLocalStreamUrl(value) {
  const streamUrl = String(value ?? "").trim().toLowerCase();
  return /^(local|webcam|device|camera):/.test(streamUrl) || /^\d+$/.test(streamUrl);
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
  if (status === "error") return "错误";
  return "未知";
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

async function loadDevice() {
  const device = await api("/api/device");
  state.detectorBackend = device.detector_backend || "basic";
  setText("detectorBackend", device.detector_backend || "-");
  setText("notifyChannel", device.notify_channel || "off");
  setText("dataDir", device.data_dir || "-");
  setText("yoloModel", device.yolo_model || "basic 模式未加载");
  setText("workerBadge", device.worker_running ? "worker 运行中" : "worker 已停止");
  if ($("workerBadge")) $("workerBadge").className = `status-pill ${device.worker_running ? "" : "bad"}`;
  renderYoloState();
}

async function loadCameras(options = {}) {
  state.cameras = await api("/api/cameras");
  const current = selectedCamera();
  if (!current || !current.enabled || options.preferNetwork) {
    state.selectedCameraId = preferredCameraId(state.cameras);
  }
  renderCameraSelect();
  renderCameraList();
  renderStream();
  if (state.selectedCameraId) {
    await loadSnapshot(state.selectedCameraId).catch(renderEmptySnapshot);
    await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
  } else {
    renderEmptySnapshot();
    renderEmptyEvaluation();
  }
}

function renderCameraSelect() {
  const select = $("cameraSelect");
  if (!select) return;
  select.innerHTML = state.cameras.length
    ? state.cameras.map((camera) => `
      <option value="${camera.id}" ${Number(camera.id) === Number(state.selectedCameraId) ? "selected" : ""}>
        ${escapeHtml(camera.name)} · ${escapeHtml(camera.room || "未设置")} · ${statusText(camera.status)}
      </option>
    `).join("")
    : '<option value="">还没有摄像头</option>';
}

function renderCameraList() {
  const list = $("cameraList");
  if (!list) return;
  if (!state.cameras.length) {
    list.innerHTML = '<div class="empty-state">还没有摄像头。填写左侧表单后保存并测试。</div>';
    return;
  }
  list.innerHTML = state.cameras.map((camera) => {
    const active = Number(camera.id) === Number(state.selectedCameraId);
    const typeLabel = isLocalStreamUrl(camera.stream_url) ? "本机" : "局域网";
    return `
      <article class="camera-row ${active ? "active" : ""} ${camera.enabled ? "" : "disabled"}">
        <div>
          <h3>${escapeHtml(camera.name)} · ${escapeHtml(camera.room || "未设置房间")}
            <span class="camera-badge">${typeLabel}</span>
            ${camera.enabled ? "" : '<span class="camera-badge muted">已禁用</span>'}
          </h3>
          <p>${escapeHtml(camera.stream_url)} · ${statusText(camera.status)}${camera.last_error ? ` · ${escapeHtml(camera.last_error)}` : ""}</p>
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
  let path = $("cameraPath")?.value.trim() || "/";
  if (!path.startsWith("/")) path = `/${path}`;
  if (!host) return "";
  return `rtsp://${host}:${port}${path}`;
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
  for (const id of ["cameraHostField", "cameraPortField", "cameraUserField", "cameraPasswordField", "cameraPathField"]) {
    if ($(id)) {
      $(id).classList.toggle("hidden", !lan);
      $(id).hidden = !lan;
    }
  }
  if ($("cameraUrlField")) {
    $("cameraUrlField").classList.toggle("hidden", lan);
    $("cameraUrlField").hidden = lan;
  }
  if (mode === "lan") {
    if ($("cameraName")) $("cameraName").value = "局域网摄像头";
    if ($("cameraRoom")) $("cameraRoom").value = "客厅";
    if ($("cameraHost")) $("cameraHost").value ||= "192.168.1.11";
    if ($("cameraPort")) $("cameraPort").value ||= "554";
    if ($("cameraUsername")) $("cameraUsername").value ||= "admin";
    if ($("cameraPath")) $("cameraPath").value ||= "/";
    syncLanUrlPreview();
  }
  if (mode === "rtsp") {
    if ($("cameraName")) $("cameraName").value = "RTSP 摄像头";
    if ($("cameraRoom")) $("cameraRoom").value = "客厅";
    if ($("cameraUrl")) $("cameraUrl").value = buildLanRtspUrl();
  }
  if (mode === "local") {
    if ($("cameraName")) $("cameraName").value = "笔记本摄像头";
    if ($("cameraRoom")) $("cameraRoom").value = "本机测试";
    if ($("cameraUrl")) $("cameraUrl").value = "local:0";
  }
}

function cameraPayloadFromForm() {
  const name = $("cameraName").value.trim();
  const room = $("cameraRoom").value.trim();
  if (state.cameraMode === "lan") {
    const streamUrl = buildLanRtspUrl();
    if (!streamUrl) throw new Error("请填写摄像头 IP");
    return {
      name: name || "局域网摄像头",
      room,
      stream_url: streamUrl,
      username: $("cameraUsername").value.trim() || null,
      password: $("cameraPassword").value || null,
      enabled: true,
    };
  }
  const streamUrl = $("cameraUrl").value.trim();
  if (!streamUrl) throw new Error("请填写视频地址");
  return {
    name: name || (state.cameraMode === "local" ? "笔记本摄像头" : "RTSP 摄像头"),
    room,
    stream_url: streamUrl,
    username: null,
    password: null,
    enabled: true,
  };
}

async function saveCamera(payload) {
  const target = normalizeStreamUrl(payload.stream_url);
  const existing = state.cameras.find((camera) => normalizeStreamUrl(camera.stream_url) === target);
  const camera = existing
    ? await api(`/api/cameras/${existing.id}`, { method: "PATCH", body: JSON.stringify(payload) })
    : await api("/api/cameras", { method: "POST", body: JSON.stringify(payload) });
  state.selectedCameraId = camera.id;
  await testCamera(camera.id);
  showToast(existing ? "摄像头已更新并测试" : "摄像头已保存并测试");
}

async function testCamera(cameraId, button) {
  setBusy(button, true);
  try {
    const result = await api(`/api/cameras/${cameraId}/test`, { method: "POST" });
    state.selectedCameraId = cameraId;
    renderSnapshot(result.snapshot);
    showToast(`抓到 ${result.width}x${result.height} 画面`);
    await loadCameras();
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
  setText("streamCamera", `${camera.name} · ${camera.room || "未设置"}`);
}

function snapshotPeople(snapshot) {
  const people = snapshot?.analysis?.people;
  return Array.isArray(people) ? people : [];
}

function tagLabel(tag) {
  const labels = {
    black_screen: "黑屏/遮挡",
    low_motion: "低变化",
    person_detected: "检测到人",
    no_person_detected: "暂未检测到人",
    fall_candidate: "疑似跌倒候选",
  };
  return labels[tag] || tag;
}

function imageFitRect(snapshot) {
  const stage = $("previewStage");
  const image = $("snapshotImage");
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
  const people = snapshotPeople(snapshot);
  const rect = imageFitRect(snapshot);
  if (!snapshot || !rect || !people.length) {
    overlay.innerHTML = "";
    overlay.removeAttribute("style");
    return;
  }
  overlay.style.left = `${rect.left}px`;
  overlay.style.top = `${rect.top}px`;
  overlay.style.width = `${rect.width}px`;
  overlay.style.height = `${rect.height}px`;
  overlay.innerHTML = people.map((person, index) => {
    const [x1, y1, x2, y2] = person.bbox || [0, 0, 0, 0];
    const left = clamp((Number(x1) / rect.imageWidth) * 100, 0, 100);
    const top = clamp((Number(y1) / rect.imageHeight) * 100, 0, 100);
    const right = clamp((Number(x2) / rect.imageWidth) * 100, 0, 100);
    const bottom = clamp((Number(y2) / rect.imageHeight) * 100, 0, 100);
    const width = clamp(right - left, 0, 100 - left);
    const height = clamp(bottom - top, 0, 100 - top);
    const label = `人 ${index + 1}${person.confidence ? ` · ${Math.round(person.confidence * 100)}%` : ""}`;
    return `
      <div class="detection-box ${person.fall_candidate ? "fall" : ""}" style="left:${left}%;top:${top}%;width:${width}%;height:${height}%">
        <span>${escapeHtml(person.fall_candidate ? `${label} · 疑似跌倒` : label)}</span>
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
}

function renderDetectionSummary(snapshot) {
  const target = $("detectionSummary");
  if (!target) return;
  const analysis = snapshot?.analysis || {};
  const people = snapshotPeople(snapshot);
  const fallCandidate = Boolean(analysis.fall_candidate);
  const blackScreen = Boolean(analysis.black_screen);
  const backend = analysis.detector_backend || state.detectorBackend || "basic";
  const title = fallCandidate ? "疑似跌倒候选" : blackScreen ? "画面异常" : backend === "yolo" ? "YOLO 已运行" : "基础检测";
  const levelClass = fallCandidate || blackScreen ? "bad" : people.length ? "" : "muted";
  const details = [
    `后端 ${backend}`,
    `亮度 ${fmtNumber(analysis.brightness ?? snapshot?.brightness, 1)}`,
    `对比度 ${fmtNumber(analysis.contrast, 1)}`,
    `变化 ${analysis.motion_score === null || analysis.motion_score === undefined ? "-" : fmtNumber(analysis.motion_score, 4)}`,
    `人数 ${snapshot?.person_count ?? analysis.person_count ?? "-"}`,
  ];
  target.innerHTML = `<span class="status-pill ${levelClass}">${escapeHtml(title)}</span><p>${escapeHtml(details.join(" · "))}</p>`;
}

function renderEmptySnapshot() {
  state.latestSnapshot = null;
  if ($("snapshotImage")) $("snapshotImage").removeAttribute("src");
  if ($("snapshotEmpty")) $("snapshotEmpty").style.display = "grid";
  if ($("detectionOverlay")) $("detectionOverlay").innerHTML = "";
  for (const id of ["snapshotTime", "streamFrameTime", "snapshotBrightness", "snapshotContrast", "snapshotMotion", "snapshotPeople", "snapshotTags"]) {
    setText(id, "-");
  }
}

async function loadSnapshot(cameraId) {
  const snapshot = await api(`/api/cameras/${cameraId}/snapshot/latest`);
  renderSnapshot(snapshot);
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
    : "当前检测结果没有生成告警候选。";
  $("ruleEvaluation").innerHTML = `
    <div>
      <span class="status-pill ${hasCandidates ? "bad" : ""}">${hasCandidates ? `${candidates.length} 个候选` : "未命中规则"}</span>
      <p>${escapeHtml(candidateText)} · 无人 ${escapeHtml(fmtDuration(evalState.no_person_seconds))} · 无变化 ${escapeHtml(fmtDuration(evalState.no_motion_seconds))}</p>
    </div>
  `;
}

function renderEmptyEvaluation() {
  if (!$("ruleEvaluation")) return;
  $("ruleEvaluation").innerHTML = `
    <div>
      <span class="status-pill muted">等待规则</span>
      <p>worker 还没有生成规则评估，抓帧或等待下一轮。</p>
    </div>
  `;
}

async function loadEvents() {
  const list = $("eventList");
  if (!list) return;
  const params = new URLSearchParams({ limit: "40" });
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
    ["notificationEnabled", "notification_enabled"],
  ]) {
    if ($(id)) $(id).checked = Boolean(rules[key]);
  }
}

function renderYoloState() {
  const yoloEnabled = state.detectorBackend === "yolo";
  for (const id of ["personDetectionEnabled", "fallDetectionEnabled", "yoloConfidence"]) {
    if ($(id)) $(id).disabled = !yoloEnabled;
  }
  if ($("yoloHint")) {
    $("yoloHint").textContent = yoloEnabled
      ? "YOLO 模式已启用：人形、无人和跌倒候选会参与下一轮检测。"
      : "当前是 basic 模式：只运行亮度、对比度、运动检测。需要 YOLO 时用 GOHOME_DETECTOR_BACKEND=yolo 重启服务。";
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
        person_detection_enabled: $("personDetectionEnabled").checked && state.detectorBackend === "yolo",
        fall_detection_enabled: $("fallDetectionEnabled").checked && state.detectorBackend === "yolo",
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
    await Promise.all([loadDevice(), loadRules().catch(() => null)]);
    await loadCameras();
    await loadEvents();
  } catch (error) {
    showToast(error.message || "无法连接 edge-agent");
  }
}

function bindEvents() {
  on("refreshAll", "click", refreshAll);
  on("captureSelected", "click", (event) => captureSelected(event.currentTarget).catch((error) => showToast(error.message)));
  on("saveRules", "click", (event) => saveRules(event.currentTarget).catch((error) => showToast(error.message)));
  on("clearDoneEvents", "click", () => clearDoneEvents().catch((error) => showToast(error.message)));
  on("eventFilter", "change", (event) => {
    state.eventFilter = event.target.value;
    loadEvents().catch((error) => showToast(error.message));
  });
  on("cameraSelect", "change", async (event) => {
    state.selectedCameraId = Number(event.currentTarget.value);
    renderStream();
    await loadSnapshot(state.selectedCameraId).catch(renderEmptySnapshot);
    await loadEvaluation(state.selectedCameraId).catch(renderEmptyEvaluation);
  });
  on("modeLan", "click", () => setCameraMode("lan"));
  on("modeRtsp", "click", () => setCameraMode("rtsp"));
  on("quickLocal", "click", () => setCameraMode("local"));
  for (const id of ["cameraHost", "cameraPort", "cameraPath"]) {
    on(id, "input", syncLanUrlPreview);
  }
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
        showToast(error.message);
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
          if (!window.confirm("删除这个摄像头配置？历史截图和告警不会删除。")) return;
          await deleteCamera(cameraId);
          showToast("摄像头已删除");
          await loadCameras();
        }
      } catch (error) {
        showToast(error.message);
      }
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
  bindEvents();
  if (pageName === "cameras") setCameraMode("lan");
  refreshAll();
  state.refreshTimer = setInterval(() => {
    if (pageName === "home") {
      if (state.selectedCameraId) {
        loadSnapshot(state.selectedCameraId).catch(() => null);
        loadEvaluation(state.selectedCameraId).catch(() => null);
      }
      loadEvents().catch(() => null);
    }
  }, 6000);
});
