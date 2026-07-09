#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const DEFAULT_BASE_URL = "http://127.0.0.1:8788";
const DEFAULT_TOKEN = "gohome-local-app-token";

const baseUrl = String(process.env.GOHOME_APP_BASE_URL || process.argv[2] || DEFAULT_BASE_URL).replace(/\/$/, "");
const appToken = process.env.GOHOME_APP_TOKEN || DEFAULT_TOKEN;
const opsToken = String(process.env.GOHOME_OPS_TOKEN || "").trim();

const results = [];

function record(level, name, detail = "") {
    results.push({ level, name, detail });
}

function pass(name, detail = "") {
    record("pass", name, detail);
}

function warn(name, detail = "") {
    record("warn", name, detail);
}

function fail(name, detail = "") {
    record("fail", name, detail);
}

async function request(pathname, options = {}) {
    const { token = appToken, ...fetchOptions } = options;
    const headers = {
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(fetchOptions.body && !(fetchOptions.headers || {})["Content-Type"] ? { "Content-Type": "application/json" } : {}),
        ...(fetchOptions.headers || {}),
    };
    const response = await fetch(`${baseUrl}${pathname}`, {
        ...fetchOptions,
        headers: {
            ...headers,
        },
    });
    const text = await response.text();
    let payload = null;
    try {
        payload = text ? JSON.parse(text) : null;
    } catch (_error) {
        payload = text;
    }
    return { response, payload, text };
}

async function requestJson(path) {
    const { response, payload, text } = await request(path);
    if (!response.ok) {
        throw new Error(`${path} -> ${response.status} ${text}`);
    }
    return payload;
}

async function requestJsonAs(token, pathname) {
    const { response, payload, text } = await request(pathname, { token });
    if (!response.ok) {
        throw new Error(`${pathname} -> ${response.status} ${text}`);
    }
    return payload;
}

async function postJson(pathname, payload, token = "") {
    const { response, payload: responsePayload, text } = await request(pathname, {
        method: "POST",
        token,
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const error = new Error(`${pathname} -> ${response.status} ${text}`);
        error.status = response.status;
        error.payload = responsePayload;
        throw error;
    }
    return responsePayload;
}

async function putJson(pathname, payload, token = "") {
    const { response, payload: responsePayload, text } = await request(pathname, {
        method: "PUT",
        token,
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        throw new Error(`${pathname} -> ${response.status} ${text}`);
    }
    return responsePayload;
}

async function checkPage(path, expectedText) {
    const response = await fetch(`${baseUrl}/${path}`);
    const text = await response.text();
    if (!response.ok) {
        fail(`page ${path}`, `HTTP ${response.status}`);
        return;
    }
    if (expectedText && !text.includes(expectedText)) {
        warn(`page ${path}`, `missing text: ${expectedText}`);
        return;
    }
    pass(`page ${path}`);
}

function localDbPath() {
    return process.env.GOHOME_APP_DB_PATH || path.join(process.cwd(), "data", "app-server", "db.json");
}

function localPasswordFor(email) {
    try {
        const db = JSON.parse(fs.readFileSync(localDbPath(), "utf8"));
        const user = Array.isArray(db.users)
            ? db.users.find((item) => String(item.email || "").toLowerCase() === String(email || "").toLowerCase())
            : null;
        return user?.password ? String(user.password) : "";
    } catch (_error) {
        return "";
    }
}

async function restoreOriginalUser(originalUser) {
    if (!originalUser?.email) return;
    const email = String(originalUser.email || "").toLowerCase();
    const password = /@phone\.gohome\.local$/i.test(email) ? "000000" : localPasswordFor(email);
    if (!password) {
        warn("active user restore", `cannot restore ${email}, password not available locally`);
        return;
    }
    try {
        await postJson("/api/auth/login", { email, password }, "");
        pass("active user restore", originalUser.display_name || email);
    } catch (error) {
        warn("active user restore", error.message);
    }
}

async function cleanupVerifyData() {
    const endpoint = new URL(`${baseUrl}/api/v1/internal/verify-data/cleanup`);
    if (opsToken) endpoint.searchParams.set("ops_token", opsToken);
    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({ dry_run: false }),
        });
        const text = await response.text();
        const payload = text ? JSON.parse(text) : {};
        if (!response.ok) {
            warn("verify data cleanup", payload?.detail || `HTTP ${response.status}`);
            return;
        }
        const deleted = payload.deleted || {};
        const total = Object.values(deleted).reduce((sum, value) => sum + Number(value || 0), 0);
        pass("verify data cleanup", `${total} record(s) removed`);
    } catch (error) {
        warn("verify data cleanup", error.message || "cleanup failed");
    }
}

