/** Todo 42: кап тайла 524000 ячеек (failing-first), точные bbox-запросы,
 * гонка устаревших тайлов, отмена полёта и битые данные. */

import { describe, expect, it } from "vitest";
import type { CandidateEventPayload } from "../../api/types-analysis";
import {
  TILE_CELL_CAP,
  assertLevelWithinCap,
  createTileLoader,
  fullLevelRequest,
  sliceTile,
  tileRequestForRange,
} from "./spectrogramModel";
import type { SpectrogramLevel } from "./spectrogramModel";
import { summarizeWindow } from "./spectrogramSummary";
import { TileError } from "./tileError";

function makeLevel(timeBins: number, bands: number): SpectrogramLevel {
  return {
    timeS: new Float64Array(timeBins),
    frequencyHz: new Float64Array(bands),
    powerDb: new Float32Array(timeBins * bands),
    timeBins,
    bands,
  };
}

/** Уровень с известной сеткой: time = i, freq = j*10, value = i*1000 + j. */
function makeKnownLevel(): SpectrogramLevel {
  const level = makeLevel(8, 4);
  for (let t = 0; t < level.timeBins; t += 1) (level.timeS[t] as number) = t * 0.5;
  for (let f = 0; f < level.bands; f += 1) (level.frequencyHz[f] as number) = f * 10;
  for (let f = 0; f < level.bands; f += 1) {
    for (let t = 0; t < level.timeBins; t += 1) {
      level.powerDb[f * level.timeBins + t] = t * 1000 + f;
    }
  }
  return level;
}

