const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(window.location.search);
const nextUrl = params.get("next") || "/admin/index.html";
let lastPassword = "";
let loginLockTimer = null;

function setMessage(message, tone = "") {
  const node = $("adminLoginMessage");
  if (!node) return;
  node.textContent = message || "";
  node.dataset.tone = tone;
}

function setBusy(button, busy, label) {
  if (!button) return;
  button.disabled = busy;
  button.dataset.originalText ??= button.innerHTML;
  button.innerHTML = busy
    ? '<span class="material-symbols-outlined" data-icon="…" aria-hidden="true"></span>处理中'
    : (label || button.dataset.originalText);
}

function formatApiError(data, status) {
  const detail = data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && !Array.isArray(detail) && typeof detail.message === "string") {
    return detail.message;
  }
  if (Array.isArray(detail)) {
    const validation = detail[0] || {};
    const field = Array.isArray(validation.loc) ? validation.loc.at(-1) : "";
    if (field === "new_password" && validation.type === "string_too_short") {
      return `新密码至少需要 ${validation.ctx?.min_length || 10} 位。`;
    }
    if (field === "new_password" && validation.type === "string_too_long") {
      return `新密码最多允许 ${validation.ctx?.max_length || 128} 位。`;
    }
    if (field === "old_password") return "请输入当前使用的一次性密码。";
    if (typeof validation.msg === "string" && validation.msg.trim()) return validation.msg;
  }
  return `请求失败（HTTP ${status}）。`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (_error) {
      data = null;
    }
  }
  if (!response.ok) {
    const error = new Error(formatApiError(data, response.status));
    error.retryAfter = Number(response.headers.get("Retry-After") || 0);
    throw error;
  }
  return data;
}

function lockLoginButton(seconds) {
  const button = $("adminLoginButton");
  let remaining = Math.max(1, Math.ceil(Number(seconds) || 0));
  window.clearInterval(loginLockTimer);
  button.disabled = true;
  const render = () => {
    button.innerHTML = `<span class="material-symbols-outlined" data-icon="◷" aria-hidden="true"></span>${remaining} 秒后重试`;
    remaining -= 1;
    if (remaining < 0) {
      window.clearInterval(loginLockTimer);
      loginLockTimer = null;
      button.disabled = false;
      button.innerHTML = button.dataset.originalText;
    }
  };
  render();
  loginLockTimer = window.setInterval(render, 1000);
}

function showPasswordChange() {
  $("adminLoginForm").hidden = true;
  $("adminLoginForm").classList.add("hidden");
  $("adminPasswordForm").hidden = false;
  $("adminPasswordForm").classList.remove("hidden");
  if (lastPassword) $("adminOldPassword").value = lastPassword;
  $("adminNewPassword").focus();
  setMessage("请先修改初始密码。");
}

function showLogin() {
  $("adminPasswordForm").hidden = true;
  $("adminPasswordForm").classList.add("hidden");
  $("adminLoginForm").hidden = false;
  $("adminLoginForm").classList.remove("hidden");
}

async function loadStatus() {
  try {
    const status = await api("/api/admin/auth/status");
    $("loginDeviceName").textContent = status.device_name || "回家盒子";
    $("loginDeviceMeta").textContent = `${status.device_id || "-"} · ${status.mdns_name || "gohome.local"}`;
    $("adminUsername").value = status.admin_username || "admin";
    if (status.authenticated && status.must_change_password) {
      showPasswordChange();
      return;
    }
    if (status.authenticated) {
      window.location.replace(nextUrl);
    }
  } catch (error) {
    setMessage(error.message || "盒子状态读取失败", "bad");
  }
}

async function login(event) {
  event.preventDefault();
  const button = $("adminLoginButton");
  setBusy(button, true);
  setMessage("");
  const payload = {
    username: $("adminUsername").value.trim(),
    password: $("adminPassword").value,
  };
  lastPassword = payload.password;
  try {
    const result = await api("/api/admin/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (result.must_change_password) {
      showPasswordChange();
      return;
    }
    window.location.replace(nextUrl);
  } catch (error) {
    setMessage(error.message || "登录失败", "bad");
    if (error.retryAfter > 0) lockLoginButton(error.retryAfter);
  } finally {
    if (!loginLockTimer) setBusy(button, false);
  }
}

async function changePassword(event) {
  event.preventDefault();
  const oldPassword = $("adminOldPassword").value;
  const newPassword = $("adminNewPassword").value;
  const confirmPassword = $("adminConfirmPassword").value;
  if (!oldPassword) {
    setMessage("请输入当前使用的一次性密码。", "bad");
    $("adminOldPassword").focus();
    return;
  }
  if (newPassword.length < 10) {
    setMessage("新密码至少需要 10 位。", "bad");
    $("adminNewPassword").focus();
    return;
  }
  if (newPassword.length > 128) {
    setMessage("新密码最多允许 128 位。", "bad");
    $("adminNewPassword").focus();
    return;
  }
  if (newPassword !== confirmPassword) {
    setMessage("两次输入的新密码不一致。", "bad");
    return;
  }
  const button = $("adminPasswordButton");
  setBusy(button, true);
  try {
    await api("/api/admin/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        old_password: oldPassword,
        new_password: newPassword,
      }),
    });
    lastPassword = "";
    $("adminPassword").value = "";
    showLogin();
    setMessage("密码已修改，请用新密码重新登录。", "good");
  } catch (error) {
    setMessage(error.message || "密码修改失败", "bad");
  } finally {
    setBusy(button, false);
  }
}

async function logout() {
  await api("/api/admin/auth/logout", { method: "POST" }).catch(() => null);
  lastPassword = "";
  showLogin();
  setMessage("已退出。");
}

document.addEventListener("DOMContentLoaded", () => {
  $("adminLoginForm")?.addEventListener("submit", login);
  $("adminPasswordForm")?.addEventListener("submit", changePassword);
  $("adminLogoutButton")?.addEventListener("click", logout);
  loadStatus();
});
