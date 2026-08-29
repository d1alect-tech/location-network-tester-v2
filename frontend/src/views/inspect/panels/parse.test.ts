import { describe, expect, it } from "vitest";
import { parseApd } from "./apd";
import { parseAudio } from "./audio";
import { parseBurst } from "./burst";
import { parseCmDmCsv } from "./cmDm";
import { parseHarmonics } from "./harmonics";
import { parseItic } from "./itic";
import { parseNotching } from "./notching";
import { parseTrends } from "./trends";

/** Given / When / Then: missing artifacts stay null — never a fake 0. */

describe("panel parsers", () => {
  it("returns null for missing harmonics windows instead of a fake 0", () => {
    // Given / When / Then
    expect(parseHarmonics(null)).toBeNull();
    expect(parseHarmonics({ windows: [] })).toBeNull();
  });

  it("returns null for missing notching instead of a fake 0", () => {
    expect(parseNotching(null)).toBeNull();
    expect(parseNotching({ notches: [] })).toBeNull();
  });

  it("returns null for missing APD bins instead of a fake 0", () => {
    expect(parseApd(null)).toBeNull();
    expect(parseApd({ apd: [] })).toBeNull();
  });

  it("keeps burst_count 0 as a real empty list, not a missing file", () => {
    // Given
    const payload = { burst_count: 0, bursts: [] };

    // When
    const view = parseBurst(payload);

    // Then
    expect(view).toEqual({ count: 0, rows: [] });
    expect(parseBurst(null)).toBeNull();
  });

  it("returns null for missing trends instead of a fake 0 slope", () => {
    expect(parseTrends(null)).toBeNull();
    expect(parseTrends({ crest_factor: 1.2 })).toBeNull();
  });

  it("returns null for missing audio instead of a fake 0 band", () => {
    expect(parseAudio(null)).toBeNull();
  });

  it("returns null for missing ITIC summary instead of a fake 0", () => {
    expect(parseItic(null)).toBeNull();
    expect(parseItic({ events: [] })).toBeNull();
  });

  it("returns null for empty CM/DM csv instead of a fake 0 bin", () => {
    expect(parseCmDmCsv("")).toBeNull();
    expect(parseCmDmCsv("frequency_hz,other\n")).toBeNull();
  });
});
