import { describe, expect, it } from "vitest";
import {
  isCatalogPage,
  isConfigPayload,
  isContextResponse,
  isHealthPayload,
  isProfileList,
} from "./guards";

const validConfig = {
  root: "C:/lnt-sessions",
  profiles: ["bad", "quiet"],
  defaults: {
    simulate: { duration_s: 2.4, sample_rate_hz: 500000, seed: 6022, repeat: 1, interval_s: 0 },
    capture: { duration_s: 2.4, sample_rate_hz: 1000000, range_v: 5, repeat: 1, interval_s: 0 },
    ranges: [0.5, 5, 20],
  },
  build_id: "0.1.0+abc123",
  mutation_nonce: "nonce-value",
  static_asset_hash: "deadbeef",
  static_assets: { app: "/static/app.deadbeef.js" },
};

describe("isHealthPayload", () => {
  it("accepts the /api/health contract shape", () => {
    expect(isHealthPayload({ status: "ok", build_id: "0.1.0+abc123" })).toBe(true);
  });

  it("rejects missing build_id and non-objects", () => {
    expect(isHealthPayload({ status: "ok" })).toBe(false);
    expect(isHealthPayload("ok")).toBe(false);
    expect(isHealthPayload(null)).toBe(false);
  });
});

describe("isConfigPayload", () => {
  it("accepts the full /api/config contract shape", () => {
    expect(isConfigPayload(validConfig)).toBe(true);
  });

  it("rejects when defaults or nonce are missing", () => {
    const { mutation_nonce: _nonce, ...broken } = validConfig;
    expect(isConfigPayload(broken)).toBe(false);
    expect(isConfigPayload({ ...validConfig, defaults: {} })).toBe(false);
  });
});

describe("isCatalogPage", () => {
  it("accepts a cursor page of catalog sessions", () => {
    expect(
      isCatalogPage({
        items: [
          {
            id: "2026-08-01_a",
            health: "ok",
            created_utc: "2026-08-01T10:00:00Z",
            source: "capture",
            session_type: "needle",
            profile: null,
            label: "kitchen",
          },
        ],
        next_cursor: null,
      }),
    ).toBe(true);
  });

  it("rejects unknown health values and wrong item shapes", () => {
    expect(isCatalogPage({ items: [{ id: "x", health: "bogus" }], next_cursor: null })).toBe(false);
    expect(isCatalogPage({ items: "all", next_cursor: null })).toBe(false);
  });
});

describe("isContextResponse", () => {
  it("accepts a materialized context view", () => {
    expect(
      isContextResponse({
        session_id: "s1",
        revision: 3,
        health: "ok",
        reason_codes: [],
        fields: {
          outlet: { kind: "string", value: "A1", captured_at: "2026-08-01T10:00:00Z" },
        },
        tags: ["kitchen"],
        notes: null,
      }),
    ).toBe(true);
  });

  it("rejects non-numeric revision or non-record fields", () => {
    expect(isContextResponse({ session_id: "s", revision: "3", fields: {}, tags: [] })).toBe(false);
    expect(isContextResponse({ session_id: "s", revision: 1, fields: [], tags: [] })).toBe(false);
  });
});

describe("isProfileList", () => {
  it("accepts versioned profile revisions", () => {
    expect(
      isProfileList({
        items: [
          {
            profile_id: "loc-1",
            kind: "location",
            revision: 2,
            captured_at: "2026-08-01T10:00:00Z",
            data: { alias: "home", outlet: "A1", circuit: "L1" },
          },
        ],
      }),
    ).toBe(true);
  });

  it("rejects unknown profile kinds and missing data", () => {
    expect(isProfileList({ items: [{ profile_id: "p", kind: "other", data: {} }] })).toBe(false);
    expect(isProfileList({ items: [{}] })).toBe(false);
  });
});
