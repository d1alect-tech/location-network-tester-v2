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
import { REASON_NO_ARTIFACT, reasonFromError } from "./pairLoadOutcome";
import { createPanelHost } from "./panels/host";
import type { PanelAbsence } from "./panels/host";
import { loadW1Session } from "./w1ChromeLoad";
import type { W1JobWatchOptions } from "./w1JobProgress";
import { createW1JobRail } from "./w1JobRail";
import { renderAbsent, renderScalars, renderVerdict } from "./w1Render";
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
  /** Успешная задача анализа: данные пары перезабираются хостом тем же
   * конвейером, что и смена пары (literal setPair на неизменной паре —
   * no-op по контракту задачи 5, поэтому отдельный канал). */
  readonly onJobReload?: () => void;
  /** Внедрение планировщиков SSE-ожидания: юнит-тесты без EventSource. */
  readonly jobWatch?: W1JobWatchOptions;
};

export interface W1ChromeHandle {
  /** Шапка секции: владелец DOM — хром, размещает её шелл analysis-v2. */
  readonly bar: HTMLElement;
  /** Тело раскрытия «Анализ сессии (метрики и панели)». */
  readonly root: HTMLElement;
  setSession(session: string | null): void;
  /** Сводка для свёрнутой шапки раскрытия: «панелей N · скаляров M/4». */
  onSummary(listener: (text: string) => void): void;
  /** Причина отсутствия анализа v2 (G1/Q3 = A): сиблинг счётчика сводки,
   * null — анализа нет причина не нужна. Канал onSummary отвергнут вердиктом. */
  onAbsenceReason(listener: (reason: string | null) => void): void;
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
  let absence: ((reason: string | null) => void) | null = null;
  let absenceReason: string | null = null;

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
  const jobRail = createW1JobRail();
  const root = el("div", { className: "av2-body" }, [
    banner,
    scalarsBlock,
    extended.root,
    panelsBlock,
    jobRail.root,
  ]);

  function publish(panelCount: number, scalarCount: number): void {
    summary?.(session === null ? NO_SESSION_SUMMARY : summaryText(panelCount, scalarCount));
  }

  /** Провод словаря задач 3 на NO-POINTER пути: причина уходит в свёрнутую
   * шапку (сиблинг счётчика), не трогая пиннутый текст сводки. */
  function publishAbsence(reason: string | null): void {
    absenceReason = reason;
    absence?.(reason);
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
    publishAbsence(state.hasPointer ? null : REASON_NO_ARTIFACT);
    panelsBlock.hidden = !state.hasPointer;
    panelsTitle.textContent = `${PANELS_TITLE} · ${String(state.panelCount)}`;
    paintAbsent(state.absent);
    renderVerdict(verdictHost, state.verdict);
    renderScalars(scalarsHost, state.scalars);
    scalarsBlock.hidden = state.scalars.length === 0;
    publish(state.panelCount, state.scalars.length);
  }

  /** Задача 8 (D1e/R5): rerun честен — старт задачи, живой SSE-прогресс из
   * реальных стадий (сфабрикованный scaleX-хардкод удалён), терминал с
   * исходом; успех перезабирает данные пары (onJobReload), недоступность
   * задачи — честный failed(reason) из словаря задач 3, контролы не виснут. */
  async function rerun(): Promise<void> {
    const current = session;
    if (current === null) return;
    options.onJobBusy?.(true);
    try {
      await client.ensureReady();
      jobRail.show();
      const started = await client.jobs.start({ kind: "analyze", session_name: current });
      const final = await jobRail.awaitTerminal(
        started,
        () => client.jobs.get(started.job_id),
        options.jobWatch,
      );
      if (final.status === "succeeded") options.onJobReload?.();
    } catch (error) {
      if (isAbortError(error)) return;
      jobRail.paintFailure(reasonFromError(error));
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
      publishAbsence(null);
      if (next === null) return;
      void loadSession(next, generation).catch(report);
    },
    onSummary(listener) {
      summary = listener;
      listener(session === null ? NO_SESSION_SUMMARY : summaryText(0, 0));
    },
    onAbsenceReason(listener) {
      absence = listener;
      listener(absenceReason);
    },
    destroy() {
      generation += 1;
      loadAbort.abort();
      jobRail.close();
      extended.destroy();
      bar.remove();
      root.remove();
    },
  };
}
