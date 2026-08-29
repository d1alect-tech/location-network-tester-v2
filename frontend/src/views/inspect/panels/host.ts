/** Disclosure host: closed <details>, mount body only after open + artifact. */

import { clearElement, el } from "../../../components/primitives/dom";
import type { ThdWindow } from "../thdVerdict";
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
import { TRENDS_KIND, TRENDS_LABEL, renderTrends } from "./trends";

export type PanelHostInput = {
  readonly session: string;
  readonly artifactKey: string;
  readonly sessionType: string;
  readonly cycles: number;
  readonly failures: readonly BranchFailure[];
};

export type PanelHostScalars = {
  readonly windows: readonly ThdWindow[] | null;
  readonly notch: number | null;
  readonly bursts: number | null;
};

export type PanelHostHandle = {
  readonly root: HTMLElement;
  clear(): void;
  bind(input: PanelHostInput, signal: AbortSignal): Promise<PanelHostScalars>;
};

export function harmonicsVisible(cycles: number, failures: readonly BranchFailure[]): boolean {
  if (cycles < 100) return false;
  return failures.every((row) => row.branch !== "harmonics");
}

function artifactBase(session: string, key: string): string {
  return `/api/analysis/sessions/${encodeURIComponent(session)}/artifacts/${encodeURIComponent(key)}`;
}

function mountPanel(kind: string, label: string, paint: (body: HTMLElement) => void): HTMLElement {
  const body = el("div", { className: "lnt-w1-panel-body" });
  const root = el("details", { className: "lnt-w1-panel", attrs: { "data-panel": kind } }, [
    el("summary", { text: label }),
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

function failedBranch(failures: readonly BranchFailure[], branch: string): boolean {
  return failures.some((row) => row.branch === branch);
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
    const showHarmonics = harmonics !== null && harmonicsVisible(input.cycles, input.failures);
    if (showHarmonics) {
      nodes.push(
        mountPanel(HARMONICS_KIND, HARMONICS_LABEL, (body) => renderHarmonics(body, harmonics)),
      );
    }
    if (notching !== null && !failedBranch(input.failures, "notching")) {
      nodes.push(
        mountPanel(NOTCHING_KIND, NOTCHING_LABEL, (body) => renderNotching(body, notching)),
      );
    }
    if (apd !== null && !failedBranch(input.failures, "apd")) {
      nodes.push(mountPanel(APD_KIND, APD_LABEL, (body) => renderApd(body, apd)));
    }
    if (burst !== null && !failedBranch(input.failures, "burst")) {
      nodes.push(mountPanel(BURST_KIND, BURST_LABEL, (body) => renderBurst(body, burst)));
    }
    if (trends !== null && !failedBranch(input.failures, "trends")) {
      nodes.push(mountPanel(TRENDS_KIND, TRENDS_LABEL, (body) => renderTrends(body, trends)));
    }
    if (audio !== null && !failedBranch(input.failures, "audio")) {
      nodes.push(mountPanel(AUDIO_KIND, AUDIO_LABEL, (body) => renderAudio(body, audio)));
    }
    if (itic !== null) {
      nodes.push(mountPanel(ITIC_KIND, ITIC_LABEL, (body) => renderItic(body, itic)));
    }
    if (cmDm !== null) {
      nodes.push(mountPanel(CM_DM_KIND, CM_DM_LABEL, (body) => renderCmDm(body, cmDm)));
    }
    for (const row of input.failures) {
      nodes.push(
        mountPanel("branch-failure", row.branch, (body) => {
          body.append(el("p", { className: "lnt-w1-panel-note", text: row.branch }));
        }),
      );
    }
    root.append(...nodes);
    return {
      windows: parseWindows(harmonics),
      notch: peakNotch(notching),
      bursts: burstCount(burst),
    };
  }

  return { root, clear, bind };
}
