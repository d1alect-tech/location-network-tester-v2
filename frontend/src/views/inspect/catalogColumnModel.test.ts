import { describe, expect, it } from "vitest";
import type { CatalogSession } from "../../api/types";
import { loadKey } from "./bootPick";
import { buildCatalogRows, roleOf } from "./catalogColumnModel";

const sampleSessions: readonly CatalogSession[] = [
  {
    id: "ses-001",
    health: "ok",
    created_utc: "2026-08-28T10:00:00Z",
    source: "hardware",
    session_type: "capture",
    profile: "lab",
    label: "Базовый стенд",
    storage_path: "/data/ses-001",
  },
  {
    id: "ses-002",
    health: "ok",
    created_utc: "2026-08-28T14:30:00Z",
    source: "hardware",
    session_type: "capture",
    profile: "lab",
    label: "Тестовый стенд 1",
    storage_path: "/data/ses-002",
  },
  {
    id: "ses-003",
    health: "ok",
    created_utc: "2026-08-29T09:15:00Z",
    source: "hardware",
    session_type: "simulate",
    profile: "lab",
    label: "Анализ шума",
    storage_path: "/data/ses-003",
  },
];

describe("catalogColumnModel", () => {
  describe("buildCatalogRows - date sorting and grouping", () => {
    it("groups sessions by created_utc day in descending order with correct headers and counts", () => {
      const rows = buildCatalogRows({
        sessions: sampleSessions,
        sort: "date",
        dir: "desc",
        query: "",
      });

      expect(rows).toEqual([
        {
          kind: "group",
          day: "2026-08-29",
          header: "2026-08-29",
          count: 1,
        },
        {
          kind: "session",
          session: sampleSessions[2],
        },
        {
          kind: "group",
          day: "2026-08-28",
          header: "2026-08-28",
          count: 2,
        },
        {
          kind: "session",
          session: sampleSessions[1],
        },
        {
          kind: "session",
          session: sampleSessions[0],
        },
      ]);
    });

    it("groups sessions by created_utc day in ascending order when dir is asc", () => {
      const rows = buildCatalogRows({
        sessions: sampleSessions,
        sort: "date",
        dir: "asc",
        query: "",
      });

      expect(rows).toEqual([
        {
          kind: "group",
          day: "2026-08-28",
          header: "2026-08-28",
          count: 2,
        },
        {
          kind: "session",
          session: sampleSessions[0],
        },
        {
          kind: "session",
          session: sampleSessions[1],
        },
        {
          kind: "group",
          day: "2026-08-29",
          header: "2026-08-29",
          count: 1,
        },
        {
          kind: "session",
          session: sampleSessions[2],
        },
      ]);
    });
  });

  describe("buildCatalogRows - label sorting", () => {
    it("yields zero group rows and ru-collated flat order", () => {
      const rows = buildCatalogRows({
        sessions: sampleSessions,
        sort: "label",
        dir: "asc",
        query: "",
      });

      const groupRows = rows.filter((r) => r.kind === "group");
      expect(groupRows).toHaveLength(0);

      expect(rows).toEqual([
        { kind: "session", session: sampleSessions[2] }, // "Анализ шума"
        { kind: "session", session: sampleSessions[0] }, // "Базовый стенд"
        { kind: "session", session: sampleSessions[1] }, // "Тестовый стенд 1"
      ]);
    });

    it("yields descending ru-collated order when dir is desc", () => {
      const rows = buildCatalogRows({
        sessions: sampleSessions,
        sort: "label",
        dir: "desc",
        query: "",
      });

      expect(rows).toEqual([
        { kind: "session", session: sampleSessions[1] }, // "Тестовый стенд 1"
        { kind: "session", session: sampleSessions[0] }, // "Базовый стенд"
        { kind: "session", session: sampleSessions[2] }, // "Анализ шума"
      ]);
    });
  });

  describe("buildCatalogRows - query filtering", () => {
    it("filters sessions by label containing query case-insensitively", () => {
      const rows = buildCatalogRows({
        sessions: sampleSessions,
        sort: "label",
        dir: "asc",
        query: "стенд",
      });

      expect(rows).toEqual([
        { kind: "session", session: sampleSessions[0] }, // "Базовый стенд"
        { kind: "session", session: sampleSessions[1] }, // "Тестовый стенд 1"
      ]);
    });

    it("falls back to id matching when label is null", () => {
      const sessionWithoutLabel: CatalogSession = {
        id: "target-session-99",
        health: "ok",
        created_utc: "2026-08-28T12:00:00Z",
        source: null,
        session_type: null,
        profile: null,
        label: null,
      };

      const rows = buildCatalogRows({
        sessions: [sessionWithoutLabel],
        sort: "label",
        dir: "asc",
        query: "TARGET",
      });

      expect(rows).toEqual([{ kind: "session", session: sessionWithoutLabel }]);
    });

    it("returns a single empty row when no sessions match query", () => {
      const rows = buildCatalogRows({
        sessions: sampleSessions,
        sort: "date",
        dir: "desc",
        query: "несуществующий-запрос",
      });

      expect(rows).toEqual([{ kind: "empty" }]);
    });

    it("returns a single empty row when input sessions is empty", () => {
      const rows = buildCatalogRows({
        sessions: [],
        sort: "date",
        dir: "desc",
        query: "",
      });

      expect(rows).toEqual([{ kind: "empty" }]);
    });
  });

  describe("buildCatalogRows - unknown-day placement (R3)", () => {
    const dated = (id: string, created: string): CatalogSession => ({
      id,
      health: "ok",
      created_utc: created,
      source: "disk",
      session_type: "capture",
      profile: null,
      label: null,
    });
    const undated: CatalogSession = {
      id: "no-date",
      health: "partial",
      created_utc: null,
      source: null,
      session_type: null,
      profile: null,
      label: null,
    };

    it("date/desc: unknown-группа ПОСЛЕДНЯЯ (зеркало API)", () => {
      const rows = buildCatalogRows({
        sessions: [undated, dated("new", "2026-08-29T10:00:00Z")],
        sort: "date",
        dir: "desc",
        query: "",
      });
      const groups = rows.filter((row) => row.kind === "group");
      expect(groups.map((row) => (row.kind === "group" ? row.day : ""))).toEqual([
        "2026-08-29",
        "unknown",
      ]);
    });

    it("внутри дня — именованный keyset-порядок, не порядок вставки", () => {
      const rows = buildCatalogRows({
        sessions: [dated("b-id", "2026-08-29T09:00:00Z"), dated("a-id", "2026-08-29T11:00:00Z")],
        sort: "date",
        dir: "desc",
        query: "",
      });
      const ids = rows
        .filter((row) => row.kind === "session")
        .map((row) => (row.kind === "session" ? row.session.id : ""));
      expect(ids).toEqual(["a-id", "b-id"]);
    });
  });

  describe("roleOf", () => {
    const ses = (id: string): CatalogSession => ({
      id,
      health: "ok",
      created_utc: null,
      source: null,
      session_type: null,
      profile: null,
      label: null,
    });

    it("returns 'a' when sessionId matches pair.a", () => {
      expect(roleOf(ses("ses-1"), loadKey, { a: "ses-1", b: "ses-2" })).toBe("a");
    });

    it("matches the duplicate row by dir-name load key", () => {
      const dup: CatalogSession = {
        ...ses("syn-quiet-seed6022"),
        health: "duplicate_id",
        storage_path: "/root/sim-quiet-20261005-151028",
      };
      expect(roleOf(dup, loadKey, { a: "sim-quiet-20261005-151028", b: null })).toBe("a");
      expect(roleOf(dup, loadKey, { a: null, b: null })).toBeNull();
    });

    it("returns 'b' when sessionId matches pair.b", () => {
      expect(roleOf(ses("ses-2"), loadKey, { a: "ses-1", b: "ses-2" })).toBe("b");
    });

    it("returns null when sessionId does not match pair", () => {
      expect(roleOf(ses("ses-3"), loadKey, { a: "ses-1", b: "ses-2" })).toBeNull();
      expect(roleOf(ses("ses-1"), loadKey, { a: null, b: null })).toBeNull();
    });
  });
});
