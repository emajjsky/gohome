(function () {
    const $ = (id) => document.getElementById(id);

    const state = {
        config: null,
        saving: false,
    };

    function setText(id, value) {
        const node = $(id);
        if (node) node.textContent = value;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function purposeLabel(value) {
        const labels = {
            care_text: "关怀文案",
            care_image: "关怀配图",
            content_summary: "内容摘要",
        };
        return labels[value] || value || "-";
    }

    function secretModeLabel(value) {
        const labels = {
            env: "环境变量",
            local: "本地密钥",
            secret_ref: "密钥引用",
            not_required: "无需密钥",
            unset: "未配置",
        };
        return labels[value] || value || "未配置";
    }

    function statusTone(provider) {
        if (!provider.enabled) return "warn";
        if (provider.configured) return "good";
        return "danger";
    }

    function statusLabel(provider) {
        if (!provider.enabled) return "未启用";
        if (provider.configured) return "可用";
        return "缺密钥";
    }

    function providerTitle(provider) {
        return `${purposeLabel(provider.purpose)} · ${provider.provider || "provider"} / ${provider.model || "model"}`;
    }

    function renderSummary(config) {
        const providers = Array.isArray(config.model_providers) ? config.model_providers : [];
        const enabled = providers.filter((item) => item.enabled).length;
        const configured = providers.filter((item) => item.configured).length;
        setText("opsServiceStatus", config.ok ? "在线" : "异常");
        setText("opsStoreKind", config.store || "-");
        setText("opsProviderSummary", `${configured}/${providers.length} 可用 · ${enabled} 已启用`);
        const policy = config.secret_policy || {};
        setText("opsSecretPolicy", `本地 ${policy.local || "-"}；云端 ${policy.cloud || "-"}；数据库 ${policy.database || "-"}`);
    }

    function providerTemplate(provider) {
        const secretHint = provider.requires_secret
            ? `密钥来源：${secretModeLabel(provider.secret_mode)}${provider.active_env_key ? ` · ${provider.active_env_key}` : ""}`
            : "密钥来源：无需密钥";
        const secretRef = provider.api_key_secret_ref || "";
        return `
            <article class="ops-provider" data-provider-id="${escapeHtml(provider.provider_id)}">
                <div class="ops-provider-top">
                    <div>
                        <p class="ops-provider-id">${escapeHtml(provider.provider_id)}</p>
                        <p class="ops-provider-title">${escapeHtml(providerTitle(provider))}</p>
                    </div>
                    <div class="ops-badges">
                        <span class="ops-badge ${statusTone(provider)}">${statusLabel(provider)}</span>
                        <span class="ops-badge">${escapeHtml(secretModeLabel(provider.secret_mode))}</span>
                    </div>
                </div>
                <form class="ops-form" data-provider-form="${escapeHtml(provider.provider_id)}">
                    <label class="ops-field">
                        <span>Provider</span>
                        <input class="ops-input" name="provider" value="${escapeHtml(provider.provider)}" autocomplete="off">
                    </label>
                    <label class="ops-field">
                        <span>Model</span>
                        <input class="ops-input" name="model" value="${escapeHtml(provider.model)}" autocomplete="off">
                    </label>
                    <label class="ops-field">
                        <span>用途</span>
                        <select class="ops-select" name="purpose">
                            ${["care_text", "care_image", "content_summary"].map((purpose) => `
                                <option value="${purpose}" ${purpose === provider.purpose ? "selected" : ""}>${purposeLabel(purpose)}</option>
                            `).join("")}
                        </select>
                    </label>
                    <label class="ops-field">
                        <span>启用</span>
                        <span class="ops-toggle-line">
                            <span>${provider.enabled ? "已启用" : "未启用"}</span>
                            <input name="enabled" type="checkbox" ${provider.enabled ? "checked" : ""}>
                        </span>
                    </label>
                    <label class="ops-field full">
                        <span>API Key</span>
                        <input class="ops-input" name="api_key" type="password" autocomplete="new-password" placeholder="${provider.api_key_set ? "留空不更换" : "填入后仅保存到服务器侧密钥存储"}">
                    </label>
                    <label class="ops-field full">
                        <span>Secret Ref</span>
                        <input class="ops-input" name="api_key_secret_ref" value="${escapeHtml(secretRef)}" autocomplete="off" placeholder="如 secret:gohome/care-text 或 local:model-provider:image-wan">
                    </label>
                    <label class="ops-field full">
                        <span>密钥操作</span>
                        <span class="ops-toggle-line">
                            <span>清除本地密钥</span>
                            <input name="clear_api_key" type="checkbox">
                        </span>
                    </label>
                    <div class="ops-form-actions">
                        <p class="ops-feedback" data-provider-feedback="${escapeHtml(provider.provider_id)}">${escapeHtml(secretHint)}</p>
                        <button class="ops-button primary" type="submit">
                            <span class="material-symbols-outlined">save</span>
                            保存
                        </button>
                    </div>
                </form>
            </article>
        `;
    }

    function renderProviders(config) {
        const list = $("opsProviderList");
        if (!list) return;
        const providers = Array.isArray(config.model_providers) ? config.model_providers : [];
        if (!providers.length) {
            list.innerHTML = `<div class="ops-empty">还没有 provider 配置</div>`;
            return;
        }
        list.innerHTML = providers.map(providerTemplate).join("");
    }

    function formPayload(form) {
        const data = new FormData(form);
        const payload = {
            provider: String(data.get("provider") || "").trim(),
            model: String(data.get("model") || "").trim(),
            purpose: String(data.get("purpose") || "care_text").trim(),
            enabled: data.get("enabled") === "on",
            api_key_secret_ref: String(data.get("api_key_secret_ref") || "").trim(),
        };
        const apiKey = String(data.get("api_key") || "").trim();
        if (apiKey) payload.api_key = apiKey;
        if (data.get("clear_api_key") === "on") {
            payload.clear_api_key = true;
            payload.api_key_secret_ref = "";
        }
        return payload;
    }

    function setFeedback(providerId, value) {
        const node = document.querySelector(`[data-provider-feedback="${CSS.escape(providerId)}"]`);
        if (node) node.textContent = value;
    }

    async function saveProvider(form) {
        if (state.saving || !window.GoHomeEdge) return;
        const providerId = form.getAttribute("data-provider-form");
        if (!providerId) return;
        state.saving = true;
        setFeedback(providerId, "正在保存");
        try {
            await GoHomeEdge.v1UpdateModelProvider(providerId, formPayload(form));
            setFeedback(providerId, "已保存");
            await loadConfig();
        } catch (error) {
            setFeedback(providerId, error.message || "保存失败");
        } finally {
            state.saving = false;
        }
    }

    async function loadConfig() {
        if (!window.GoHomeEdge) return;
        const config = await GoHomeEdge.v1OpsServiceConfig();
        state.config = config;
        renderSummary(config);
        renderProviders(config);
    }

    async function bootstrap() {
        if (!window.GoHomeEdge) return;
        try {
            GoHomeEdge.bootstrapLaunchState?.();
            await GoHomeEdge.connect();
            await loadConfig();
        } catch (error) {
            setText("opsServiceStatus", "未连接");
            setText("opsProviderSummary", "-");
            setText("opsSecretPolicy", error.message || "后台服务不可用");
            const list = $("opsProviderList");
            if (list) list.innerHTML = `<div class="ops-empty">${escapeHtml(error.message || "后台服务不可用")}</div>`;
        }
    }

    document.addEventListener("submit", (event) => {
        const form = event.target.closest("[data-provider-form]");
        if (!form) return;
        event.preventDefault();
        saveProvider(form);
    });

    $("opsRefreshBtn")?.addEventListener("click", () => {
        loadConfig().catch((error) => {
            setText("opsServiceStatus", "刷新失败");
            setText("opsSecretPolicy", error.message || "刷新失败");
        });
    });

    document.addEventListener("DOMContentLoaded", bootstrap);
})();
