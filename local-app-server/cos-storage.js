"use strict";

const COS = require("cos-nodejs-sdk-v5");

function envEnabled(value) {
    return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function createDisabledStorage() {
    return {
        enabled: false,
        bucket: "",
        region: "",
        signedPutUrl() {
            throw new Error("COS storage is not configured");
        },
        signedGetUrl() {
            throw new Error("COS storage is not configured");
        },
        async headObject() {
            throw new Error("COS storage is not configured");
        },
        async putObject() {
            throw new Error("COS storage is not configured");
        },
        async deleteObject() {},
    };
}

function createCosStorage(options = {}) {
    const enabled = options.enabled ?? envEnabled(process.env.GOHOME_COS_ENABLED);
    if (!enabled) return createDisabledStorage();

    const bucket = String(options.bucket || process.env.GOHOME_COS_BUCKET || "").trim();
    const region = String(options.region || process.env.GOHOME_COS_REGION || "").trim();
    const secretId = String(options.secretId || process.env.GOHOME_COS_SECRET_ID || "").trim();
    const secretKey = String(options.secretKey || process.env.GOHOME_COS_SECRET_KEY || "").trim();
    if (!bucket || !region || (!options.client && (!secretId || !secretKey))) {
        return createDisabledStorage();
    }

    const client = options.client || new COS({ SecretId: secretId, SecretKey: secretKey });
    return {
        enabled: true,
        bucket,
        region,
        signedPutUrl({ key, contentType, expiresSeconds = 600 }) {
            return client.getObjectUrl({
                Bucket: bucket,
                Region: region,
                Key: key,
                Method: "PUT",
                Sign: true,
                Expires: expiresSeconds,
                Protocol: "https:",
                Headers: { "Content-Type": contentType },
            });
        },
        signedGetUrl({ key, expiresSeconds = 300 }) {
            return client.getObjectUrl({
                Bucket: bucket,
                Region: region,
                Key: key,
                Method: "GET",
                Sign: true,
                Expires: expiresSeconds,
                Protocol: "https:",
            });
        },
        async headObject({ key }) {
            return client.headObject({ Bucket: bucket, Region: region, Key: key });
        },
        async putObject({ key, body, contentType }) {
            if (!key) throw new Error("COS object key is required");
            return client.putObject({
                Bucket: bucket,
                Region: region,
                Key: key,
                Body: body,
                ContentType: contentType || "application/octet-stream",
            });
        },
        async deleteObject({ key }) {
            if (!key) return;
            await client.deleteObject({ Bucket: bucket, Region: region, Key: key });
        },
    };
}

module.exports = { createCosStorage };
