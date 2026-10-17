import { describe, expect, it, vi } from "vitest";
import type { JobSnapshot } from "../api/types-jobs";
import { parseHash } from "../state/routeState";
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

describe("createJobTimelineView: записанная сессия открывается в инспекции", () => {
  const SESSION_ID = "2026-09-05T10-00-00_rc_measurement";

  function writtenView(names: readonly string[]) {
    const view = createJobTimelineView({ onCancel: vi.fn(), onRetry: vi.fn() });
    document.body.replaceChildren(view.root);
    view.update(
      applySnapshot(
        initialTimeline,
        snap({ version: 2, status: "succeeded", written_sessions: [...names] }),
      ),
    );
    return view;
  }

  it("элемент .capture-written-item несёт ссылку на маршрут инспекции", () => {
    // Given / When
    const view = writtenView([SESSION_ID]);

    // Then: класс и текст элемента сохранены (пины capture.spec.ts:94,215)
    const item = view.root.querySelector(".capture-written-item");
    expect(item?.textContent).toBe(SESSION_ID);
    const link = item?.querySelector("a");
    expect(link).not.toBeNull();
    // href разбирается каноническим парсером маршрутов продукта: тот же
    // переход, который выполняет клик в браузере.
    expect(parseHash(link?.getAttribute("href") ?? "")).toEqual({
      route: "inspect",
      params: { a: SESSION_ID },
    });
  });

  it("клик по записанной сессии доходит до ссылки и не отменяется", () => {
    // Given
    const view = writtenView([SESSION_ID]);
    const link = view.root.querySelector<HTMLAnchorElement>(".capture-written-item a");
    const seen: { href: string | null; prevented: boolean }[] = [];
    link?.addEventListener("click", (event) => {
      seen.push({ href: link?.getAttribute("href") ?? null, prevented: event.defaultPrevented });
    });

    // When
    link?.click();

    // Then: jsdom не выполняет фрагмент-переход, поэтому саму навигацию
    // проверяет e2e captureWrittenSession.spec.ts в настоящем браузере; здесь —
    // что клик попадает в ссылку с каноническим href и ничем не отменён.
    expect(seen).toEqual([{ href: `#/inspect?a=${SESSION_ID}`, prevented: false }]);
  });

  it("F-2: запись серии до её анализа остаётся текстом без ссылки", () => {
    // Given: рабочий записал сессию позиции 1 и ушёл в analyzing — артефактов
    // анализа ещё нет, инспект показал бы «н/д» навсегда (f3 F-2).
    const view = createJobTimelineView({ onCancel: vi.fn(), onRetry: vi.fn() });
    document.body.replaceChildren(view.root);

    // When
    view.update(
      applySnapshot(
        initialTimeline,
        snap({
          version: 2,
          status: "running",
          stage: "analyzing",
          series_index: 1,
          series_total: 2,
          written_sessions: [SESSION_ID],
        }),
      ),
    );

    // Then: элемент и текст на месте (пин .capture-written-item), ссылки нет.
    const item = view.root.querySelector(".capture-written-item");
    expect(item?.textContent).toBe(SESSION_ID);
    expect(item?.querySelector("a")).toBeNull();
  });

  it("F-2: ссылка появляется, когда задача ушла к следующей позиции серии", () => {
    // Given: позиция 1 записана и проанализирована, идёт позиция 2.
    const view = createJobTimelineView({ onCancel: vi.fn(), onRetry: vi.fn() });
    document.body.replaceChildren(view.root);

    // When
    view.update(
      applySnapshot(
        initialTimeline,
        snap({
          version: 3,
          status: "running",
          stage: "simulating",
          series_index: 2,
          series_total: 2,
          written_sessions: [SESSION_ID],
        }),
      ),
    );

    // Then
    const link = view.root.querySelector<HTMLAnchorElement>(".capture-written-item a");
    expect(link?.getAttribute("href")).toBe(`#/inspect?a=${SESSION_ID}`);
  });

  it("F-2: interrupted до анализа оставляет запись текстом", () => {
    // Given: сервер перезапустился посреди анализа позиции 1 (пин capture.spec).
    const view = createJobTimelineView({ onCancel: vi.fn(), onRetry: vi.fn() });
    document.body.replaceChildren(view.root);

    // When
    view.update(
      applySnapshot(
        initialTimeline,
        snap({
          version: 9,
          status: "interrupted",
          stage: "capturing",
          series_index: 1,
          series_total: 3,
          written_sessions: [SESSION_ID],
        }),
      ),
    );

    // Then
    const item = view.root.querySelector(".capture-written-item");
    expect(item?.textContent).toBe(SESSION_ID);
    expect(item?.querySelector("a")).toBeNull();
  });

  it("без идентификатора сессии элемент остаётся текстом без ссылки", () => {
    // Given / When
    const view = writtenView(["   "]);

    // Then
    const item = view.root.querySelector(".capture-written-item");
    expect(item?.textContent).toBe("   ");
    expect(item?.querySelector("a")).toBeNull();
  });
});
