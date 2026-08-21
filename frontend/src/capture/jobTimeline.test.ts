import { describe, expect, it } from "vitest";
import type { JobSnapshot } from "../api/types-jobs";
import {
  applySnapshot,
  canCancel,
  cancelAtBoundary,
  initialTimeline,
  needsRecoveryPrompt,
  requestCancel,
  seriesText,
} from "./jobTimeline";

/** Фабрика снимков задачи: канонический payload JobSnapshot.to_payload(). */
function snap(overrides: Partial<JobSnapshot>): JobSnapshot {
  return {
    schema_version: 1,
    version: 1,
    job_id: "job-1",
    kind: "capture",
    status: "queued",
    stage: "queued",
    series_index: null,
    series_total: null,
    written_sessions: [],
    result: null,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

describe("jobTimeline state machine", () => {
  it("cancel-at-boundary: running series → operator cancel → cancelling snapshot → cancelled", () => {
    let state = initialTimeline;
    state = applySnapshot(
      state,
      snap({ version: 2, status: "running", stage: "capturing", series_index: 2, series_total: 3 }),
    );
    expect(canCancel(state)).toBe(true);
    expect(cancelAtBoundary(state)).toBe(false);

    // Оператор запросил отмену — задача ещё работает до безопасной границы.
    state = requestCancel(state);
    expect(canCancel(state)).toBe(true);

    // Бэкенд подтвердил: отмена выполнится после текущей сессии серии.
    state = applySnapshot(state, snap({ version: 3, status: "cancelling" }));
    expect(cancelAtBoundary(state)).toBe(true);
    expect(canCancel(state)).toBe(false);

    // Терминальный снимок отмены закрывает задачу.
    state = applySnapshot(state, snap({ version: 4, status: "cancelled", stage: "capturing" }));
    expect(canCancel(state)).toBe(false);
    expect(cancelAtBoundary(state)).toBe(false);
  });

  it("ignores stale and out-of-order snapshots by version (dedup)", () => {
    let state = applySnapshot(initialTimeline, snap({ version: 5, status: "running" }));
    state = applySnapshot(state, snap({ version: 4, status: "queued" }));
    state = applySnapshot(state, snap({ version: 5, status: "running" }));
    expect(state.latest?.version).toBe(5);
    expect(state.history.map((item) => item.version)).toEqual([5]);
  });

  it("interrupted status requires the recovery prompt and allows retry", () => {
    const state = applySnapshot(
      initialTimeline,
      snap({ version: 7, status: "interrupted", stage: "capturing", error_code: "server_restart" }),
    );
    expect(needsRecoveryPrompt(state)).toBe(true);
    expect(state.latest?.status).toBe("interrupted");
  });

  it("failed status allows retry without recovery prompt", () => {
    const state = applySnapshot(
      initialTimeline,
      snap({ version: 3, status: "failed", error_code: "device_lost" }),
    );
    expect(needsRecoveryPrompt(state)).toBe(false);
    expect(canCancel(state)).toBe(false);
  });

  it("series text renders i/N only when the job is a series", () => {
    const single = applySnapshot(initialTimeline, snap({ version: 2, status: "running" }));
    expect(seriesText(single)).toBeNull();
    const series = applySnapshot(
      initialTimeline,
      snap({ version: 2, status: "running", series_index: 2, series_total: 5 }),
    );
    expect(seriesText(series)).toBe("Серия 2 из 5");
  });
});