async function verifyNewUserIsolation(originalUser) {
    const stamp = Date.now().toString(36);
    const email = `verify-${stamp}@gohome.local`;
    const password = "123456";
    let token = "";
    try {
        const registered = await postJson("/api/auth/register", {
            email,
            password,
            display_name: "流程自检",
        }, "");
        token = registered?.token || "";
        const me = token ? await requestJsonAs(token, "/api/users/me") : null;
        if (me?.email === email) pass("new user register", email);
        else fail("new user register", "registered token cannot read current user");

        const initialFamilies = token ? await requestJsonAs(token, "/api/families/mine") : [];
        if (Array.isArray(initialFamilies) && initialFamilies.length === 0) {
            pass("new user family isolation", "no inherited family");
        } else {
            fail("new user family isolation", `${Array.isArray(initialFamilies) ? initialFamilies.length : "invalid"} inherited family item(s)`);
        }

        const initialCameras = token ? await requestJsonAs(token, "/api/app/cameras") : [];
        if (Array.isArray(initialCameras) && initialCameras.length === 0) {
            pass("new user camera isolation", "no inherited cameras");
        } else {
            fail("new user camera isolation", `${Array.isArray(initialCameras) ? initialCameras.length : "invalid"} inherited camera(s)`);
        }

        const initialDevice = token ? await requestJsonAs(token, "/api/app/device") : null;
        if (!initialDevice?.device_id) pass("new user device isolation", "no inherited box binding");
        else fail("new user device isolation", `inherited ${initialDevice.device_id}`);

        const family = await postJson("/api/families", { name: `流程自检-${stamp}` }, token);
        if (family?.id) pass("new user create family", `${family.name || family.id}`);
        else fail("new user create family", "missing family id");

        if (family?.id) {
            const profile = await putJson(`/api/v1/families/${encodeURIComponent(family.id)}/elders/elder_primary/profile`, {
                display_name: "测试长辈",
                relationship: "母亲",
                city: "上海",
                district: "浦东新区",
                phone: "13900000000",
                mobile_phone: "13900000000",
                home_phone: "021-00000000",
            }, token);
            if (profile?.display_name === "测试长辈" && profile?.home_phone) {
                pass("new user elder profile", `${profile.display_name} ${profile.home_phone}`);
            } else {
                fail("new user elder profile", "profile did not persist expected fields");
            }

            const familyCameras = await requestJsonAs(token, "/api/app/cameras");
            if (Array.isArray(familyCameras) && familyCameras.length === 0) {
                pass("new family camera state", "still empty before binding/config");
            } else {
                fail("new family camera state", `${Array.isArray(familyCameras) ? familyCameras.length : "invalid"} camera(s) before binding`);
            }
        }
    } catch (error) {
        fail("new user flow", error.message);
    } finally {
        await restoreOriginalUser(originalUser);
        await cleanupVerifyData();
    }
}

