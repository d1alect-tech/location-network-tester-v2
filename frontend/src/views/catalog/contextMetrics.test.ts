/** Метрики сводки: только то, что реально лежит в манифесте/анализе.
 * Нечисловое и отсутствующее — null с причиной, ноль не подставляется. */

import { describe, expect, it } from "vitest";
import type { SessionDetailPayload } from "../../api/types-plots";
import { EMPTY_METRICS, readSessionMetrics } from "./contextMetrics";

function detail(
  manifest: Record<string, unknown>,
  lineQuality: Record<string, unknown> | null,
): SessionDetailPayload {
  return {
    name: "s",
    manifest,
    analysis: lineQuality === null ? null : { line_quality: lineQuality },
    spectrum_available: false,
    waveform_available: false,
    ch2_available: false,
  };
}

describe("readSessionMetrics", () => {
  it("без деталей сессии все метрики недоступны с причинами", () => {
    const metrics = readSessionMetrics(null);
    expect(metrics).toEqual(EMPTY_METRICS);
    expect(metrics.durationReason).not.toBeNull();
    expect(metrics.mainsReason).not.toBeNull();
    expect(metrics.thdReason).not.toBeNull();
  });

  it("читает длительность из манифеста, частоту и THD из анализа", () => {
    const metrics = readSessionMetrics(
      detail(
        { duration_s: 12.4 },
        { fundamental_hz: 50.02, thd_ratio: 0.037, cycles_analyzed: 620 },
      ),
    );
    expect(metrics.durationS).toBe(12.4);
    expect(metrics.mainsHz).toBe(50.02);
    expect(metrics.thdRatio).toBe(0.037);
    expect(metrics.cycles).toBe(620);
    expect(metrics.thdReason).toBeNull();
  });

  it("частота сети берётся из манифеста, когда анализ её не собрал", () => {
    const metrics = readSessionMetrics(detail({ line_frequency_hz: 50 }, null));
    expect(metrics.mainsHz).toBe(50);
    expect(metrics.thdRatio).toBeNull();
  });

  it("NaN и Infinity не проходят как значения", () => {
    const metrics = readSessionMetrics(
      detail(
        { duration_s: Number.NaN },
        { thd_ratio: Number.POSITIVE_INFINITY, cycles_analyzed: 5 },
      ),
    );
    expect(metrics.durationS).toBeNull();
    expect(metrics.thdRatio).toBeNull();
    expect(metrics.cycles).toBe(5);
  });
});
