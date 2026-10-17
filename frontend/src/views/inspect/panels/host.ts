/** Disclosure host: closed <details>, mount body only after open + artifact.
 * G7 «Disclosure-панели»: свёрнутая шапка несёт ключевое значение панели, а
 * отсутствующие панели объявлены чипами («нет артефакта» / «ветка не
 * посчитана» / «недостаточно циклов») вместо молчаливого исчезновения. */

import { clearElement, el } from "../../../components/primitives/dom";
import {
  REASON_NO_ARTIFACT,
  branchNotComputedReason,
  insufficientCyclesReason,
} from "../pairLoadOutcome";
import type { ThdWindow } from "../thdVerdict";
import { THD_MIN_CYCLES } from "../thdVerdict";
import { burstCount, parseWindows, peakNotch } from "../w1Parse";
import type { BranchFailure } from "../w1Parse";
import { APD_KIND, APD_LABEL, renderApd } from "./apd";
import { AUDIO_KIND, AUDIO_LABEL, renderAudio } from "./audio";
import { BURST_KIND, BURST_LABEL, renderBurst } from "./burst";
import { CM_DM_KIND, CM_DM_LABEL, renderCmDm } from "./cmDm";
import type { ArtifactClient } from "./fetch";
import { getArtifactJson, getArtifactText } from "./fetch";
import { HARMONICS_KIND, HARMONICS_LABEL, renderHarmonics } from "./harmonics";
import { ITIC_KIND, ITIC_LABEL, renderItic } from "./itic";
import { NOTCHING_KIND, NOTCHING_LABEL, renderNotching } from "./notching";
import { panelKeyText } from "./panelSummary";
import { TRENDS_KIND, TRENDS_LABEL, renderTrends } from "./trends";

export type PanelHostInput = {
  readonly session: string;
  readonly artifactKey: string;
  readonly sessionType: string;
  readonly cycles: number;
  readonly failures: readonly BranchFailure[];
};

export type PanelAbsenceTone = "absent" | "failed" | "withheld";

export type PanelAbsence = {
  readonly kind: string;
  readonly label: string;
  readonly reason: string;
  readonly tone: PanelAbsenceTone;
};

export type PanelHostScalars = {
  readonly windows: readonly ThdWindow[] | null;
  readonly notch: number | null;
  readonly bursts: number | null;
  /** Сколько раскрытий смонтировано (строка сводки в шапке секции). */
  readonly panelCount: number;
  /** Честное отсутствие: чипы вместо пустого места. */
  readonly absent: readonly PanelAbsence[];
};

export type PanelHostHandle = {
  readonly root: HTMLElement;
  clear(): void;
  bind(input: PanelHostInput, signal: AbortSignal): Promise<PanelHostScalars>;
};

// Фраза из единого словаря причин (задача 3, D2); реэкспорт сохранён для пинов.
export const ABSENT_ARTIFACT = REASON_NO_ARTIFACT;

export function harmonicsVisible(cycles: number, failures: readonly BranchFailure[]): boolean {
  if (cycles < THD_MIN_CYCLES) return false;
  return failures.every((row) => row.branch !== "harmonics");
}

function artifactBase(session: string, key: string): string {
  return `/api/analysis/sessions/${encodeURIComponent(session)}/artifacts/${encodeURIComponent(key)}`;
}

function mountPanel(
  kind: string,
  label: string,
  keyText: string | null,
  paint: (body: HTMLElement) => void,
): HTMLElement {
  const body = el("div", { className: "lnt-w1-panel-body" });
  const caption = el("span", { className: "lnt-w1-sum-label", text: label });
  const summary =
    keyText === null
      ? el("summary", {}, [caption])
      : el("summary", {}, [
          caption,
          el("span", {
            className: "lnt-w1-sum-value",
            text: keyText,
            attrs: { "data-panel-key": kind },
          }),
        ]);
  const root = el("details", { className: "lnt-w1-panel", attrs: { "data-panel": kind } }, [
    summary,
    body,
  ]);
  let painted = false;
  root.addEventListener("toggle", () => {
    if (!root.open || painted) return;
    painted = true;
    paint(body);
  });
  return root;
}

