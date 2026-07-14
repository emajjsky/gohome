#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function createStorage(initial = {}) {
    const values = new Map(Object.entries(initial));
    return {
        get length() { return values.size; },
        key(index) { return [...values.keys()][index] ?? null; },
        getItem(key) { return values.has(String(key)) ? values.get(String(key)) : null; },
        setItem(key, value) { values.set(String(key), String(value)); },
        removeItem(key) { values.delete(String(key)); },
        keys() { return [...values.keys()]; },
    };
}

function response(payload, status = 200) {
    return {
        ok: status >= 200 && status < 300,
        status,
        text: async () => JSON.stringify(payload),
        json: async () => payload,
    };
}

function createHarness(options = {}) {
    const localStorage = options.localStorage || createStorage({ "gohome.authToken": "token-account-1234567890" });
    const sessionStorage = options.sessionStorage || createStorage();
    const events = [];
    const fetches = [];
    const listeners = new Map();
    const location = {
        protocol: "https:",
        pathname: "/index.html",
        search: "",
        hash: "",
        href: "https://example.test/index.html",
    };
    const window = {
        location,
        history: { replaceState() {} },
        innerWidth: 390,
        matchMedia: () => ({ matches: true }),
        dispatchEvent(event) {
            events.push(event);
            for (const listener of listeners.get(event.type) || []) listener(event);
            return true;
        },
        addEventListener(type, listener) {
            const current = listeners.get(type) || [];
            current.push(listener);
            listeners.set(type, current);
        },
    };
    const context = {
        window,
        localStorage,
        sessionStorage,
        document: { cookie: "" },
        navigator: {},
        URL,
        URLSearchParams,
        AbortController,
        Blob,
        FormData,
        TextEncoder,
        setTimeout,
        clearTimeout,
        CustomEvent: class CustomEvent {
            constructor(type, options = {}) {
                this.type = type;
                this.detail = options.detail;
            }
        },
        fetch: (...args) => {
            fetches.push(args);
            return context.nextFetch(...args);
        },
        nextFetch: async () => response({ ok: true }),
    };
    window.window = window;
    const source = fs.readFileSync(path.resolve(__dirname, "../assets/scripts/edge-client.js"), "utf8");
    vm.runInNewContext(source, context, { filename: "edge-client.js" });
    return { context, window, localStorage, sessionStorage, events, fetches };
}

function apiCacheKeys(storage) {
    return storage.keys().filter((key) => key.startsWith("gohome.apiCache."));
}

function assertMainPagesHaveNoBlockingLoadingCopy() {
    const root = path.resolve(__dirname, "..");
    const forbidden = /正在读取|正在同步|同步中|读取中|正在生成|正在打开|马上出现|正在连接画面|识别中/;
    for (const file of ["index.html", "monitor.html", "events.html", "companionship.html", "privacy.html"]) {
        const html = fs.readFileSync(path.join(root, file), "utf8");
        const main = html.match(/<main\b[\s\S]*?<\/main>/i)?.[0] || "";
        assert.ok(!forbidden.test(main), `${file} contains blocking loading copy in main content`);
    }
    const store = fs.readFileSync(path.join(root, "assets/scripts/app-state-store.js"), "utf8");
    assert.ok(!store.includes("body::after"), "page state store must not render a full-page spinner");
    assert.ok(!store.includes("gohome-state-spin"), "page state store must not animate a blocking loader");
}

