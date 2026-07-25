"use strict";

const DAY_MS = 24 * 60 * 60 * 1000;

function dateKeyShanghai(value = new Date()) {
    return new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).format(value);
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
    const start = Date.parse(`${dateKey}T00:00:00+08:00`);
    if (!Number.isFinite(start) || dateKeyShanghai(new Date(start)) !== dateKey) {
        throw Object.assign(new Error("invalid activity date"), { statusCode: 400 });
    }
    return [start, start + DAY_MS];
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

function summarizeDay(date, intervals = []) {
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
    return {
        date,
        has_data: valid.length > 0,
        active_minutes: durationMinutes(valid.map((item) => [item.started, item.ended])),
        interval_count: valid.length,
        person_count_max: personCountMax,
        first_activity_at: valid[0]?.started_at || null,
        last_activity_at: valid[valid.length - 1]?.ended_at || null,
        observed_postures: [...postures].sort(),
        rooms,
    };
}

function buildActivityOverview(date, intervalsByDate = {}) {
    const dates = dateKeysEndingAt(date, 7);
    const days = dates.map((day) => summarizeDay(day, intervalsByDate[day] || []));
    const today = days[days.length - 1];
    const baselineDays = days.slice(0, -1).filter((day) => day.has_data);
    const baselineMinutes = baselineDays.length
        ? Math.round(baselineDays.reduce((total, day) => total + day.active_minutes, 0) / baselineDays.length)
        : null;
    const facts = [];
    if (today.has_data) {
        facts.push(`今日记录 ${today.active_minutes} 分钟可验证活动`);
        if (today.rooms[0]) facts.push(`${today.rooms[0].room}活动时间最长`);
    }
    if (baselineMinutes !== null && today.has_data) {
        const delta = today.active_minutes - baselineMinutes;
        const threshold = Math.max(15, Math.round(baselineMinutes * 0.3));
        if (Math.abs(delta) >= threshold) {
            facts.push(delta > 0 ? "今日活动时长高于近期记录" : "今日活动时长低于近期记录");
        }
    }
    return {
        date,
        today,
        seven_day_trend: days,
        baseline: {
            comparable_days: baselineDays.length,
            average_active_minutes: baselineMinutes,
        },
        facts,
    };
}

module.exports = {
    buildActivityOverview,
    clipIntervalToDate,
    dateKeyShanghai,
    dateKeysEndingAt,
    dayBoundsShanghai,
    durationMinutes,
    groupIntervalsByDate,
    mergeRanges,
    summarizeDay,
};
