import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/errors";
import type { SpectrogramLevel } from "../../components/charts/spectrogramModel";
import { createGramPair } from "./gramPair";
import type { GramPairTile } from "./gramPair";

function makeLevel(
  timeS: readonly number[],
  frequencyHz: readonly number[],
  powerDb: readonly number[],
): SpectrogramLevel {
  return {
    timeS: Float64Array.from(timeS),
    frequencyHz: Float64Array.from(frequencyHz),
    powerDb: Float32Array.from(powerDb),
    timeBins: timeS.length,
    bands: frequencyHz.length,
  };
}

const TIME = [0, 0.5] as const;
const FREQ = [10, 20] as const;
const POWER_A = [0, 2, 4, 6] as const;
const POWER_B = [3, 1, 10, 4] as const;
const DELTA_B_MINUS_A = [3, -1, 6, -2] as const;

const LEVEL_A = makeLevel(TIME, FREQ, POWER_A);
const LEVEL_B = makeLevel(TIME, FREQ, POWER_B);
const LEVEL_B_MISMATCH = makeLevel([0, 0.5, 1], FREQ, [1, 2, 3, 4, 5, 6]);

const STUB_CLIENT = {
  analysis: {
    artifactBytes: async (): Promise<ArrayBuffer> => new ArrayBuffer(0),
  },
};

function fakeLoadLevel(
  levels: ReadonlyMap<string, SpectrogramLevel>,
): (session: string, _signal: AbortSignal) => Promise<SpectrogramLevel> {
  return async (session) => {
    const level = levels.get(session);
    if (level === undefined) {
      throw new Error(`no synthetic level for ${session}`);
    }
    return level;
  };
}

function asTile(current: ReturnType<ReturnType<typeof createGramPair>["current"]>): GramPairTile {
  expect(current.kind).toBe("tile");
  if (current.kind !== "tile") {
    throw new Error("expected tile");
  }
  return current;
}

describe("createGramPair", () => {
  it("defaults to mode b with a matching-grid tile after load(a, b)", async () => {
    // Given: two sessions whose spectrogram grids match
    const pair = createGramPair({
      client: STUB_CLIENT,
      loadLevel: fakeLoadLevel(
        new Map([
          ["sess-a", LEVEL_A],
          ["sess-b", LEVEL_B],
        ]),
      ),
    });

    // When
    await pair.load("sess-a", "sess-b");

    // Then
    expect(pair.mode()).toBe("b");
    expect(pair.gridMatches()).toBe(true);
    expect(pair.paired()).toBe(true);
    expect(pair.current().kind).toBe("tile");
    pair.dispose();
  });

  it("slices B minus A in dB with a symmetric range when mode is delta", async () => {
    // Given: matching grids with mixed-sign cell deltas
    const pair = createGramPair({
      client: STUB_CLIENT,
      loadLevel: fakeLoadLevel(
        new Map([
          ["sess-a", LEVEL_A],
          ["sess-b", LEVEL_B],
        ]),
      ),
    });
    await pair.load("sess-a", "sess-b");

    // When
    pair.setMode("delta");

    // Then: values are B.powerDb − A.powerDb; color scale straddles zero
    const tile = asTile(pair.current());
    expect(Array.from(tile.tile.values)).toEqual(Array.from(DELTA_B_MINUS_A));
    expect(tile.minDb).toBeLessThan(0);
    expect(tile.maxDb).toBeGreaterThan(0);
    expect(tile.minDb).toBe(-tile.maxDb);
    pair.dispose();
  });

  it("refuses delta when timeS lengths differ and keeps the previous mode", async () => {
    // Given: B has a longer time axis than A
    const pair = createGramPair({
      client: STUB_CLIENT,
      loadLevel: fakeLoadLevel(
        new Map([
          ["sess-a", LEVEL_A],
          ["sess-b", LEVEL_B_MISMATCH],
        ]),
      ),
    });
    await pair.load("sess-a", "sess-b");
    const previous = pair.mode();

    // When
    pair.setMode("delta");

    // Then: grids do not match; delta is refused; current stays a tile (not delta)
    expect(pair.gridMatches()).toBe(false);
    expect(pair.mode()).toBe(previous);
    expect(pair.current().kind).toBe("tile");
    pair.dispose();
  });

  it("defaults to mode a when B is null", async () => {
    // Given: only session A
    const pair = createGramPair({
      client: STUB_CLIENT,
      loadLevel: fakeLoadLevel(new Map([["sess-a", LEVEL_A]])),
    });

    // When
    await pair.load("sess-a", null);

    // Then
    expect(pair.mode()).toBe("a");
    pair.dispose();
  });

  it("treats 404 absence of B as no comparison: mode a, not empty", async () => {
    // Given: у сессии Б нет артефакта анализа v2 (404)
    const pair = createGramPair({
      client: STUB_CLIENT,
      loadLevel: async (session) => {
        if (session === "sess-b") throw new ApiError("http", { status: 404 });
        return LEVEL_A;
      },
    });

    // When
    await pair.load("sess-a", "sess-b");

    // Then: сравнение невозможно, но база показана; дельта отклонена
    expect(pair.mode()).toBe("a");
    expect(pair.gridMatches()).toBe(false);
    expect(pair.paired()).toBe(false);
    expect(pair.empty()).toBe(false);
    expect(pair.current().kind).toBe("tile");
    pair.setMode("delta");
    expect(pair.mode()).toBe("a");
    pair.dispose();
  });

  it("both sessions absent → empty() without throwing", async () => {
    // Given: ни у одной сессии нет артефакта
    const pair = createGramPair({
      client: STUB_CLIENT,
      loadLevel: async () => {
        throw new ApiError("http", { status: 404 });
      },
    });

    // When
    await pair.load("sess-a", "sess-b");

    // Then
    expect(pair.empty()).toBe(true);
    expect(pair.current().kind).toBe("mismatch");
    pair.dispose();
  });

  it("non-absence errors still propagate", async () => {
    // Given: сетевой сбой — это не отсутствие артефакта
    const pair = createGramPair({
      client: STUB_CLIENT,
      loadLevel: async () => {
        throw new ApiError("network");
      },
    });

    // When / Then
    await expect(pair.load("sess-a", null)).rejects.toThrow(ApiError);
    pair.dispose();
  });
});
