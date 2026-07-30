"use strict";

const DAY_MS = 24 * 60 * 60 * 1000;
const SHANGHAI_DATE_FORMATTER = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
});
const SHANGHAI_TIME_FORMATTER = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
});
const DAY_BOUNDS_CACHE = new Map();

function dateKeyShanghai(value = new Date()) {
    return SHANGHAI_DATE_FORMATTER.format(value);
}

function dateKeysEndingAt(dateKey, count) {
    const [dayStart] = dayBoundsShanghai(dateKey);
    const anchor = dayStart + DAY_MS / 2;
    return Array.from({ length: count }, (_, index) => (
        dateKeyShanghai(new Date(anchor - (count - index - 1) * DAY_MS))
    ));
}

function dayBoundsShanghai(dateKey) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(dateKey || ""))) {
        throw Object.assign(new Error("invalid activity date"), { statusCode: 400 });
    }
    const cached = DAY_BOUNDS_CACHE.get(dateKey);
    if (cached) return cached;
    const start = Date.parse(`${dateKey}T00:00:00+08:00`);
    if (!Number.isFinite(start) || dateKeyShanghai(new Date(start)) !== dateKey) {
        throw Object.assign(new Error("invalid activity date"), { statusCode: 400 });
    }
    const bounds = Object.freeze([start, start + DAY_MS]);
    if (DAY_BOUNDS_CACHE.size >= 64) DAY_BOUNDS_CACHE.delete(DAY_BOUNDS_CACHE.keys().next().value);
    DAY_BOUNDS_CACHE.set(dateKey, bounds);
    return bounds;
}

function clipIntervalToDate(interval, dateKey) {
    const [dayStart, dayEnd] = dayBoundsShanghai(dateKey);
    const started = Math.max(Date.parse(interval?.started_at || ""), dayStart);
    const ended = Math.min(Date.parse(interval?.ended_at || ""), dayEnd);
    if (!Number.isFinite(started) || !Number.isFinite(ended) || ended <= started) return null;
    return {
        ...interval,
        started_at: new Date(started).toISOString(),
        ended_at: new Date(ended).toISOString(),
    };
}

function groupIntervalsByDate(dates, intervals = []) {
    return Object.fromEntries(dates.map((date) => [
        date,
        intervals.map((interval) => clipIntervalToDate(interval, date)).filter(Boolean),
    ]));
}

function mergeRanges(ranges) {
    const sorted = ranges
        .map(([start, end]) => [Number(start), Number(end)])
        .filter(([start, end]) => Number.isFinite(start) && Number.isFinite(end) && end > start)
        .sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const range of sorted) {
        const previous = merged[merged.length - 1];
        if (!previous || range[0] > previous[1]) merged.push([...range]);
        else previous[1] = Math.max(previous[1], range[1]);
    }
    return merged;
}

function durationMinutes(ranges) {
    const milliseconds = mergeRanges(ranges).reduce((total, [start, end]) => total + end - start, 0);
    return Math.round(milliseconds / 60000);
}

function minuteOfShanghaiDay(value) {
    const parts = SHANGHAI_TIME_FORMATTER.formatToParts(new Date(value)).reduce((result, part) => {
        if (part.type !== "literal") result[part.type] = part.value;
        return result;
    }, {});
    return Number(parts.hour || 0) * 60 + Number(parts.minute || 0);
}

function dayReachedShanghaiMinute(date, evaluationAt, minute) {
    const evaluated = evaluationAt instanceof Date ? evaluationAt : new Date(evaluationAt);
    if (!Number.isFinite(evaluated.getTime())) {
        throw Object.assign(new Error("invalid activity evaluation time"), { statusCode: 400 });
    }
    const evaluationDate = dateKeyShanghai(evaluated);
    if (date < evaluationDate) return true;
    if (date > evaluationDate) return false;
    return minuteOfShanghaiDay(evaluated) >= minute;
}

function activityDurationComparisonReady(date, evaluationAt = new Date()) {
    return dayReachedShanghaiMinute(date, evaluationAt, 20 * 60);
}

function nightActivityComparisonReady(date, evaluationAt = new Date()) {
    return dayReachedShanghaiMinute(date, evaluationAt, 5 * 60);
}

function overlapRanges(intervals, start, end) {
    return intervals
        .map((item) => [Math.max(item.started, start), Math.min(item.ended, end)])
        .filter(([rangeStart, rangeEnd]) => rangeEnd > rangeStart);
}

function summarizeDay(date, intervals = []) {
    const [dayStart] = dayBoundsShanghai(date);
    const valid = intervals
        .map((item) => clipIntervalToDate(item, date))
        .filter(Boolean)
        .map((item) => ({ ...item, started: Date.parse(item.started_at), ended: Date.parse(item.ended_at) }))
        .filter((item) => Number.isFinite(item.started) && Number.isFinite(item.ended) && item.ended > item.started)
        .sort((a, b) => a.started - b.started);
    const roomRanges = new Map();
    const roomCounts = new Map();
    const postures = new Set();
    let personCountMax = 0;
    for (const interval of valid) {
        const room = String(interval.room || "").trim() || "监控区域";
        if (!roomRanges.has(room)) roomRanges.set(room, []);
        roomRanges.get(room).push([interval.started, interval.ended]);
        roomCounts.set(room, (roomCounts.get(room) || 0) + 1);
        personCountMax = Math.max(personCountMax, Number(interval.person_count_max || 0));
        for (const posture of Array.isArray(interval.postures) ? interval.postures : []) {
            const value = String(posture || "").trim();
            if (value) postures.add(value);
        }
    }
    const rooms = [...roomRanges.entries()]
        .map(([room, ranges]) => ({
            room,
            active_minutes: durationMinutes(ranges),
            interval_count: roomCounts.get(room) || 0,
        }))
        .sort((a, b) => b.active_minutes - a.active_minutes || a.room.localeCompare(b.room, "zh-CN"));
    const nightRanges = mergeRanges(overlapRanges(valid, dayStart, dayStart + 5 * 60 * 60 * 1000));
    return {
        date,
        has_data: valid.length > 0,
        active_minutes: durationMinutes(valid.map((item) => [item.started, item.ended])),
        interval_count: valid.length,
        person_count_max: personCountMax,
        first_activity_at: valid[0]?.started_at || null,
        last_activity_at: valid[valid.length - 1]?.ended_at || null,
        first_activity_minute: valid[0] ? minuteOfShanghaiDay(valid[0].started_at) : null,
        night_activity_minutes: durationMinutes(nightRanges),
        night_activity_sessions: nightRanges.length,
        observed_postures: [...postures].sort(),
        rooms,
    };
}

