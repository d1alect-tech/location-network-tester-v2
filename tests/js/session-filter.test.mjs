import assert from "node:assert/strict";
import { test } from "node:test";

import { filterSessions, sortSessions } from "../../src/lnt/ui/static/session-filter.js";

function session(name, createdUtc, extra = {}) {
  const summary = createdUtc === null
    ? null
    : { session_id: name, created_utc: createdUtc, ...extra };
  return { name, status: "valid", error: null, analyzed: true, summary };
}

test("sortSessions orders by created_utc descending", () => {
  const sessions = [
    session("first", "2026-08-01T10:00:00Z"),
    session("third", "2026-08-03T10:00:00Z"),
    session("second", "2026-08-02T10:00:00Z"),
  ];

  const sorted = sortSessions(sessions);

  assert.deepEqual(sorted.map((item) => item.name), ["third", "second", "first"]);
});

test("sortSessions puts sessions without summary or created_utc last", () => {
  const withoutDate = { name: "no-date", status: "valid", error: null, analyzed: false, summary: { session_id: "no-date" } };
  const sessions = [session("no-summary", null), withoutDate, session("dated", "2026-08-02T10:00:00Z")];

  const sorted = sortSessions(sessions);

  assert.equal(sorted[0].name, "dated");
  assert.deepEqual(sorted.slice(1).map((item) => item.name), ["no-date", "no-summary"]);
});

test("sortSessions breaks ties by name ascending", () => {
  const sessions = [
    session("b-session", "2026-08-01T10:00:00Z"),
    session("a-session", "2026-08-01T10:00:00Z"),
  ];

  const sorted = sortSessions(sessions);

  assert.deepEqual(sorted.map((item) => item.name), ["a-session", "b-session"]);
});

test("sortSessions does not mutate its input", () => {
  const sessions = [session("first", "2026-08-01T10:00:00Z"), session("second", "2026-08-02T10:00:00Z")];

  const sorted = sortSessions(sessions);

  assert.notEqual(sorted, sessions);
  assert.deepEqual(sessions.map((item) => item.name), ["first", "second"]);
});

test("filterSessions matches name and label case-insensitively", () => {
  const sessions = [
    { name: "Alpha-1", status: "valid", error: null, analyzed: true, summary: { label: "стенд А" } },
    { name: "beta", status: "valid", error: null, analyzed: true, summary: null },
  ];

  assert.equal(filterSessions(sessions, "alpha").length, 1);
  assert.equal(filterSessions(sessions, "СТЕНД").length, 1);
});

test("filterSessions returns a copy for blank query", () => {
  const sessions = [session("first", "2026-08-01T10:00:00Z")];

  const blank = filterSessions(sessions, "");
  const spaced = filterSessions(sessions, "   ");

  assert.notEqual(blank, sessions);
  assert.equal(blank.length, 1);
  assert.equal(spaced.length, 1);
});
