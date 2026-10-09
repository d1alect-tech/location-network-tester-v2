/** Восстановление активной задачи при монтировании и подключение SSE-потока.
 * Вынесено из captureView.ts дословно — сплит под потолок 250 чистых LOC
 * (tests/test_module_size.py). */

import type { LntApiClient } from "../api/client";
import type { JobSnapshot } from "../api/types-jobs";
import type { CaptureFlowState } from "./captureStartFlow";
import { applySnapshot, initialTimeline, needsRecoveryPrompt } from "./jobTimeline";
import type { TimelineViewHandle } from "./jobTimelineView";
import type { LivePanelHandle } from "./spectrogramLivePanel";
import { watchJobEvents } from "./sse";

export interface CaptureRecoveryDeps {
  readonly client: LntApiClient;
  readonly state: CaptureFlowState;
  readonly timeline: TimelineViewHandle;
  readonly liveGram: LivePanelHandle;
  applySnapshotToTimeline(snapshot: JobSnapshot): void;
  /** Bootstrap потока запуска: тот создаётся сразу следом, зовётся позже. */
  ensureBootstrap(): Promise<boolean>;
}

export interface CaptureRecoveryHandle {
  /** SSE задачи: снимки в хронологию, состояние связи, опрос при обрыве. */
  attachStream(snapshot: JobSnapshot): void;
  /** Один раз при монтировании: живую/прерванную задачу показать и довести. */
  recoverActiveJobOnMount(): Promise<void>;
}

export function createCaptureRecovery(deps: CaptureRecoveryDeps): CaptureRecoveryHandle {
  function attachStream(snapshot: JobSnapshot): void {
    deps.state.stream?.close();
    deps.state.stream = watchJobEvents(
      snapshot.job_id,
      {
        onSnapshot: deps.applySnapshotToTimeline,
        onConnection: (kind) => {
          deps.state.timelineState = { ...deps.state.timelineState, connection: kind };
          deps.timeline.update(deps.state.timelineState);
        },
      },
      { pollSnapshot: () => deps.client.jobs.get(snapshot.job_id) },
    );
  }

  async function recoverActiveJobOnMount(): Promise<void> {
    if (!(await deps.ensureBootstrap())) return;
    try {
      const page = await deps.client.jobs.list(1, 0);
      const latest = page.items[0];
      // Live-панель в idle показывает последнюю завершённую сессию post-hoc.
      if (latest !== undefined) deps.liveGram.onSnapshot(latest);
      if (
        latest === undefined ||
        (!needsRecoveryPrompt({ ...initialTimeline, latest }) && latest.status === "succeeded")
      ) {
        return;
      }
      deps.state.timelineState = applySnapshot(initialTimeline, latest);
      deps.timeline.update(deps.state.timelineState);
      const status = latest.status;
      if (status === "queued" || status === "running" || status === "cancelling") {
        attachStream(latest);
      }
    } catch {
      // Восстановление необязательно: без истории стартовая валидна.
    }
  }

  return { attachStream, recoverActiveJobOnMount };
}
