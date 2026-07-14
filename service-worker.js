"use strict";

const SHELL_CACHE = "gohome-app-shell-20260715-3";
const SHELL_DOCUMENTS = new Set([
    "/index.html",
    "/monitor.html",
    "/events.html",
    "/companionship.html",
    "/privacy.html",
    "/watch.html",
    "/event_detail.html",
    "/parent_profile.html",
    "/family_members.html",
    "/care_schedule.html",
    "/cameras.html",
    "/rules.html",
    "/presence_settings.html",
    "/notifications.html",
    "/privacy_data.html",
    "/device_binding.html",
    "/camera_intro.html",
    "/connect.html",
]);

function documentCacheKey(request) {
    const url = new URL(request.url);
    const pathname = url.pathname === "/" ? "/index.html" : url.pathname;
    return new Request(pathname, { method: "GET" });
}

async function updateDocument(request, cache, cacheKey) {
    const response = await fetch(request);
    if (response.ok && response.type !== "opaque") {
        await cache.put(cacheKey, response.clone());
    }
    return response;
}

self.addEventListener("install", (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(SHELL_CACHE);
        await cache.addAll([...SHELL_DOCUMENTS]);
        await self.skipWaiting();
    })());
});

self.addEventListener("activate", (event) => {
    event.waitUntil((async () => {
        const names = await caches.keys();
        await Promise.all(names
            .filter((name) => name.startsWith("gohome-app-shell-") && name !== SHELL_CACHE)
            .map((name) => caches.delete(name)));
        await self.clients.claim();
    })());
});

self.addEventListener("fetch", (event) => {
    const request = event.request;
    if (request.method !== "GET" || request.mode !== "navigate") return;

    const url = new URL(request.url);
    const pathname = url.pathname === "/" ? "/index.html" : url.pathname;
    if (url.origin !== self.location.origin || !SHELL_DOCUMENTS.has(pathname)) return;

    event.respondWith((async () => {
        const cache = await caches.open(SHELL_CACHE);
        const cacheKey = documentCacheKey(request);
        const cached = await cache.match(cacheKey);
        const network = updateDocument(request, cache, cacheKey);
        if (cached) {
            event.waitUntil(network.catch(() => null));
            return cached;
        }
        return network;
    })());
});
