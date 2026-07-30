"use strict";

const ALLOWED_CATEGORIES = new Set([
    "居家防滑与安全",
    "照明与视野",
    "日常生活与收纳",
    "沟通与简易电子",
    "非医疗出行配件",
]);

const EXCLUDED_TERMS = [
    "药品", "药物", "处方", "非处方药", "保健品", "膳食补充剂", "营养补充剂",
    "医疗器械", "诊断", "治疗", "治愈", "疗效", "康复", "降血压", "降血糖",
    "改善疾病", "预防疾病", "缓解疼痛", "矫正", "监测血压", "监测血糖", "血氧仪",
];

const MAX_VERIFICATION_AGE_DAYS = 180;

function text(value) {
    return String(value || "").trim();
}

function httpsUrl(value) {
    try {
        const parsed = new URL(text(value));
        return parsed.protocol === "https:" ? parsed.toString() : "";
    } catch (_error) {
        return "";
    }
}

function stringArray(value) {
    return Array.isArray(value)
        ? [...new Set(value.map(text).filter(Boolean))]
        : [];
}

function productPolicyErrors(product, { now = Date.now(), maxAgeDays = MAX_VERIFICATION_AGE_DAYS } = {}) {
    const errors = [];
    const category = text(product?.category);
    const searchable = [
        category,
        product?.brand,
        product?.name,
        product?.summary,
        product?.disclosure,
        ...stringArray(product?.suitability),
    ].map(text).join(" ").toLowerCase();
    if (!ALLOWED_CATEGORIES.has(category)) errors.push("unsupported category");
    if (!text(product?.brand)) errors.push("brand required");
    if (!text(product?.name)) errors.push("name required");
    if (!httpsUrl(product?.image_url)) errors.push("https image required");
    if (!text(product?.source_name)) errors.push("source required");
    if (!httpsUrl(product?.source_url)) errors.push("https source required");
    if (!stringArray(product?.suitability).length) errors.push("suitability required");
    const verifiedAt = Date.parse(product?.verified_at || "");
    const maximumAge = Math.max(1, Number(maxAgeDays) || MAX_VERIFICATION_AGE_DAYS) * 86400000;
    if (!Number.isFinite(verifiedAt)) errors.push("verification time required");
    else if (verifiedAt > now + 86400000 || now - verifiedAt > maximumAge) errors.push("verification is stale");
    if (EXCLUDED_TERMS.some((term) => searchable.includes(term.toLowerCase()))) errors.push("medical or regulated claim excluded");
    return [...new Set(errors)];
}

function isProductAllowed(product, options) {
    return productPolicyErrors(product, options).length === 0;
}

function recommendationReason(product, preferences = {}) {
    const needs = stringArray(preferences.needs);
    const suitability = stringArray(product.suitability);
    const matchedNeed = needs.find((need) => suitability.some((label) => label.includes(need) || need.includes(label)));
    if (matchedNeed) return `符合已选择的“${matchedNeed}”需求`;
    if (stringArray(preferences.categories).includes(text(product.category))) return `符合已选择的“${text(product.category)}”类别`;
    return suitability[0] ? `适合关注“${suitability[0]}”的家庭` : "来自已核验的非医疗生活用品清单";
}

function productView(product, preferences = {}, options = {}) {
    if (!isProductAllowed(product, options)) return null;
    return {
        id: text(product.id),
        category: text(product.category),
        brand: text(product.brand),
        name: text(product.name),
        summary: text(product.summary),
        image_url: httpsUrl(product.image_url),
        source_name: text(product.source_name),
        source_url: httpsUrl(product.source_url),
        suitability: stringArray(product.suitability),
        recommendation_reason: recommendationReason(product, preferences),
        disclosure: text(product.disclosure) || "无赞助或返佣关系",
        verified_at: new Date(product.verified_at).toISOString(),
    };
}

function normalizeProductPreferences(input = {}) {
    const categories = stringArray(input.categories);
    const unsupported = categories.filter((category) => !ALLOWED_CATEGORIES.has(category));
    if (unsupported.length) {
        throw Object.assign(new Error(`unsupported product categories: ${unsupported.join(", ")}`), { statusCode: 400 });
    }
    return {
        categories: categories.slice(0, ALLOWED_CATEGORIES.size),
        needs: stringArray(input.needs).slice(0, 12),
    };
}

module.exports = {
    ALLOWED_CATEGORIES,
    EXCLUDED_TERMS,
    MAX_VERIFICATION_AGE_DAYS,
    isProductAllowed,
    normalizeProductPreferences,
    productPolicyErrors,
    productView,
};