describe("ограничение тайла спектрограммы (кап 524000 ячеек)", () => {
  it("обзор в пределах капа проходит проверку", () => {
    const bounded = makeLevel(2048, 255); // 522240 ≤ капа
    expect(() => assertLevelWithinCap(bounded)).not.toThrow();
  });

  it("запрос уровня больше капа отклоняется до рендера с русской причиной", () => {
    const oversized = makeLevel(2048, 1024); // хранимый обзор ~2 млн ячеек
    expect(2048 * 1024).toBeGreaterThan(TILE_CELL_CAP);
    try {
      assertLevelWithinCap(oversized);
      expect.unreachable("должна быть выброшена TileError");
    } catch (error) {
      expect(error).toBeInstanceOf(TileError);
      const tileError = error as TileError;
      expect(tileError.code).toBe("tile_too_large");
      expect(tileError.message).toContain("524000");
      expect(tileError.message).toContain("яч");
    }
  });

  it("brush даёт ТОЧНЫЙ запрос bbox по значениям окна", () => {
    const level = makeKnownLevel();
    const request = tileRequestForRange(level, 0.5, 1.6, 9, 25);
    // timeS = [0, .5, 1, 1.5, …]: ≥0.5 → t0=1; <1.6 → t1=4 (полуоткрытый)
    // frequency = [0,10,20,30]: ≥9 → f0=1; ≤25 → f1=3
    expect(request.window).toEqual({ t0: 1, t1: 4, f0: 1, f1: 3 });
    expect(request.cells).toBe(6);
    const tile = sliceTile(level, request);
    // Точное совпадение значений выбранной области с источником:
    expect(Array.from(tile.values)).toEqual([1001, 2001, 3001, 1002, 2002, 3002]);
    expect(Array.from(tile.times)).toEqual([0.5, 1, 1.5]);
    expect(Array.from(tile.freqs)).toEqual([10, 20]);
  });

  it("устаревший ответ тайла отбрасывается гонко-защитой (C→A→B)", async () => {
    interface Gate {
      promise: Promise<string>;
      resolve: (value: string) => void;
    }
    function gate(): Gate {
      let resolve!: (value: string) => void;
      const promise = new Promise<string>((res) => {
        resolve = res;
      });
      return { promise, resolve };
    }
    const gates = [gate(), gate(), gate()];
    let call = 0;
    const loader = createTileLoader<string>(() => {
      const current = gates[call];
      if (current === undefined) throw new Error("неожиданный вызов");
      return current.promise;
    });
    const runA = loader.load({ key: "a", window: { t0: 0, t1: 1, f0: 0, f1: 1 }, cells: 1 });
    call = 1;
    const runB = loader.load({ key: "b", window: { t0: 1, t1: 2, f0: 0, f1: 1 }, cells: 1 });
    call = 2;
    const runC = loader.load({ key: "c", window: { t0: 2, t1: 3, f0: 0, f1: 1 }, cells: 1 });
    gates[2]?.resolve("c-data");
    await runC;
    gates[0]?.resolve("stale-a");
    await runA;
    gates[1]?.resolve("stale-b");
    await runB;
    const state = loader.get();
    expect(state).toMatchObject({ kind: "ready", value: "c-data" });
    expect(state.kind === "ready" && state.request.key).toBe("c");
  });

  it("смена зума обрывает предыдущий полёт через AbortController", async () => {
    const signals: AbortSignal[] = [];
    const resolvers: Array<(value: string) => void> = [];
    const loader = createTileLoader<string>((_request, signal) => {
      signals.push(signal);
      return new Promise<string>((resolve) => {
        resolvers.push(resolve);
      });
    });
    const first = loader.load({ key: "first", window: { t0: 0, t1: 1, f0: 0, f1: 1 }, cells: 1 });
    const second = loader.load({ key: "second", window: { t0: 2, t1: 3, f0: 0, f1: 1 }, cells: 1 });
    expect(signals[0]?.aborted).toBe(true); // первый запрос оборван сменой зума
    expect(signals[1]?.aborted).toBe(false);
    resolvers[0]?.("stale-first"); // поздний ответ обрыва не влияет
    resolvers[1]?.("second-data");
    await Promise.all([first, second]);
    expect(loader.get()).toMatchObject({ kind: "ready", value: "second-data" });
    loader.dispose();
  });

  it("ошибка загрузки тайла нормализуется в состояние error с повтором", async () => {
    let fail = true;
    const loader = createTileLoader<string>(async () => {
      if (fail) throw new TypeError("fetch failed");
      return "ok";
    });
    await loader.load({ key: "k", window: { t0: 0, t1: 1, f0: 0, f1: 1 }, cells: 1 });
    const state = loader.get();
    expect(state.kind).toBe("error");
    fail = false;
    await loader.load({ key: "k", window: { t0: 0, t1: 1, f0: 0, f1: 1 }, cells: 1 });
    expect(loader.get().kind).toBe("ready");
  });

  it("сводка окна: диапазоны, статистика дБ, NaN и события в окне", () => {
    const level = makeKnownLevel();
    (level.powerDb[2] as number) = Number.NaN; // одна ячейка без покрытия
    const events: CandidateEventPayload[] = [
      eventAt(0.6),
      eventAt(3.9), // вне окна
    ];
    const summary = summarizeWindow(level, tileRequestForRange(level, 0, 2, 0, 40), events);
    expect(summary.cells).toBe(16);
    expect(summary.eventCount).toBe(1);
    expect(summary.nanShare).toBeCloseTo(1 / 16, 5);
    expect(summary.maxDb).toBe(3003);
    expect(summary.topBands[0]?.hz).toBe(30);
  });

  it("запрос пустого окна или сверхкапного уровня отклоняется типизированной ошибкой", () => {
    const level = makeKnownLevel();
    expect(() => tileRequestForRange(level, 100, 200, 0, 10)).toThrowError(TileError);
    try {
      fullLevelRequest(makeLevel(2048, 1024)); // ~2 млн ячеек целиком
      expect.unreachable();
    } catch (error) {
      expect((error as TileError).code).toBe("tile_too_large");
    }
  });

  it("полный уровень как стартовый тайл покрывает весь серверный уровень", () => {
    const level = makeLevel(256, 128); // движок бэкенда: 256×128 = 32768 ≤ капа
    const request = fullLevelRequest(level);
    expect(request.cells).toBe(32_768);
    expect(request.window).toEqual({ t0: 0, t1: 256, f0: 0, f1: 128 });
  });
});

function eventAt(peakTimeS: number): CandidateEventPayload {
  return {
    start_sample: 0,
    end_sample: 1,
    peak_sample: 0,
    start_time_s: peakTimeS - 0.01,
    end_time_s: peakTimeS + 0.01,
    peak_time_s: peakTimeS,
    peak_value_v: 0.5,
    polarity: "positive",
    dominant_band: null,
    excess_energy_v2_s: 1,
    snr: 12,
    qualification_status: "qualified",
    boundary: false,
    clipped: false,
  };
}
