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
        if (url.pathname === "/api/v2/account/profile") {
            if (method === "GET") {
                return { status: 200, body: await this.viewService.accountProfile(userId) };
            }
            if (method === "PATCH") {
                return { status: 200, body: await this.viewService.updateAccountProfile(userId, body) };
            }
        }

        if (method === "GET" && url.pathname === "/api/v2/account/export") {
            return {
                status: 200,
                body: await this.viewService.accountExport(userId),
                headers: { "Content-Disposition": "attachment; filename=Gohome-data-export.json" },
            };
        }

        if (method === "GET" && url.pathname === "/api/v2/account/deletion-plan") {
            return { status: 200, body: await this.viewService.accountDeletionPlan(userId) };
        }

        if (method === "DELETE" && url.pathname === "/api/v2/account") {
            return { status: 200, body: await this.viewService.deleteAccount(userId, body) };
        }

        const familyMembersMatch = url.pathname.match(/^\/api\/v2\/families\/([^/]+)\/members$/);
        if (method === "GET" && familyMembersMatch) {
            return { status: 200, body: await this.viewService.familyMembers(userId, decodeURIComponent(familyMembersMatch[1])) };
        }

        const familyMemberMatch = url.pathname.match(/^\/api\/v2\/families\/([^/]+)\/members\/([^/]+)$/);
        if (method === "DELETE" && familyMemberMatch) {
            return {
                status: 200,
                body: await this.viewService.removeFamilyMember(
                    userId,
                    decodeURIComponent(familyMemberMatch[1]),
                    decodeURIComponent(familyMemberMatch[2]),
                ),
            };
        }

        const familyLeaveMatch = url.pathname.match(/^\/api\/v2\/families\/([^/]+)\/leave$/);
        if (method === "POST" && familyLeaveMatch) {
            return { status: 200, body: await this.viewService.leaveFamily(userId, decodeURIComponent(familyLeaveMatch[1])) };
        }

        const ownershipTransferMatch = url.pathname.match(/^\/api\/v2\/families\/([^/]+)\/ownership-transfer$/);
        if (method === "POST" && ownershipTransferMatch) {
            return {
                status: 200,
                body: await this.viewService.transferFamilyOwnership(
                    userId,
                    decodeURIComponent(ownershipTransferMatch[1]),
                    body.target_member_id,
                    body,
                ),
            };
        }

        const familyInvitationsMatch = url.pathname.match(/^\/api\/v2\/families\/([^/]+)\/invitations$/);
        if (familyInvitationsMatch) {
            const familyId = decodeURIComponent(familyInvitationsMatch[1]);
            if (method === "GET") {
                return { status: 200, body: await this.viewService.familyInvitations(userId, familyId) };
            }
            if (method === "POST") {
                return { status: 201, body: await this.viewService.createFamilyInvitation(userId, familyId, body) };
            }
        }

        const familyInvitationMatch = url.pathname.match(/^\/api\/v2\/families\/([^/]+)\/invitations\/([^/]+)$/);
        if (method === "DELETE" && familyInvitationMatch) {
            return {
                status: 200,
                body: await this.viewService.revokeFamilyInvitation(
                    userId,
                    decodeURIComponent(familyInvitationMatch[1]),
                    decodeURIComponent(familyInvitationMatch[2]),
                ),
            };
        }

        if (method === "POST" && url.pathname === "/api/v2/family-invitations/consume") {
            return { status: 200, body: await this.viewService.consumeFamilyInvitation(userId, body) };
        }

        if (method === "GET" && url.pathname === "/api/v2/app/bootstrap") {
            const body = await this.viewService.bootstrapForUser(userId);
            const etag = etagFor(body.revision);
            if (notModified(headers, body.revision)) return { status: 304, headers: { ETag: etag } };
            return { status: 200, body, headers: { ETag: etag } };
        }

        if (method === "GET" && url.pathname === "/api/v2/home") {
            const body = await this.viewService.homeForFamily(userId, url.searchParams.get("family_id"), headers);
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

        if (method === "GET" && url.pathname === "/api/v2/products") {
            const responseBody = await this.viewService.productsForFamily(userId, url.searchParams.get("family_id"), {
                categories: url.searchParams.getAll("category"),
                limit: url.searchParams.get("limit") || undefined,
            });
            const etag = etagFor(responseBody.revision);
            if (notModified(headers, responseBody.revision)) return { status: 304, headers: { ETag: etag } };
            return { status: 200, body: responseBody, headers: { ETag: etag } };
        }

        if (method === "GET" && url.pathname === "/api/v2/activity-timeline") {
            const responseBody = await this.viewService.activityTimelineForFamily(userId, url.searchParams.get("family_id"), {
                date: url.searchParams.get("date") || undefined,
            });
            const etag = etagFor(responseBody.revision);
            if (notModified(headers, responseBody.revision)) return { status: 304, headers: { ETag: etag } };
            return { status: 200, body: responseBody, headers: { ETag: etag } };
        }

        if (method === "GET" && url.pathname === "/api/v2/activity-overview") {
            const responseBody = await this.viewService.activityOverviewForFamily(userId, url.searchParams.get("family_id"), {
                date: url.searchParams.get("date") || undefined,
            });
            const etag = etagFor(responseBody.revision);
            if (notModified(headers, responseBody.revision)) return { status: 304, headers: { ETag: etag } };
            return { status: 200, body: responseBody, headers: { ETag: etag } };
        }

        if (method === "DELETE" && url.pathname === "/api/v2/activity-history") {
            return {
                status: 200,
                body: await this.viewService.deleteActivityHistory(userId, url.searchParams.get("family_id")),
            };
        }

        const productMatch = url.pathname.match(/^\/api\/v2\/products\/([^/]+)$/);
        if (method === "GET" && productMatch) {
            const responseBody = await this.viewService.productForFamily(
                userId,
                url.searchParams.get("family_id"),
                decodeURIComponent(productMatch[1]),
            );
            const etag = etagFor(responseBody.revision);
            if (notModified(headers, responseBody.revision)) return { status: 304, headers: { ETag: etag } };
            return { status: 200, body: responseBody, headers: { ETag: etag } };
        }

        if (method === "GET" && url.pathname === "/api/v2/product-preferences") {
            return { status: 200, body: await this.viewService.productPreferences(userId, url.searchParams.get("family_id")) };
        }

        if (method === "PUT" && url.pathname === "/api/v2/product-preferences") {
            return {
                status: 200,
                body: await this.viewService.updateProductPreferences(userId, url.searchParams.get("family_id"), body),
            };
        }

        if (url.pathname === "/api/v2/memories") {
            const familyId = url.searchParams.get("family_id");
            if (method === "GET") {
                const responseBody = await this.viewService.memoriesForFamily(userId, familyId, {
                    limit: url.searchParams.get("limit") || undefined,
                });
                const etag = etagFor(responseBody.revision);
                if (notModified(headers, responseBody.revision)) return { status: 304, headers: { ETag: etag } };
                return { status: 200, body: responseBody, headers: { ETag: etag } };
            }
            if (method === "POST") return { status: 201, body: await this.viewService.createMemory(userId, familyId, body) };
        }

        const memoryMatch = url.pathname.match(/^\/api\/v2\/memories\/([^/]+)$/);
        if (memoryMatch) {
            const memoryId = decodeURIComponent(memoryMatch[1]);
            const familyId = url.searchParams.get("family_id");
            if (method === "PATCH") return { status: 200, body: await this.viewService.updateMemory(userId, familyId, memoryId, body) };
            if (method === "DELETE") return { status: 200, body: await this.viewService.deleteMemory(userId, familyId, memoryId) };
        }

        const commentCollectionMatch = url.pathname.match(/^\/api\/v2\/memories\/([^/]+)\/comments$/);
        if (method === "POST" && commentCollectionMatch) {
            return {
                status: 201,
                body: await this.viewService.addMemoryComment(
                    userId,
                    url.searchParams.get("family_id"),
                    decodeURIComponent(commentCollectionMatch[1]),
                    body,
                ),
            };
        }

        const commentMatch = url.pathname.match(/^\/api\/v2\/memories\/([^/]+)\/comments\/([^/]+)$/);
        if (method === "DELETE" && commentMatch) {
            return {
                status: 200,
                body: await this.viewService.deleteMemoryComment(
                    userId,
                    url.searchParams.get("family_id"),
                    decodeURIComponent(commentMatch[1]),
                    decodeURIComponent(commentMatch[2]),
                ),
            };
        }

        const favoriteMatch = url.pathname.match(/^\/api\/v2\/memories\/([^/]+)\/favorite$/);
        if (favoriteMatch && ["PUT", "DELETE"].includes(method)) {
            return {
                status: 200,
                body: await this.viewService.setMemoryFavorite(
                    userId,
                    url.searchParams.get("family_id"),
                    decodeURIComponent(favoriteMatch[1]),
                    method === "PUT",
                ),
            };
        }

        return null;
    }
}

module.exports = { NativeApiRouter, etagFor };