function attentionItem(type, facts, suggestedTopic) {
    return {
        type,
        severity: "notice",
        label: "需要留意",
        facts,
        suggested_topic: suggestedTopic,
        requires_review: false,
    };
}

function buildActivityOverview(date, intervalsByDate = {}, options = {}) {
    const dates = dateKeysEndingAt(date, 7);
    const days = dates.map((day) => summarizeDay(day, intervalsByDate[day] || []));
    const today = days[days.length - 1];
    const baselineDays = days.slice(0, -1).filter((day) => day.has_data);
    const baselineMinutes = baselineDays.length
        ? Math.round(baselineDays.reduce((total, day) => total + day.active_minutes, 0) / baselineDays.length)
        : null;
    const baselineFirstActivity = baselineDays.length
        ? Math.round(baselineDays.reduce((total, day) => total + day.first_activity_minute, 0) / baselineDays.length)
        : null;
    const canCompareRoutine = today.has_data && baselineDays.length >= 3;
    const canCompareActivityDuration = canCompareRoutine
        && activityDurationComparisonReady(date, options.evaluationAt);
    const canCompareNightActivity = nightActivityComparisonReady(date, options.evaluationAt);
    const facts = [];
    const attentionItems = [];
    if (today.has_data) {
        facts.push(`今日记录 ${today.active_minutes} 分钟可验证活动`);
        if (today.rooms[0]) facts.push(`${today.rooms[0].room}活动时间最长`);
    }
    if (canCompareRoutine && baselineMinutes !== null) {
        const delta = today.active_minutes - baselineMinutes;
        const threshold = Math.max(15, Math.round(baselineMinutes * 0.3));
        if (delta >= threshold || (canCompareActivityDuration && delta <= -threshold)) {
            facts.push(delta > 0 ? "今日活动时长高于近期记录" : "今日活动时长低于近期记录");
        }
        if (canCompareActivityDuration
            && baselineMinutes >= 30
            && delta < 0
            && today.active_minutes <= Math.round(baselineMinutes * 0.6)) {
            attentionItems.push(attentionItem(
                "activity_reduced",
                [`今日已记录 ${today.active_minutes} 分钟活动`, `近期可比较日平均 ${baselineMinutes} 分钟`],
                "今天过得怎么样？有没有什么想和我聊聊的？",
            ));
        }
    }
    if (canCompareNightActivity
        && today.has_data
        && (today.night_activity_sessions >= 2 || today.night_activity_minutes >= 20)) {
        attentionItems.push(attentionItem(
            "night_activity",
            [`00:00–05:00 记录 ${today.night_activity_minutes} 分钟活动`, `共形成 ${today.night_activity_sessions} 段可验证活动`],
            "昨晚休息得怎么样？今天要不要早点休息？",
        ));
    }
    if (canCompareRoutine && baselineFirstActivity !== null && today.first_activity_minute !== null) {
        const shift = today.first_activity_minute - baselineFirstActivity;
        if (Math.abs(shift) >= 120) {
            attentionItems.push(attentionItem(
                "routine_shift",
                [
                    `今日首次活动 ${formatClockMinute(today.first_activity_minute)}`,
                    `近期可比较日平均 ${formatClockMinute(baselineFirstActivity)}`,
                ],
                "今天的安排和平时不太一样吗？最近有什么新计划？",
            ));
        }
    }
    return {
        date,
        today,
        seven_day_trend: days,
        baseline: {
            comparable_days: baselineDays.length,
            average_active_minutes: baselineMinutes,
            average_first_activity_minute: baselineFirstActivity,
        },
        data_quality: {
            status: !today.has_data ? "no_today_activity" : canCompareRoutine ? "comparable" : "building_baseline",
            has_today_activity: today.has_data,
            comparable_days: baselineDays.length,
            minimum_comparable_days: 3,
            can_compare_routine: canCompareRoutine,
            activity_duration_comparison_ready: canCompareActivityDuration,
            night_activity_comparison_ready: canCompareNightActivity,
        },
        facts,
        attention_items: attentionItems,
    };
}

function formatClockMinute(value) {
    const minutes = Math.max(0, Math.min(1439, Number(value) || 0));
    return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

module.exports = {
    activityDurationComparisonReady,
    buildActivityOverview,
    clipIntervalToDate,
    dateKeyShanghai,
    dateKeysEndingAt,
    dayBoundsShanghai,
    durationMinutes,
    formatClockMinute,
    groupIntervalsByDate,
    mergeRanges,
    nightActivityComparisonReady,
    summarizeDay,
};
