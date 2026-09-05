import { describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import {
  POLL_INTERVAL_MS,
  POLL_LIMIT,
  pollResult,
  runAnalysis,
  runComparability,
} from "./comparisonJobs";
import type { ExperimentDetail } from "./experimentsStore";

type JobClient = Pick<LntApiClient, "research" | "statistics">;

function stubClient(overrides: { research?: unknown; statistics?: unknown } = {}): JobClient {
  return { research: {}, statistics: {}, ...overrides } as unknown as JobClient;
}

function stubDetail(kind = "ab"): ExperimentDetail {
  return {
    experiment: { experiment_id: "exp.demo", protocol: { kind } },
  } as unknown as ExperimentDetail;
}

describe("comparisonJobs leaf (C3c: задачи сравнения)", () => {
  it("keeps poll timings frozen (verbatim move)", () => {
    expect(POLL_INTERVAL_MS).toBe(300);
    expect(POLL_LIMIT).toBe(40);
  });

  it("pollResult returns the envelope once result_kind appears", async () => {
    const envelope = { result_kind: "descriptive", result: {}, metadata: {} };
    const result = vi
      .fn()
      .mockResolvedValueOnce({ status: "pending" })
      .mockResolvedValueOnce(envelope);
    const client = stubClient({ statistics: { result } });
    const out = await pollResult(client, "job-1", new AbortController().signal);
    expect(out).toBe(envelope);
    expect(result).toHaveBeenCalledTimes(2);
  });

  it("pollResult throws the frozen timeout message after the limit", async () => {
    vi.useFakeTimers();
    try {
      const result = vi.fn().mockResolvedValue({ status: "pending" });
      const client = stubClient({ statistics: { result } });
      const pending = pollResult(client, "job-1", new AbortController().signal);
      const assertion = expect(pending).rejects.toThrow(
        "превышено время ожидания результата статистики",
      );
      for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
        await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
      }
      await assertion;
      expect(result).toHaveBeenCalledTimes(POLL_LIMIT);
    } finally {
      vi.useRealTimers();
    }
  });

  it("comparable gate blocks analysis without touching the network", async () => {
    const showBanner = vi.fn();
    const submit = vi.fn();
    const client = stubClient({ statistics: { submit } });
    await runAnalysis({
      client,
      detail: stubDetail(),
      lastReport: { comparable: false, findings: [] },
      featureKey: "band_mid_total",
      units: "В²/Гц",
      seed: 43,
      signal: new AbortController().signal,
      buildStatisticsRequest: vi.fn(),
      showBanner,
      renderEnvelope: vi.fn(),
    });
    expect(showBanner).toHaveBeenCalledWith(
      "Расчёт заблокирован: сравнимость не подтверждена.",
      "warn",
    );
    expect(submit).not.toHaveBeenCalled();
  });

  it("runComparability without context shows the banner instead of a silent return", async () => {
    const showBanner = vi.fn();
    const comparabilityCheck = vi.fn();
    const client = stubClient({ research: { comparabilityCheck } });
    await runComparability({
      client,
      detail: null,
      signal: new AbortController().signal,
      groupedInProtocolOrder: vi.fn(),
      onReport: vi.fn(),
      showBanner,
      renderReport: vi.fn(),
    });
    expect(showBanner).toHaveBeenCalledWith(
      "Нет данных эксперимента для проверки сравнимости. Сначала выберите эксперимент.",
      "warn",
    );
    expect(comparabilityCheck).not.toHaveBeenCalled();
  });
});
