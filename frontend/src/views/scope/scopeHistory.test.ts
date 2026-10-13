/** Todo 11 RED: кольцевая история кадров осциллографа. Покрывается:
 * прокрутка назад (view(k) — k кадров назад, 0 — живой), вытеснение
 * старейшего при переполнении кольца, копирование данных кадра в
 * ограниченные Float32Array (мутация источника не видна), бюджет памяти
 * при 300+ кадрах подряд (стабильность) и прореживание кадров длиннее
 * потолка точки. */

import { describe, expect, it } from "vitest";
import type { LiveFramePayload } from "../../api/types-live";
import { HISTORY_FRAMES, HISTORY_POINT_CAP, ScopeHistory } from "./scopeHistory";

function frame(index: number, points: number): LiveFramePayload {
  const time_s: number[] = [];
  const voltage_v: number[] = [];
  for (let i = 0; i < points; i += 1) {
    time_s.push((i / points) * 0.001);
    voltage_v.push(index + (i % 10) / 100);
  }
  return {
    frame_index: index,
    triggered: true,
    emitted_at_s: index / 30,
    dropped_samples: 0,
    skipped_frames: 0,
    sample_rate_hz: 8_000_000,
    frame_samples: points * 16,
    decimated: true,
    calibration_used: false,
    ch1: { time_s, voltage_v, point_count: points },
    ch2: { time_s: [...time_s], voltage_v: voltage_v.map((v) => -v), point_count: points },
  };
}

describe("ScopeHistory: кольцо и прокрутка", () => {
  it("view(0) — новейший кадр, view(k) — кадр k назад; пустой буфер — null", () => {
    const history = new ScopeHistory();
    expect(history.view(0)).toBeNull();
    for (const i of [1, 2, 3, 4, 5]) history.push(frame(i, 8));

    expect(history.frameCount()).toBe(5);
    expect(history.view(0)?.frameIndex).toBe(5);
    expect(history.view(2)?.frameIndex).toBe(3);
    expect(history.view(4)?.frameIndex).toBe(1);
    expect(history.view(5)).toBeNull();
    expect(history.view(-1)).toBeNull();
  });

  it("кольцо вытесняет старейший: после N+1 кадров счётчик и порядок держат бюджет N", () => {
    const history = new ScopeHistory();
    for (let i = 0; i <= HISTORY_FRAMES; i += 1) history.push(frame(i, 8));

    expect(history.frameCount()).toBe(HISTORY_FRAMES);
    expect(history.view(0)?.frameIndex).toBe(HISTORY_FRAMES);
    // Старейший теперь кадр 1 (кадр 0 вытеснен).
    expect(history.view(HISTORY_FRAMES - 1)?.frameIndex).toBe(1);
    expect(history.view(HISTORY_FRAMES)).toBeNull();
  });

  it("хранит копию: мутация исходных массивов кадра не меняет буфер", () => {
    const history = new ScopeHistory();
    const incoming = frame(9, 8);
    history.push(incoming);
    (incoming.ch1.voltage_v[0] as number) = 1234;
    (incoming.ch1.time_s[0] as number) = 999;

    expect(history.view(0)?.ch1.voltageV[0]).toBeCloseTo(9, 6);
    expect(history.view(0)?.ch1.timeS[0]).toBe(0);
  });

  it("clear опустошает буфер", () => {
    const history = new ScopeHistory();
    history.push(frame(1, 8));
    history.clear();
    expect(history.frameCount()).toBe(0);
    expect(history.view(0)).toBeNull();
  });
});

describe("ScopeHistory: бюджет памяти", () => {
  it("300 кадров по потолку точек: кадров ≤ N, байты равны бюджету и не растут", () => {
    const history = new ScopeHistory();
    for (let i = 0; i < 300; i += 1) history.push(frame(i, HISTORY_POINT_CAP));

    expect(history.frameCount()).toBe(HISTORY_FRAMES);
    expect(history.usedBytes()).toBe(history.byteBudget());
    const steady = history.usedBytes();

    // When: ещё сотня кадров поверх трёхсот.
    for (let i = 300; i < 400; i += 1) history.push(frame(i, HISTORY_POINT_CAP));

    // Then: память стабильна — бюджет не превышен ни на байт.
    expect(history.usedBytes()).toBe(steady);
    expect(history.usedBytes()).toBeLessThanOrEqual(history.byteBudget());
    for (const series of [history.view(0)?.ch1, history.view(0)?.ch2]) {
      expect(series?.timeS.length).toBeLessThanOrEqual(HISTORY_POINT_CAP);
      expect(series?.voltageV.length).toBeLessThanOrEqual(HISTORY_POINT_CAP);
    }
  });

  it("кадр длиннее потолка прореживается шагом и не раздувает бюджет", () => {
    const history = new ScopeHistory();
    // 6000 точек → шаг 2 (ceil(6000/4000)), в буфер идёт каждая вторая.
    const incoming = frame(1, HISTORY_POINT_CAP + 2000);
    history.push(incoming);

    const stored = history.view(0)?.ch1;
    expect(stored?.timeS.length).toBeLessThanOrEqual(HISTORY_POINT_CAP);
    expect(stored?.voltageV.length).toBeLessThanOrEqual(HISTORY_POINT_CAP);
    // Шаг 2: сохраняется каждая вторая точка; Float32 округляет — близость.
    expect(stored?.timeS[1]).toBeCloseTo(incoming.ch1.time_s[2] as number, 10);
    expect(stored?.voltageV[1]).toBeCloseTo(incoming.ch1.voltage_v[2] as number, 6);
    expect(history.usedBytes()).toBeLessThanOrEqual(history.byteBudget());
  });

  it("короткие кадры не занимают весь бюджет", () => {
    const history = new ScopeHistory();
    for (let i = 0; i < 300; i += 1) history.push(frame(i, 8));
    expect(history.usedBytes()).toBeLessThan(history.byteBudget());
    expect(history.frameCount()).toBe(HISTORY_FRAMES);
  });
});