function assertAppShellNavigationCache() {
    const root = path.resolve(__dirname, "..");
    const store = fs.readFileSync(path.join(root, "assets/scripts/app-state-store.js"), "utf8");
    const worker = fs.readFileSync(path.join(root, "service-worker.js"), "utf8");
    assert.match(store, /serviceWorker\.register\(APP_SHELL_SERVICE_WORKER/);
    for (const file of ["index.html", "monitor.html", "events.html", "companionship.html", "privacy.html"]) {
        const html = fs.readFileSync(path.join(root, file), "utf8");
        assert.match(html, /20260715-appstore-11/, `${file} must load the app shell registrar`);
        assert.ok(worker.includes(`"/${file}"`), `${file} must be pre-cached for tab navigation`);
    }
    for (const file of ["watch.html", "event_detail.html", "care_schedule.html", "cameras.html", "rules.html", "notifications.html"]) {
        assert.ok(worker.includes(`"/${file}"`), `${file} must be pre-cached for the primary product flow`);
    }
    assert.match(worker, /request\.mode !== "navigate"/);
    assert.ok(!worker.includes("/api/"), "service worker must never cache authenticated API responses");
    assert.match(worker, /event\.waitUntil\(network\.catch/);
}

async function flush() {
    await new Promise((resolve) => setImmediate(resolve));
}

async function main() {
    assertMainPagesHaveNoBlockingLoadingCopy();
    assertAppShellNavigationCache();
    const harness = createHarness();
    const { context, window, localStorage, sessionStorage, events, fetches } = harness;
    let payload = { revision: 1 };
    context.nextFetch = async () => response(payload);

    const first = await window.GoHomeEdge.request("/api/test", { cacheTtlMs: 1000 });
    assert.deepEqual(first, { revision: 1 });
    assert.equal(fetches.length, 1, "first request must reach the network");

    const cacheKey = apiCacheKeys(localStorage)[0];
    const expired = JSON.parse(localStorage.getItem(cacheKey));
    expired.expires_at = Date.now() - 1;
    expired.stale_until = Date.now() + 60_000;
    localStorage.setItem(cacheKey, JSON.stringify(expired));

    let resolveRevalidation;
    context.nextFetch = () => new Promise((resolve) => { resolveRevalidation = resolve; });
    const staleOne = await window.GoHomeEdge.request("/api/test", { cacheTtlMs: 1000 });
    const staleTwo = await window.GoHomeEdge.request("/api/test", { cacheTtlMs: 1000 });
    assert.deepEqual(staleOne, { revision: 1 });
    assert.deepEqual(staleTwo, { revision: 1 });
    assert.equal(fetches.length, 2, "stale requests must share one background revalidation");

    resolveRevalidation(response({ revision: 2 }));
    await flush();
    assert.ok(events.some((event) => event.type === "gohome:data-updated" && event.detail.path === "/api/test"));
    const refreshed = await window.GoHomeEdge.request("/api/test", { cacheTtlMs: 1000 });
    assert.deepEqual(refreshed, { revision: 2 });
    assert.equal(fetches.length, 2, "fresh revalidated data must be returned without another fetch");

    context.nextFetch = async () => response({ ticket: "readonly" });
    await window.GoHomeEdge.request("/api/playback", { method: "POST", invalidateCache: false });
    assert.ok(apiCacheKeys(localStorage).length > 0, "read-only technical POST must preserve cache");

    context.nextFetch = async () => response({
        ticket: "persisted-playback-ticket",
        expires_at: new Date(Date.now() + 120_000).toISOString(),
    });
    const playbackPayload = { resource_type: "stream", camera_id: 9, expires_in_seconds: 120 };
    await window.GoHomeEdge.createPlaybackSession(playbackPayload);
    const playbackFetchCount = fetches.length;
    assert.ok(sessionStorage.keys().some((key) => key.startsWith("gohome.playbackSessions.")), "playback ticket must persist for the next page");

    const nextPage = createHarness({ localStorage, sessionStorage });
    nextPage.context.nextFetch = async () => {
        throw new Error("persisted playback ticket should avoid a second request");
    };
    const reused = await nextPage.window.GoHomeEdge.createPlaybackSession(playbackPayload);
    assert.equal(reused.ticket, "persisted-playback-ticket", "next page must reuse the unexpired playback ticket");
    assert.equal(fetches.length, playbackFetchCount, "reusing a playback ticket must not add a request on the first page");

    context.nextFetch = async () => response({ saved: true });
    await window.GoHomeEdge.request("/api/settings", { method: "PUT", body: "{}" });
    assert.equal(apiCacheKeys(localStorage).length, 0, "mutation must invalidate persisted API cache");
    assert.ok(events.some((event) => event.type === "gohome:data-updated" && event.detail.reason === "mutation"));

    console.log("frontend state cache verification passed");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
