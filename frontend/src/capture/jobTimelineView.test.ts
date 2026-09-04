import { describe, expect, it, vi } from "vitest";
import type { JobSnapshot } from "../api/types-jobs";
import { applySnapshot, initialTimeline } from "./jobTimeline";
import { createJobTimelineView } from "./jobTimelineView";

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

describe("createJobTimelineView: онбординг при latest==null", () => {
  it("без задачи показывает русский онбординг вместо скрытой секции", () => {
    // Given
    const view = createJobTimelineView({ onCancel: vi.fn(), onRetry: vi.fn() });

    // When
    view.update(initialTimeline);

    // Then
    expect(view.root.hidden).toBe(false);
    expect(view.root.textContent).toContain("Задач пока нет");
  });

  it("онбординг скрывается при появлении снимка задачи", () => {
    // Given
    const view = createJobTimelineView({ onCancel: vi.fn(), onRetry: vi.fn() });
    document.body.replaceChildren(view.root);

    // When
    view.update(
      applySnapshot(initialTimeline, snap({ version: 2, status: "running", stage: "capturing" })),
    );

    // Then
    const onboarding = view.root.querySelector<HTMLElement>("[data-timeline-onboarding]");
    expect(onboarding?.hidden).toBe(true);
    expect(view.root.textContent).toContain("Задача выполняется");
  });
});
