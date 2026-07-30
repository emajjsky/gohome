"use strict";

const crypto = require("crypto");
const { promisify } = require("util");

const FORMAT = "scrypt";
const KEY_LENGTH = 64;
const scrypt = promisify(crypto.scrypt);

async function encodePassword(password, salt = crypto.randomBytes(16)) {
    const value = String(password || "");
    if (!value) throw new Error("password required");
    const derived = await scrypt(value, salt, KEY_LENGTH);
    return `${FORMAT}$${salt.toString("base64")}$${derived.toString("base64")}`;
}

async function verifyPassword(password, encoded) {
    const [format, saltText, hashText, extra] = String(encoded || "").split("$");
    if (format !== FORMAT || !saltText || !hashText || extra !== undefined) return false;
    try {
        const expected = Buffer.from(hashText, "base64");
        if (expected.length !== KEY_LENGTH) return false;
        const actual = await scrypt(String(password || ""), Buffer.from(saltText, "base64"), expected.length);
        return crypto.timingSafeEqual(actual, expected);
    } catch {
        return false;
    }
}

function verifyLegacyPassword(password, legacyPassword) {
    const provided = Buffer.from(String(password || ""));
    const expected = Buffer.from(String(legacyPassword || ""));
    return provided.length > 0 && provided.length === expected.length && crypto.timingSafeEqual(provided, expected);
}

module.exports = { encodePassword, verifyLegacyPassword, verifyPassword };