function failureOf(failures: readonly BranchFailure[], branch: string): BranchFailure | null {
  return failures.find((row) => row.branch === branch) ?? null;
}

function absentChip(kind: string, label: string, reason: string, tone: PanelAbsenceTone) {
  return { kind, label, reason, tone } satisfies PanelAbsence;
}

function failedChip(kind: string, label: string, failure: BranchFailure): PanelAbsence {
  return absentChip(kind, label, branchNotComputedReason(failure.message), "failed");
}

export function createPanelHost(options: {
  readonly client: ArtifactClient;
  readonly root: HTMLElement;
}): PanelHostHandle {
  const { client, root } = options;

  function clear(): void {
    clearElement(root);
  }

  async function bind(input: PanelHostInput, signal: AbortSignal): Promise<PanelHostScalars> {
    clear();
    const base = artifactBase(input.session, input.artifactKey);
    const jsonOf = (name: string) => getArtifactJson(client, `${base}/${name}`, signal);
    const [harmonics, notching, apd, burst, trends, audio] = await Promise.all([
      jsonOf("harmonics.json"),
      jsonOf("notching.json"),
      jsonOf("apd.json"),
      jsonOf("burst.json"),
      jsonOf("trends.json"),
      jsonOf("audio_panel.json"),
    ]);
    const itic = input.sessionType === "line_quality" ? await jsonOf("power_quality.json") : null;
    const cmDm =
      input.sessionType === "cm_dm"
        ? await getArtifactText(client, `${base}/cm_dm_spectrum.csv`, signal)
        : null;

    const nodes: HTMLElement[] = [];
    const absent: PanelAbsence[] = [];
    const consumed = new Set<string>();

    function offer(
      kind: string,
      label: string,
      payload: unknown | null,
      paint: (body: HTMLElement) => void,
    ): void {
      const failure = failureOf(input.failures, kind);
      if (failure !== null) consumed.add(failure.branch);
      if (kind === HARMONICS_KIND && payload !== null && failure === null) {
        if (harmonicsVisible(input.cycles, input.failures)) {
          nodes.push(mountPanel(kind, label, panelKeyText(kind, payload), paint));
          return;
        }
        absent.push(
          absentChip(
            kind,
            label,
            insufficientCyclesReason(input.cycles, THD_MIN_CYCLES),
            "withheld",
          ),
        );
        return;
      }
      if (payload === null || failure !== null) {
        absent.push(
          failure !== null
            ? failedChip(kind, label, failure)
            : absentChip(kind, label, ABSENT_ARTIFACT, "absent"),
        );
        return;
      }
      nodes.push(mountPanel(kind, label, panelKeyText(kind, payload), paint));
    }

    offer(HARMONICS_KIND, HARMONICS_LABEL, harmonics, (body) => renderHarmonics(body, harmonics));
    offer(NOTCHING_KIND, NOTCHING_LABEL, notching, (body) => renderNotching(body, notching));
    offer(APD_KIND, APD_LABEL, apd, (body) => renderApd(body, apd));
    offer(BURST_KIND, BURST_LABEL, burst, (body) => renderBurst(body, burst));
    offer(TRENDS_KIND, TRENDS_LABEL, trends, (body) => renderTrends(body, trends));
    offer(AUDIO_KIND, AUDIO_LABEL, audio, (body) => renderAudio(body, audio));
    if (input.sessionType === "line_quality") {
      offer(ITIC_KIND, ITIC_LABEL, itic, (body) => renderItic(body, itic));
    }
    if (input.sessionType === "cm_dm") {
      offer(CM_DM_KIND, CM_DM_LABEL, cmDm, (body) => renderCmDm(body, cmDm ?? ""));
    }

    // Провал ветки без своей панели (например psd) обязан быть назван, а не потерян.
    for (const row of input.failures) {
      if (consumed.has(row.branch)) continue;
      absent.push(failedChip(row.branch, row.branch, row));
    }

    root.append(...nodes);
    return {
      windows: parseWindows(harmonics),
      notch: peakNotch(notching),
      bursts: burstCount(burst),
      panelCount: nodes.length,
      absent,
    };
  }

  return { root, clear, bind };
}
