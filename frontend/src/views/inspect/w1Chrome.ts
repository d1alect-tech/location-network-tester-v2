/** Analysis-v2 хром (G7 «Disclosure-панели»): шапка секции + тело раскрытия.
 * Шапка видна всегда: заголовок, вердикт THD-V, сессия базы, CTA пересчёта.
 * B2: сессию задаёт ПАРА инспекции — своего select и своего вызова
 * catalogSessions здесь нет, detail берётся из общего загрузчика пары. */

import type { LntApiClient } from "../../api/client";
import { ApiError, isAbortError } from "../../api/errors";
import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { createExtendedRun } from "./extendedRun";
import type { DetailLoader } from "./pairDetail";
import { createPanelHost } from "./panels/host";
import type { PanelAbsence } from "./panels/host";
import { loadW1Session } from "./w1ChromeLoad";
import { parseFailures } from "./w1Parse";
import { renderAbsent, renderFailures, renderScalars, renderVerdict } from "./w1Render";
import "./w1Chrome.css";

export const MISSING_BANNER =
  "Расширенный анализ (ITIC, гармоники, APD…) для этой сессии не записан. Метрики и спектр v1 на месте.";
export const CTA_LABEL = "Пересчитать анализ (v2)";
export const NO_SESSION_SUMMARY = "сессия не выбрана";
export const SCALAR_SLOTS = 4;
export const SESSION_CAPTION = "Сессия инспекции · база";
export const SESSION_HINT = "Выбор в рейке каталога: первый клик — база, второй — сравнение.";
export const PANELS_TITLE = "Сворачиваемые панели";

export type W1ChromeOptions = {
  readonly client: LntApiClient;
  /** Общий загрузчик detail пары: один fetch на смену пары (B2). */
  readonly detail?: DetailLoader;
  /** Тип сессии из каталога инспекции — единственного источника выбора. */
  readonly sessionTypeOf?: (session: string) => string;
  /** Состояние in-flight задачи анализа: парбар блокирует контролы (job-busy). */
  readonly onJobBusy?: (busy: boolean) => void;
};

export interface W1ChromeHandle {
  /** Шапка секции: владелец DOM — хром, размещает её шелл analysis-v2. */
  readonly bar: HTMLElement;
  /** Тело раскрытия «Анализ сессии (метрики и панели)». */
  readonly root: HTMLElement;
  setSession(session: string | null): void;
  /** Сводка для свёрнутой шапки раскрытия: «панелей N · скаляров M/4». */
  onSummary(listener: (text: string) => void): void;
  destroy(): void;
}

function summaryText(panelCount: number, scalarCount: number): string {
  return `панелей ${String(panelCount)} · скаляров ${String(scalarCount)}/${String(SCALAR_SLOTS)}`;
}

