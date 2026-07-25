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
        "2026-07-23": [interval("2026-07-23", 60)],
        "2026-07-24": [interval("2026-07-24", 60)],
        "2026-07-25": [interval("2026-07-25", 20)],
    });
    assert.equal(overview.baseline.comparable_days, 2);
    assert.equal(overview.baseline.average_active_minutes, 60);
    assert.equal(overview.facts.includes("今日活动时长低于近期记录"), true);
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
