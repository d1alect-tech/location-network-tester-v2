/** Загрузка состояния analysis-v2 для базы пары: указатель анализа, артефакты
 * панелей, скаляры W1 и вердикт THD-V. Только данные — DOM здесь не появляется
 * (оболочка в w1Chrome.ts, рендер в w1Render.ts). detail приходит из общего
 * загрузчика пары (B2): свой запрос метрик секция не делает. */

import type { LntApiClient } from "../../api/client";
import type { DetailLoader } from "./pairDetail";
import { getArtifactJson } from "./panels/fetch";
import type { PanelAbsence, PanelHostHandle } from "./panels/host";
import { thdVerdict } from "./thdVerdict";
import type { ThdVerdict, ThdWindow } from "./thdVerdict";
import { SCALAR, isPointer, needleOf } from "./w1Parse";
import type { Scalar } from "./w1Parse";

export type W1LoadDeps = {
  readonly client: LntApiClient;
  readonly detail: DetailLoader;
  readonly panels: PanelHostHandle;
  readonly sessionTypeOf: (session: string) => string;
};

export type W1SessionState = {
  /** false — анализа v2 для сессии нет: метрики и спектр v1 на месте. */
  readonly hasPointer: boolean;
  readonly scalars: readonly Scalar[];
  readonly verdict: ThdVerdict;
  readonly panelCount: number;
  readonly absent: readonly PanelAbsence[];
};

function pointerPath(session: string): string {
  return `/api/analysis/sessions/${encodeURIComponent(session)}/.lnt-default-analysis.json`;
}

export async function loadW1Session(
  deps: W1LoadDeps,
  session: string,
  signal: AbortSignal,
): Promise<W1SessionState> {
  const detail = await deps.detail(session, { signal });
  const pointerRaw = await getArtifactJson(deps.client, pointerPath(session), signal);
  const pointer = isPointer(pointerRaw) ? pointerRaw : null;
  const needle = needleOf(detail.analysis);
  const scalars: Scalar[] = [];
  let panelCount = 0;
  let absent: readonly PanelAbsence[] = [];
  let windows: readonly ThdWindow[] | null = null;
  let harmonicsFailed = false;
  if (pointer !== null) {
    const bound = await deps.panels.bind(
      {
        session,
        artifactKey: pointer.artifact_key,
        sessionType: deps.sessionTypeOf(session),
        cycles: needle.cycles,
        failures: [],
      },
      signal,
    );
    windows = bound.windows;
    panelCount = bound.panelCount;
    absent = bound.absent;
    if (windows !== null) {
      const mean = windows.reduce((sum, row) => sum + row.thd, 0) / windows.length;
      scalars.push({ key: "thd-v", label: SCALAR.thd, value: mean });
    }
    if (bound.notch !== null) {
      scalars.push({ key: "peak-notch-depth", label: SCALAR.notch, value: bound.notch });
    }
    if (bound.bursts !== null) {
      scalars.push({ key: "burst-count", label: SCALAR.burst, value: bound.bursts });
    }
    harmonicsFailed = windows === null;
  }
  if (needle.sigma !== null) {
    scalars.push({ key: "sigma-pk", label: SCALAR.sigma, value: needle.sigma });
  }
  return {
    hasPointer: pointer !== null,
    scalars,
    verdict: thdVerdict({
      windows,
      cyclesAnalyzed: needle.cycles,
      harmonicsFailed: pointer !== null && harmonicsFailed,
    }),
    panelCount,
    absent,
  };
}