export function createW1Chrome(options: W1ChromeOptions): W1ChromeHandle {
  const { client } = options;
  const loadDetail: DetailLoader =
    options.detail ?? ((name, detailOptions) => client.plots.detail(name, detailOptions));
  const sessionTypeOf = options.sessionTypeOf ?? (() => "");
  let loadAbort = new AbortController();
  let generation = 0;
  let session: string | null = null;
  let summary: ((text: string) => void) | null = null;

  const verdictHost = el("span", { className: "av2-verdict", attrs: { "data-role": "verdict" } });
  const sessionId = el("span", {
    className: "av2-session-id",
    text: "—",
    attrs: { "data-session-id": "", title: SESSION_HINT },
  });
  const sessionBox = el(
    "span",
    { className: "av2-session", attrs: { "data-role": "session-display" } },
    [el("span", { className: "av2-session-cap", text: SESSION_CAPTION }), sessionId],
  );
  const cta = el("button", {
    className: "lnt-btn lnt-btn-primary av2-cta",
    text: CTA_LABEL,
    attrs: { type: "button" },
  });
  cta.disabled = true;
  const bar = el("div", { className: "panel-hd av2-hd" }, [
    el("h2", { className: "panel-title", text: "Анализ v2" }),
    verdictHost,
    sessionBox,
    cta,
  ]);

  const banner = el("p", { className: "lnt-w1-banner", attrs: { role: "status" } });
  banner.hidden = true;
  const scalarsHost = el("div", { className: "band-scalars av2-scalars" });
  const scalarsBlock = el("section", { className: "av2-block" }, [
    el("h3", { className: "av2-block-title", text: "Скаляры W1" }),
    scalarsHost,
  ]);
  scalarsBlock.hidden = true;
  const extended = createExtendedRun({
    client: { ...client.analysis, ensureReady: (runOptions) => client.ensureReady(runOptions) },
  });
  const absentHost = el("ul", { className: "av2-absent", attrs: { "data-role": "absent-panels" } });
  absentHost.hidden = true;
  const panelsTitle = el("h3", {
    className: "av2-block-title",
    attrs: { "data-role": "panels-title" },
    text: `${PANELS_TITLE} · 0`,
  });
  const panelsHost = el("div", { className: "lnt-w1-panels" });
  const panels = createPanelHost({ client, root: panelsHost });
  const panelsBlock = el("section", { className: "av2-block" }, [
    panelsTitle,
    absentHost,
    panelsHost,
  ]);
  panelsBlock.hidden = true;
  const jobBar = el("div", { className: "lnt-w1-job-bar" });
  const failuresHost = el("ul", { className: "lnt-w1-failures" });
  const jobRail = el("div", { className: "lnt-w1-job-rail" }, [jobBar, failuresHost]);
  jobRail.hidden = true;
  const root = el("div", { className: "av2-body" }, [
    banner,
    scalarsBlock,
    extended.root,
    panelsBlock,
    jobRail,
  ]);

  function publish(panelCount: number, scalarCount: number): void {
    summary?.(session === null ? NO_SESSION_SUMMARY : summaryText(panelCount, scalarCount));
  }

  function paintSession(): void {
    sessionId.textContent = session ?? "—";
    sessionId.setAttribute("data-session-id", session ?? "");
    cta.disabled = session === null;
  }

  function resetBody(): void {
    banner.hidden = true;
    banner.textContent = "";
    clearElement(verdictHost);
    clearElement(scalarsHost);
    clearElement(absentHost);
    panels.clear();
    scalarsBlock.hidden = true;
    panelsBlock.hidden = true;
    absentHost.hidden = true;
    panelsTitle.textContent = `${PANELS_TITLE} · 0`;
  }

  function paintAbsent(rows: readonly PanelAbsence[]): void {
    renderAbsent(absentHost, rows);
    absentHost.hidden = rows.length === 0;
  }

  async function loadSession(current: string, gen: number): Promise<void> {
    const state = await loadW1Session(
      { client, detail: loadDetail, panels, sessionTypeOf },
      current,
      loadAbort.signal,
    );
    if (gen !== generation) return;
    banner.hidden = state.hasPointer;
    banner.textContent = state.hasPointer ? "" : MISSING_BANNER;
    panelsBlock.hidden = !state.hasPointer;
    panelsTitle.textContent = `${PANELS_TITLE} · ${String(state.panelCount)}`;
    paintAbsent(state.absent);
    renderVerdict(verdictHost, state.verdict);
    renderScalars(scalarsHost, state.scalars);
    scalarsBlock.hidden = state.scalars.length === 0;
    publish(state.panelCount, state.scalars.length);
  }

  async function rerun(): Promise<void> {
    const current = session;
    if (current === null) return;
    options.onJobBusy?.(true);
    try {
      await client.ensureReady();
      jobRail.hidden = false;
      jobBar.style.transform = "scaleX(0.5)";
      const snap = await client.jobs.start({ kind: "analyze", session_name: current });
      renderFailures(failuresHost, parseFailures(snap.result));
      jobBar.style.transform = snap.status === "succeeded" ? "scaleX(1)" : "scaleX(0.5)";
    } finally {
      options.onJobBusy?.(false);
    }
  }

  function report(error: unknown): void {
    if (isAbortError(error)) return;
    if (error instanceof ApiError) {
      announcePolite(error.message);
      return;
    }
    throw error;
  }

  cta.addEventListener("click", () => {
    void rerun().catch(report);
  });

  return {
    bar,
    root,
    setSession(next) {
      loadAbort.abort();
      loadAbort = new AbortController();
      generation += 1;
      session = next;
      paintSession();
      resetBody();
      extended.setSession(next);
      publish(0, 0);
      if (next === null) return;
      void loadSession(next, generation).catch(report);
    },
    onSummary(listener) {
      summary = listener;
      listener(session === null ? NO_SESSION_SUMMARY : summaryText(0, 0));
    },
    destroy() {
      generation += 1;
      loadAbort.abort();
      extended.destroy();
      bar.remove();
      root.remove();
    },
  };
}
