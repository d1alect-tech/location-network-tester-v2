/** W1 inspect chrome: one missing-artifact banner, THD verdict, four optional scalars. */

import { LntApiClient } from "../../api/client";
import { ApiError } from "../../api/errors";
import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { getArtifactJson } from "./panels/fetch";
import { createPanelHost } from "./panels/host";
import { thdVerdict } from "./thdVerdict";
import type { ThdVerdict, ThdWindow } from "./thdVerdict";
import { SCALAR, formatScalar, isPointer, needleOf, parseFailures } from "./w1Parse";
import type { BranchFailure, Scalar } from "./w1Parse";
import "./w1Chrome.css";

export const MISSING_BANNER =
  "Расширенный анализ (ITIC, гармоники, APD…) для этой сессии не записан. Метрики и спектр v1 на месте.";
export const CTA_LABEL = "Пересчитать анализ (v2)";
export const LEGACY_VERDICT = "Analysis v1 legacy (no THD limit check)";

export interface W1ChromeHandle {
  readonly root: HTMLElement;
  destroy(): void;
}

function assertNever(value: never): never {
  throw new Error(`unhandled verdict ${String(value)}`);
}

function renderVerdict(host: HTMLElement, verdict: ThdVerdict): void {
  clearElement(host);
  switch (verdict.kind) {
    case "pass":
      host.append(
        el("span", {
          className: "lnt-w1-badge lnt-w1-badge-ok",
          text: "THD-V pass",
          attrs: { "data-thd-verdict": "pass" },
        }),
      );
      return;
    case "fail":
      host.append(
        el("span", {
          className: "lnt-w1-badge lnt-w1-badge-fail",
          text: "THD-V fail",
          attrs: { "data-thd-verdict": "fail" },
        }),
      );
      return;
    case "legacy":
      host.append(
        el("span", {
          className: "lnt-w1-badge lnt-w1-badge-legacy",
          text: LEGACY_VERDICT,
          attrs: { "data-thd-verdict": "legacy" },
        }),
      );
      return;
    case "hidden":
      return;
    default:
      assertNever(verdict);
  }
}

function renderScalars(host: HTMLElement, scalars: readonly Scalar[]): void {
  clearElement(host);
  for (const scalar of scalars) {
    host.append(
      el("div", { attrs: { "data-scalar": scalar.key } }, [
        el("dt", { text: scalar.label }),
        el("dd", { text: formatScalar(scalar.value) }),
      ]),
    );
  }
}

function renderFailures(host: HTMLElement, failures: readonly BranchFailure[]): void {
  clearElement(host);
  for (const row of failures) {
    host.append(el("li", { text: `ветка ${row.branch} не посчитана: ${row.message}` }));
  }
}

export function createW1Chrome(options: { readonly client: LntApiClient }): W1ChromeHandle {
  const { client } = options;
  let loadAbort = new AbortController();

  const sessionSelect = el("select", {
    className: "lnt-select",
    attrs: { "aria-label": "Сессия инспекции" },
  });
  sessionSelect.append(el("option", { text: "Выберите сессию", attrs: { value: "" } }));
  const cta = el("button", {
    className: "lnt-btn lnt-btn-primary",
    text: CTA_LABEL,
    attrs: { type: "button" },
  });
  const banner = el("p", {
    className: "lnt-w1-banner",
    attrs: { role: "status" },
  });
  banner.hidden = true;
  const verdictHost = el("div", { className: "lnt-w1-verdict" });
  const scalarsHost = el("dl", { className: "lnt-w1-scalars" });
  const jobBar = el("div", { className: "lnt-w1-job-bar" });
  const failuresHost = el("ul", { className: "lnt-w1-failures" });
  const jobRail = el("div", { className: "lnt-w1-job-rail" }, [jobBar, failuresHost]);
  jobRail.hidden = true;
  const panelsHost = el("div", { className: "lnt-w1-panels" });
  const panels = createPanelHost({ client, root: panelsHost });
  const sessionTypes = new Map<string, string>();

  const root = el("section", { className: "lnt-w1-chrome", attrs: { "aria-label": "Анализ v2" } }, [
    el("div", { className: "lnt-w1-toolbar" }, [sessionSelect, cta]),
    banner,
    verdictHost,
    scalarsHost,
    panelsHost,
    jobRail,
  ]);

  async function loadCatalog(): Promise<void> {
    const page = await client.catalogSessions({ page_size: 200 });
    sessionTypes.clear();
    sessionSelect.replaceChildren(el("option", { text: "Выберите сессию", attrs: { value: "" } }));
    for (const item of page.items) {
      if (item.session_type !== null) sessionTypes.set(item.id, item.session_type);
      sessionSelect.append(el("option", { text: item.id, attrs: { value: item.id } }));
    }
  }

  async function loadSession(session: string): Promise<void> {
    loadAbort.abort();
    loadAbort = new AbortController();
    const { signal } = loadAbort;
    banner.hidden = true;
    banner.textContent = "";
    clearElement(verdictHost);
    clearElement(scalarsHost);
    panels.clear();
    if (session === "") return;
    const encoded = encodeURIComponent(session);
    const detail = await client.plots.detail(session, { signal });
    const pointerRaw = await getArtifactJson(
      client,
      `/api/analysis/sessions/${encoded}/.lnt-default-analysis.json`,
      signal,
    );
    const pointer = isPointer(pointerRaw) ? pointerRaw : null;
    const needle = needleOf(detail.analysis);
    const scalars: Scalar[] = [];
    let windows: readonly ThdWindow[] | null = null;
    let harmonicsFailed = false;
    if (pointer === null) {
      banner.hidden = false;
      banner.textContent = MISSING_BANNER;
    } else {
      const bound = await panels.bind(
        {
          session,
          artifactKey: pointer.artifact_key,
          sessionType: sessionTypes.get(session) ?? "",
          cycles: needle.cycles,
          failures: [],
        },
        signal,
      );
      windows = bound.windows;
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
    renderVerdict(
      verdictHost,
      thdVerdict({
        windows,
        cyclesAnalyzed: needle.cycles,
        harmonicsFailed: pointer !== null && harmonicsFailed,
      }),
    );
    renderScalars(scalarsHost, scalars);
  }

  async function rerun(): Promise<void> {
    const session = sessionSelect.value;
    if (session === "") return;
    await client.ensureReady();
    jobRail.hidden = false;
    jobBar.style.width = "50%";
    const snap = await client.jobs.start({ kind: "analyze", session_name: session });
    renderFailures(failuresHost, parseFailures(snap.result));
    jobBar.style.width = snap.status === "succeeded" ? "100%" : "50%";
  }

  sessionSelect.addEventListener("change", () => {
    void loadSession(sessionSelect.value).catch((error: unknown) => {
      if (error instanceof ApiError) {
        announcePolite(error.message);
        return;
      }
      throw error;
    });
  });
  cta.addEventListener("click", () => {
    void rerun().catch((error: unknown) => {
      if (error instanceof ApiError) {
        announcePolite(error.message);
        return;
      }
      throw error;
    });
  });
  void loadCatalog().catch((error: unknown) => {
    if (error instanceof ApiError) {
      announcePolite(error.message);
      return;
    }
    throw error;
  });

  return {
    root,
    destroy: () => {
      loadAbort.abort();
    },
  };
}

export function mountInspectW1Chrome(host: HTMLElement): W1ChromeHandle {
  const chrome = createW1Chrome({ client: new LntApiClient() });
  host.append(chrome.root);
  return chrome;
}
