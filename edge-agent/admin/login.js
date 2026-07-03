const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(window.location.search);
const nextUrl = params.get("next") || "/admin/index.html";
let lastPassword = "";

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
    ? '<span class="material-symbols-outlined">progress_activity</span>处理中'
    : (label || button.dataset.originalText);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`);
  return data;
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
  } finally {
    setBusy(button, false);
  }
}

async function changePassword(event) {
  event.preventDefault();
  const newPassword = $("adminNewPassword").value;
  const confirmPassword = $("adminConfirmPassword").value;
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
        old_password: $("adminOldPassword").value,
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
