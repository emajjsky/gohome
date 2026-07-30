"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
    buildActivityOverview,
    dayBoundsShanghai,
    durationMinutes,
    groupIntervalsByDate,
    summarizeDay,
} = require("../native-api/activity-reporting");

test("activity report merges overlapping cameras instead of double counting family activity", () => {
    assert.equal(durationMinutes([
        [Date.parse("2026-07-25T08:00:00+08:00"), Date.parse("2026-07-25T08:10:00+08:00")],
        [Date.parse("2026-07-25T08:05:00+08:00"), Date.parse("2026-07-25T08:20:00+08:00")],
    ]), 20);
});

test("daily activity summary keeps facts separate from inferred routines", () => {
    const summary = summarizeDay("2026-07-25", [
        {
            room: "厨房",
            started_at: "2026-07-25T04:00:00.000Z",
            ended_at: "2026-07-25T04:12:00.000Z",
            person_count_max: 1,
            postures: ["standing"],
        },
        {
            room: "客厅",
            started_at: "2026-07-25T04:10:00.000Z",
            ended_at: "2026-07-25T04:20:00.000Z",
            person_count_max: 2,
            postures: ["sitting"],
        },
    ]);
    assert.equal(summary.active_minutes, 20);
    assert.equal(summary.person_count_max, 2);
    assert.deepEqual(summary.observed_postures, ["sitting", "standing"]);
    assert.equal(summary.rooms[0].room, "厨房");
    assert.equal(JSON.stringify(summary).includes("吃饭"), false);
});

test("seven day overview only compares days with real observations", () => {
    const interval = (date, minutes) => ({
        room: "客厅",
        started_at: `${date}T01:00:00.000Z`,
        ended_at: new Date(Date.parse(`${date}T01:00:00.000Z`) + minutes * 60000).toISOString(),
        person_count_max: 1,
        postures: ["standing"],
    });
    const overview = buildActivityOverview("2026-07-25", {
        "2026-07-22": [interval("2026-07-22", 60)],
        "2026-07-23": [interval("2026-07-23", 60)],
        "2026-07-24": [interval("2026-07-24", 60)],
        "2026-07-25": [interval("2026-07-25", 20)],
    }, { evaluationAt: "2026-07-25T20:30:00+08:00" });
    assert.equal(overview.baseline.comparable_days, 3);
    assert.equal(overview.baseline.average_active_minutes, 60);
    assert.equal(overview.facts.includes("今日活动时长低于近期记录"), true);
    assert.equal(overview.data_quality.can_compare_routine, true);
    assert.equal(overview.attention_items.some((item) => item.type === "activity_reduced"), true);
});

test("partial current day never reports reduced activity before the evening comparison window", () => {
    const interval = (date, minutes) => ({
        room: "客厅",
        started_at: `${date}T01:00:00.000Z`,
        ended_at: new Date(Date.parse(`${date}T01:00:00.000Z`) + minutes * 60000).toISOString(),
    });
    const intervals = {
        "2026-07-22": [interval("2026-07-22", 60)],
        "2026-07-23": [interval("2026-07-23", 60)],
        "2026-07-24": [interval("2026-07-24", 60)],
        "2026-07-25": [interval("2026-07-25", 10)],
    };
    const morning = buildActivityOverview("2026-07-25", intervals, {
        evaluationAt: "2026-07-25T10:00:00+08:00",
    });
    const evening = buildActivityOverview("2026-07-25", intervals, {
        evaluationAt: "2026-07-25T20:00:00+08:00",
    });

    assert.equal(morning.data_quality.activity_duration_comparison_ready, false);
    assert.equal(morning.facts.includes("今日活动时长低于近期记录"), false);
    assert.equal(morning.attention_items.some((item) => item.type === "activity_reduced"), false);
    assert.equal(evening.data_quality.activity_duration_comparison_ready, true);
    assert.equal(evening.attention_items.some((item) => item.type === "activity_reduced"), true);
});

test("limited history remains factual and does not produce routine deviation", () => {
    const interval = (date, minutes) => ({
        room: "客厅",
        started_at: `${date}T01:00:00.000Z`,
        ended_at: new Date(Date.parse(`${date}T01:00:00.000Z`) + minutes * 60000).toISOString(),
    });
    const overview = buildActivityOverview("2026-07-25", {
        "2026-07-24": [interval("2026-07-24", 90)],
        "2026-07-25": [interval("2026-07-25", 10)],
    });
    assert.equal(overview.data_quality.status, "building_baseline");
    assert.deepEqual(overview.attention_items, []);
    assert.equal(overview.facts.includes("今日活动时长低于近期记录"), false);
});

test("night activity uses real interval overlap and never invents health conclusions", () => {
    const overview = buildActivityOverview("2026-07-25", {
        "2026-07-25": [{
            room: "客厅",
            started_at: "2026-07-24T17:10:00.000Z",
            ended_at: "2026-07-24T17:35:00.000Z",
            person_count_max: 1,
            postures: ["standing"],
        }],
    });
    const insight = overview.attention_items.find((item) => item.type === "night_activity");
    assert.equal(overview.today.night_activity_minutes, 25);
    assert.equal(insight?.severity, "notice");
    assert.equal(JSON.stringify(insight).includes("诊断"), false);
});

test("night activity waits until the observation window has ended", () => {
    const intervals = {
        "2026-07-25": [{
            room: "客厅",
            started_at: "2026-07-24T17:10:00.000Z",
            ended_at: "2026-07-24T17:35:00.000Z",
        }],
    };
    const beforeWindowEnd = buildActivityOverview("2026-07-25", intervals, {
        evaluationAt: "2026-07-25T04:59:00+08:00",
    });
    const afterWindowEnd = buildActivityOverview("2026-07-25", intervals, {
        evaluationAt: "2026-07-25T05:00:00+08:00",
    });

    assert.equal(beforeWindowEnd.data_quality.night_activity_comparison_ready, false);
    assert.equal(beforeWindowEnd.attention_items.some((item) => item.type === "night_activity"), false);
    assert.equal(afterWindowEnd.data_quality.night_activity_comparison_ready, true);
    assert.equal(afterWindowEnd.attention_items.some((item) => item.type === "night_activity"), true);
});

test("activity crossing Shanghai midnight is clipped into each natural day", () => {
    const dates = ["2026-07-24", "2026-07-25"];
    const grouped = groupIntervalsByDate(dates, [{
        room: "客厅",
        started_at: "2026-07-24T23:50:00+08:00",
        ended_at: "2026-07-25T00:20:00+08:00",
        person_count_max: 1,
        postures: ["standing"],
    }]);
    assert.equal(summarizeDay(dates[0], grouped[dates[0]]).active_minutes, 10);
    assert.equal(summarizeDay(dates[1], grouped[dates[1]]).active_minutes, 20);
});

test("activity dates reject calendar days that only match the text format", () => {
    assert.throws(() => dayBoundsShanghai("2026-02-30"), /invalid activity date/);
});
