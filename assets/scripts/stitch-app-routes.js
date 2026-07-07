(() => {
  const normalize = (value) => (value || "").replace(/\s+/g, "").trim();
  const page = () => window.location.pathname.split("/").pop() || "index.html";

  const mainTabs = [
    ["首页", "index.html"],
    ["守护", "monitor.html"],
    ["消息", "events.html"],
    ["陪伴", "companionship.html"],
    ["我的", "privacy.html"]
  ];

  const currentPageRoutes = {
    "welcome.html": [
      ["已有账号", "login.html"],
      ["点击登录", "login.html"],
      ["开启温情守护", "onboarding.html"]
    ],
    "onboarding.html": [
      ["跳过", "login.html"],
      ["立即开始", "login.html"]
    ],
    "login.html": [
      ["隐私政策", "privacy_data.html"],
      ["用户服务协议", "privacy_data.html"],
      ["中国移动认证服务协议", "privacy_data.html"],
      ["微信登录", "parent_profile.html"],
      ["Apple登录", "parent_profile.html"],
      ["一键登录", "parent_profile.html"]
    ],
    "parent_profile.html": [
      ["下一步", "family.html"]
    ],
    "family.html": [
      ["创建家庭", "device_binding.html"],
      ["创建家庭空间", "device_binding.html"],
      ["继续", "device_binding.html"]
    ],
    "device_binding.html": [
      ["扫描包装二维码", "camera_intro.html"],
      ["手动输入序列号", "camera_intro.html"],
      ["稍后设置", "camera_intro.html"],
      ["绑定", "camera_intro.html"]
    ],
    "camera_intro.html": [
      ["开始配置", "connect.html"]
    ],
    "connect.html": [
      ["下一步，生成连接二维码", "cameras.html"],
      ["生成连接二维码", "cameras.html"],
      ["下一步", "cameras.html"]
    ],
    "cameras.html": [
      ["添加新设备", "connect.html"],
      ["添加摄像头", "connect.html"],
      ["重新连接", "connect.html"],
      ["规则设置", "rules.html"],
      ["查看", "watch.html"]
    ],
    "index.html": [
      ["调整睡眠模式", "rules.html"],
      ["客厅环境", "monitor.html"],
      ["安防系统", "monitor.html"],
      ["通话", "companionship.html"],
      ["留言", "events.html"],
      ["查看", "watch.html"],
      ["行程", "events.html"]
    ],
    "monitor.html": [
      ["客厅", "watch.html"],
      ["卧室", "watch.html"],
      ["实时画面", "watch.html"],
      ["事件列表", "events.html"],
      ["规则设置", "rules.html"]
    ],
    "watch.html": [
      ["客厅缩略图", "watch.html"],
      ["餐厅缩略图", "watch.html"]
    ],
    "events.html": [
      ["今日降温", "event_detail.html"],
      ["紧急告警", "event_detail.html"],
      ["疑似", "event_detail.html"],
      ["提醒", "event_detail.html"]
    ],
    "event_detail.html": [
      ["误报", "events.html"],
      ["立即联系", "companionship.html"]
    ],
    "rules.html": [
      ["低", "rules.html"],
      ["中", "rules.html"],
      ["高", "rules.html"]
    ],
    "companionship.html": [
      ["语音通话", "companionship.html"],
      ["视频看看", "watch.html"],
      ["视频", "watch.html"]
    ],
    "privacy.html": [
      ["关怀推送", "care_schedule.html"],
      ["家庭成员", "family_members.html"],
      ["通知设置", "notifications.html"],
      ["规则设置", "rules.html"],
      ["隐私与数据", "privacy_data.html"],
      ["帮助与售后", "notifications.html"],
      ["退出登录", "login.html"]
    ],
    "family_members.html": [
      ["邀请新成员", "family_members.html"]
    ],
    "notifications.html": [
      ["通知", "notifications.html"]
    ],
    "privacy_data.html": [
      ["导出", "privacy_data.html"],
      ["删除", "privacy_data.html"]
    ]
  };

  const globalRoutes = [
    ["设备管理", "cameras.html"],
    ["添加设备", "camera_intro.html"],
    ["添加摄像头", "connect.html"],
    ["家庭成员", "family_members.html"],
    ["通知设置", "notifications.html"],
    ["关怀推送", "care_schedule.html"],
    ["隐私与数据", "privacy_data.html"],
    ["规则设置", "rules.html"],
    ["事件列表", "events.html"],
    ["实时画面", "watch.html"],
    ["查看实时画面", "watch.html"]
  ];

  const iconRoutes = {
    notifications: "notifications.html",
    arrow_back: "back",
    arrow_back_ios_new: "back",
    close: "back",
    settings: "rules.html",
    settings_suggest: "rules.html",
    add: "camera_intro.html",
    add_circle: "camera_intro.html",
    videocam: "watch.html",
    play_circle: "watch.html"
  };

  const routeFromPairs = (text, pairs) => {
    for (const [needle, route] of pairs) {
      if (text.includes(normalize(needle))) return route;
    }
    return null;
  };

  const routeFor = (item) => {
    if (!item || item.disabled || item.getAttribute("aria-disabled") === "true") return null;
    if (item.tagName === "BUTTON" && item.type === "submit" && item.form) return null;
    if (item.dataset.action && !item.dataset.route) return null;

    const explicit = item.dataset.route;
    if (explicit) return explicit;

    const href = item.getAttribute("href");
    if (href && href !== "#") return null;

    const aria = normalize(item.getAttribute("aria-label"));
    const text = normalize(item.innerText || item.textContent);
    const combined = `${aria}${text}`;

    for (const [label, route] of mainTabs) {
      if (combined === normalize(label) || combined.includes(normalize(label))) return route;
    }

    const currentRoutes = currentPageRoutes[page()] || [];
    const localRoute = routeFromPairs(combined, currentRoutes);
    if (localRoute) return localRoute;

    const globalRoute = routeFromPairs(combined, globalRoutes);
    if (globalRoute) return globalRoute;

    const icon = normalize(item.querySelector(".material-symbols-outlined")?.textContent);
    if (icon && iconRoutes[icon]) return iconRoutes[icon];
    return null;
  };

  const navigationTarget = (eventTarget) => {
    const direct = eventTarget.closest("[data-route], a, button");
    if (direct) return direct;
    return eventTarget.closest("article.cursor-pointer, div.cursor-pointer, section.cursor-pointer, .glass-card");
  };

  const go = (route) => {
    if (route === "back") {
      if (window.history.length > 1) window.history.back();
      else window.location.href = "index.html";
      return;
    }
    window.location.href = route;
  };

  document.addEventListener(
    "click",
    (event) => {
      const item = navigationTarget(event.target);
      if (!item || item.hasAttribute("onclick")) return;

      const route = routeFor(item);
      if (!route) return;

      event.preventDefault();
      event.stopImmediatePropagation();
      go(route);
    },
    true
  );

  document.addEventListener("submit", (event) => {
    if (page() !== "login.html") return;
    event.preventDefault();
    go("parent_profile.html");
  });

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("a, button, article.cursor-pointer, div.cursor-pointer, .glass-card").forEach((item) => {
      const route = routeFor(item);
      if (!route) return;
      if (item.tagName === "A" && (!item.getAttribute("href") || item.getAttribute("href") === "#")) {
        item.setAttribute("href", route === "back" ? "index.html" : route);
      }
      item.style.cursor = "pointer";
    });
  });
})();
