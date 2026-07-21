"use strict";

function etagFor(revision) {
    return `"${String(revision || "")}"`;
}

function notModified(requestHeaders, revision) {
    return String(requestHeaders?.["if-none-match"] || "") === etagFor(revision);
}

class NativeApiRouter {
    constructor(viewService) {
        this.viewService = viewService;
    }

    async dispatch({ method, url, userId, headers = {} }) {
        if (method === "GET" && url.pathname === "/api/v2/app/bootstrap") {
            const body = await this.viewService.bootstrapForUser(userId);
            const etag = etagFor(body.revision);
            if (notModified(headers, body.revision)) return { status: 304, headers: { ETag: etag } };
            return { status: 200, body, headers: { ETag: etag } };
        }

        if (method === "GET" && url.pathname === "/api/v2/home") {
            const body = await this.viewService.homeForFamily(userId, url.searchParams.get("family_id"));
            const etag = etagFor(body.revision);
            if (notModified(headers, body.revision)) return { status: 304, headers: { ETag: etag } };
            return { status: 200, body, headers: { ETag: etag } };
        }

        return null;
    }
}

module.exports = { NativeApiRouter, etagFor };
