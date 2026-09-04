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

  it("онбординг не показывается, если задача уже запускалась", () => {
    // Given
    const view = createJobTimelineView({ onCancel: vi.fn(), onRetry: vi.fn() });
    const withHistory = { ...initialTimeline, history: [snap({ status: "cancelled" })] };

    // When
    view.update(withHistory);

    // Then
    const onboarding = view.root.querySelector<HTMLElement>("[data-timeline-onboarding]");
    expect(onboarding?.hidden).toBe(true);
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

describe("createJobTimelineView: пояснение границы отмены", () => {
  function runningView() {
    const onCancel = vi.fn();
    const view = createJobTimelineView({ onCancel, onRetry: vi.fn() });
    document.body.replaceChildren(view.root);
    let state = applySnapshot(
      initialTimeline,
      snap({ version: 2, status: "running", stage: "capturing" }),
    );
    view.update(state);
    const note = view.root.querySelector<HTMLElement>("[data-timeline-cancel-note]");
    return {
      onCancel,
      view,
      note,
      advance: (overrides: Partial<JobSnapshot>) => {
        state = applySnapshot(state, snap(overrides));
        view.update(state);
      },
    };
  }

  function confirmCancel(view: ReturnType<typeof createJobTimelineView>) {
    const cancelButton = Array.from(view.root.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Отменить после текущей сессии"),
    );
    cancelButton?.click();
    const confirm = Array.from(document.body.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Подтвердить отмену"),
    );
    confirm?.click();
  }

  it("показывает пояснение при статусе cancelling", () => {
    // Given
    const { view, note, advance } = runningView();

    // When
    advance({ version: 3, status: "cancelling" });

    // Then
    expect(note?.hidden).toBe(false);
    expect(view.root.textContent).toContain("Отмена запланирована после текущей сессии");
  });

  it("пояснение остаётся после подтверждённой отмены рядом со статусом", () => {
    // Given
    const { onCancel, view, note, advance } = runningView();
    confirmCancel(view);
    expect(onCancel).toHaveBeenCalledWith("job-1");

    // When
    advance({ version: 4, status: "cancelled" });

    // Then
    expect(note?.hidden).toBe(false);
    expect(view.root.textContent).toContain("Отмена запланирована после текущей сессии");
    expect(view.root.textContent).toContain("Задача отменена");
  });

  it("не показывает пояснение для cancelled-задачи без подтверждения оператора", () => {
    // Given
    const { view, note, advance } = runningView();

    // When: cancelled без подтверждения (восстановление с сервера).
    advance({ version: 3, status: "cancelled" });

    // Then
    expect(note?.hidden).toBe(true);
    expect(view.root.textContent).toContain("Задача отменена");
  });

  it("сбрасывает пояснение при старте новой задачи после повтора", () => {
    // Given
    const { view, note, advance } = runningView();
    confirmCancel(view);
    advance({ version: 4, status: "cancelled" });
    expect(note?.hidden).toBe(false);

    // When: повтор сбрасывает состояние и запускает новую задачу (как startJob).
    view.update(
      applySnapshot(
        initialTimeline,
        snap({ version: 1, status: "running", stage: "capturing", job_id: "job-2" }),
      ),
    );

    // Then
    expect(note?.hidden).toBe(true);
  });
});
