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

function createHarness() {
    const localStorage = createStorage({ "gohome.authToken": "token-account-1234567890" });
    const sessionStorage = createStorage();
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
    return { context, window, localStorage, events, fetches };
}

function apiCacheKeys(storage) {
    return storage.keys().filter((key) => key.startsWith("gohome.apiCache."));
}

async function flush() {
    await new Promise((resolve) => setImmediate(resolve));
}

async function main() {
    const harness = createHarness();
    const { context, window, localStorage, events, fetches } = harness;
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