async function main() {
    let health = null;
    try {
        health = await requestJson("/health");
        if (health.ok) pass("service health", `${baseUrl} store=${health.store || "unknown"}`);
        else fail("service health", "health.ok is false");
    } catch (error) {
        fail("service health", error.message);
        printAndExit();
        return;
    }

    const user = await requestJson("/api/users/me");
    if (user?.id) pass("app auth", `${user.display_name || user.email || user.id}`);
    else fail("app auth", "missing current user");

    const families = await requestJson("/api/families/mine");
    const family = Array.isArray(families) ? families[0] : null;
    if (family?.id) pass("family", `${family.name || family.id}`);
    else fail("family", "no family returned");

    if (family?.id) {
        const profile = await requestJson(`/api/v1/families/${family.id}/elders/elder_primary/profile`);
        if (profile?.display_name) pass("elder profile", `${profile.display_name} ${profile.city || ""}`.trim());
        else warn("elder profile", "display name is empty");
        if (profile?.mobile_phone || profile?.phone || profile?.home_phone) pass("elder contact", "phone configured");
        else warn("elder contact", "phone/home phone is empty, call action cannot dial directly");

        const carePrefs = await requestJson(`/api/v1/families/${family.id}/care-preferences`);
        const schedule = carePrefs?.metadata?.care_card_schedule || {};
        if (schedule.enabled) pass("care schedule", `${schedule.delivery_time || "time not set"}`);
        else warn("care schedule", "daily care card schedule is disabled");

        const weather = await requestJson(`/api/v1/families/${family.id}/weather-signals`);
        if (weather?.available) {
            const temp = weather.temperature_c === null || weather.temperature_c === undefined ? "" : ` ${weather.temperature_c}C`;
            pass("weather provider", `${weather.provider || "weather"} ${weather.city || ""} ${weather.condition || ""}${temp}`.trim());
        } else {
            warn("weather provider", `${weather?.provider || "unknown"} ${weather?.reason || "unavailable"}`);
        }

        const content = await requestJson(`/api/v1/families/${family.id}/content-recommendations`);
        if (content?.available && Array.isArray(content.recommendations) && content.recommendations.length) {
            pass("content search", `${content.provider || "search"} ${content.recommendations.length} candidate(s)`);
        } else {
            warn("content search", `${content?.provider || "unknown"} ${content?.reason || "unavailable"}`);
        }

        const todayCare = await requestJson(`/api/v1/app/care-cards/today?family_id=${family.id}`);
        if (todayCare?.card_id) pass("today care card", `${todayCare.title || todayCare.card_id}`);
        else fail("today care card", "missing card");
        if (todayCare?.image_url) {
            const mediaPath = `/api/v1/video/media/snapshots/${encodeURIComponent(todayCare.image_url)}`;
            const media = await request(mediaPath, { headers: { Accept: "image/png,image/jpeg,image/*,*/*" } });
            const contentType = media.response.headers.get("content-type") || "";
            if (media.response.ok && contentType.startsWith("image/")) {
                pass("care card image", `${todayCare.image_mode || "image"} ${contentType}`);
            } else {
                fail("care card image", `${media.response.status} ${contentType || media.text.slice(0, 80)}`);
            }
        } else {
            warn("care card image", `image_mode=${todayCare?.image_mode || "none"}`);
        }
    }

    const device = await requestJson("/api/app/device");
    if (device?.device_id) pass("device visible", `${device.device_id}`);
    else fail("device visible", "missing app device");
    if (device?.worker_running) pass("edge worker", "reported running");
    else warn("edge worker", "worker_running is false or not reported");

    const bindings = family?.id ? await requestJson(`/api/device-bindings?family_id=${family.id}`) : [];
    if (Array.isArray(bindings) && bindings.length) pass("device binding", `${bindings.length} binding(s)`);
    else warn("device binding", "no formal app-side binding record, current demo relies on device sync state");

    const syncState = await requestJson("/api/v1/devices/current/sync-state");
    if (syncState?.config_version) pass("device sync state", syncState.config_version);
    else fail("device sync state", "missing config version");
    if (syncState?.rules_version && syncState.applied_rule_version && syncState.rules_version === syncState.applied_rule_version) {
        pass("rules applied", syncState.rules_version);
    } else if (syncState?.rules_version) {
        warn("rules applied", `desired=${syncState.rules_version}, applied=${syncState.applied_rule_version || "not reported"}`);
    } else {
        fail("rules applied", "missing rules version");
    }

    const cameras = await requestJson("/api/app/cameras");
    const enabledCameras = Array.isArray(cameras) ? cameras.filter((camera) => camera.enabled !== false) : [];
    const onlineCameras = enabledCameras.filter((camera) => String(camera.status || "").toLowerCase() === "online");
    if (enabledCameras.length) pass("cameras configured", `${enabledCameras.length} enabled`);
    else fail("cameras configured", "no enabled cameras");
    if (onlineCameras.length === enabledCameras.length && enabledCameras.length) {
        pass("camera online", `${onlineCameras.length}/${enabledCameras.length}`);
    } else {
        fail("camera online", `${onlineCameras.length}/${enabledCameras.length}`);
    }
    for (const camera of onlineCameras) {
        const evaluation = await requestJson(`/api/app/cameras/${encodeURIComponent(camera.id)}/evaluation/latest`);
        const cameraState = String(evaluation?.state?.camera_state || "").toLowerCase();
        const candidateCount = Array.isArray(evaluation?.candidates) ? evaluation.candidates.length : 0;
        if (cameraState === "offline") {
            fail("camera evaluation", `${camera.name || camera.id} online but latest evaluation is offline`);
        } else {
            pass("camera evaluation", `${camera.name || camera.id} ${cameraState || "reported"} ${candidateCount} candidate(s)`);
        }
    }

    const summary = await requestJson("/api/app/summary/today");
    if (Number(summary.open_events || 0) === 0 && Number(summary.critical_events || 0) === 0) {
        pass("user event summary", "no open critical events");
    } else {
        fail("user event summary", `open=${summary.open_events}, critical=${summary.critical_events}`);
    }

    const events = await requestJson("/api/app/events?limit=10&acknowledged=false");
    if (Array.isArray(events) && events.length === Number(summary.open_events || 0)) {
        pass("event list", `${events.length} open event(s)`);
    } else {
        fail("event list", `list=${Array.isArray(events) ? events.length : "invalid"}, summary=${summary.open_events}`);
    }

    const providers = await requestJson("/api/v1/model-providers");
    const multimodal = providers.find((item) => item.provider_id === "multimodal-language");
    const image = providers.find((item) => item.provider_id === "care-card-image");
    if (multimodal?.configured && multimodal?.api_key_set) pass("multimodal model", multimodal.model || "configured");
    else warn("multimodal model", "not fully configured");
    if (image?.configured && image?.api_key_set) pass("image model", image.model || "configured");
    else warn("image model", "not fully configured");

    await checkPage("index.html?app=1", "今日关怀");
    await checkPage("monitor.html?app=1", "摄像头");
    await checkPage("events.html?app=1", "事件");
    await checkPage("companionship.html?app=1", "今日关怀");
    await checkPage("privacy.html?app=1", "家庭设置");

    await verifyNewUserIsolation(user);

    printAndExit();
}

function printAndExit() {
    const counts = results.reduce((acc, item) => {
        acc[item.level] = (acc[item.level] || 0) + 1;
        return acc;
    }, {});
    for (const item of results) {
        const marker = item.level === "pass" ? "OK" : (item.level === "warn" ? "WARN" : "FAIL");
        console.log(`${marker} ${item.name}${item.detail ? ` - ${item.detail}` : ""}`);
    }
    console.log(`\nSummary: ${counts.pass || 0} passed, ${counts.warn || 0} warnings, ${counts.fail || 0} failed`);
    process.exit(counts.fail ? 1 : 0);
}

main().catch((error) => {
    fail("unexpected error", error.stack || error.message);
    printAndExit();
});
