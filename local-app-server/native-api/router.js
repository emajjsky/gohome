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

    async dispatch({ method, url, userId, headers = {}, body = {} }) {
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

        if (method === "GET" && url.pathname === "/api/v2/messages") {
            const responseBody = await this.viewService.messagesForFamily(userId, url.searchParams.get("family_id"), {
                status: url.searchParams.get("status") || "",
                limit: url.searchParams.get("limit") || undefined,
            });
            const etag = etagFor(responseBody.revision);
            if (notModified(headers, responseBody.revision)) return { status: 304, headers: { ETag: etag } };
            return { status: 200, body: responseBody, headers: { ETag: etag } };
        }

        const messageMatch = url.pathname.match(/^\/api\/v2\/messages\/([^/]+)$/);
        if (method === "GET" && messageMatch) {
            const responseBody = await this.viewService.messageForFamily(
                userId,
                url.searchParams.get("family_id"),
                decodeURIComponent(messageMatch[1]),
            );
            const etag = etagFor(responseBody.revision);
            if (notModified(headers, responseBody.revision)) return { status: 304, headers: { ETag: etag } };
            return { status: 200, body: responseBody, headers: { ETag: etag } };
        }

        const actionMatch = url.pathname.match(/^\/api\/v2\/messages\/([^/]+)\/actions$/);
        if (method === "POST" && actionMatch) {
            const responseBody = await this.viewService.recordMessageAction(
                userId,
                url.searchParams.get("family_id"),
                decodeURIComponent(actionMatch[1]),
                {
                    ...body,
                    idempotency_key: body.idempotency_key || headers["idempotency-key"],
                },
            );
            return { status: 200, body: responseBody };
        }

        return null;
    }
}

module.exports = { NativeApiRouter, etagFor };
