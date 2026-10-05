/** Расширенный прогон characterization-v1: одна кнопка + скачивание + сводка.
 * Без графиков и управления каталогом рецептов: recipe_id захардкожен через
 * список рецептов по имени characterization-v1. Сводка рисуется карточками
 * (`familyCards.ts`), скачивание с видимой строкой ошибки и повтором живёт в
 * `extendedDownloads.ts`. */

import type { AnalysisRunSnapshot } from "../../api/types-analysis";
import { clearElement, el } from "../../components/primitives/dom";
import { asReasonCodes, readFamilyDetail } from "./characterizationFamily";
import type { FamilySummary } from "./characterizationFamily";
import { BUNDLE_FILES, createExtendedDownloads } from "./extendedDownloads";
import type { BundleFileName } from "./extendedDownloads";
import { renderFamilyCards } from "./familyCards";
import "./extendedRun.css";

/** Типы полей семейства живут в characterizationFamily.ts; здесь — только реэкспорт. */
export type * from "./characterizationFamily";
export { BUNDLE_FILES };
export type { BundleFileName };

export const EXTENDED_RUN_BUTTON = "Запустить расширенный анализ";
export const EXTENDED_RUN_TITLE = "Расширенный анализ (characterization-v1)";
export const EXTENDED_RECIPE_NAME = "characterization-v1";

export type ExtendedRunClient = {
  /** Idempotent nonce bootstrap: расширенный прогон мутирует, нужен launch-nonce. */
  readonly ensureReady: (options?: { readonly signal?: AbortSignal }) => Promise<void>;
  readonly recipes: (options?: { readonly signal?: AbortSignal }) => Promise<
    readonly { readonly recipe_id: string; readonly name: string }[]
  >;
  readonly runAnalysis: (
    request: { readonly session: string; readonly recipe_id: string },
    options?: { readonly signal?: AbortSignal },
  ) => Promise<AnalysisRunSnapshot>;
  readonly runStatus: (
    jobId: string,
    options?: { readonly signal?: AbortSignal },
  ) => Promise<AnalysisRunSnapshot>;
  readonly artifactBytes: (
    session: string,
    key: string,
    filename: string,
    options?: { readonly signal?: AbortSignal },
  ) => Promise<ArrayBuffer>;
};

export type CharacterizationSummary = {
  readonly f1Hz: number | null;
  readonly families: readonly FamilySummary[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asFinite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Разбирает characterization.json: f1 из сводки F01 + статусы и поля семейств. */
export function parseCharacterizationSummary(payload: unknown): CharacterizationSummary | null {
  if (!isRecord(payload) || !Array.isArray(payload.families)) return null;
  const families: FamilySummary[] = [];
  for (const item of payload.families) {
    if (!isRecord(item) || typeof item.family_id !== "string" || typeof item.status !== "string") {
      return null;
    }
    families.push({
      id: item.family_id,
      status: item.status,
      reasonCodes: asReasonCodes(item.reason_codes),
      ...readFamilyDetail(item),
    });
  }
  if (families.length !== 18) return null;
  const first = payload.families[0];
  if (!isRecord(first) || !Array.isArray(first.comparison_summary)) return null;
  let f1Hz: number | null = null;
  for (const row of first.comparison_summary) {
    if (!isRecord(row) || row.name !== "f1_hz") continue;
    f1Hz = asFinite(row.value);
  }
  return { f1Hz, families };
}

function decodeJson(buffer: ArrayBuffer): unknown {
  return JSON.parse(new TextDecoder().decode(new Uint8Array(buffer)) as string) as unknown;
}

export type ExtendedRunHandle = {
  readonly root: HTMLElement;
  setSession(session: string | null): void;
  destroy(): void;
};

export function createExtendedRun(options: {
  readonly client: ExtendedRunClient;
}): ExtendedRunHandle {
  const { client } = options;
  let session: string | null = null;
  let runAbort = new AbortController();
  let busy = false;

  const status = el("p", {
    className: "lnt-w1-panel-note",
    attrs: { role: "status" },
  });
  const button = el("button", {
    className: "lnt-btn lnt-btn-primary",
    text: EXTENDED_RUN_BUTTON,
    attrs: { type: "button" },
  });
  const downloads = createExtendedDownloads({
    fetchBytes: (current, key, filename, fetchOptions) =>
      client.artifactBytes(current, key, filename, fetchOptions),
    session: () => session,
    signal: () => runAbort.signal,
  });
  const summaryHost = el("div", { className: "lnt-w1-extended-summary" });
  const root = el(
    "section",
    {
      className: "lnt-w1-extended",
      attrs: { "aria-label": EXTENDED_RUN_TITLE },
    },
    [el("div", { className: "lnt-w1-toolbar" }, [button]), status, downloads.root, summaryHost],
  );

  function setStatus(text: string): void {
    status.textContent = text;
  }

  function renderSummary(summary: CharacterizationSummary): void {
    clearElement(summaryHost);
    summaryHost.append(renderFamilyCards(summary, { session }));
  }

  async function pollDone(jobId: string, signal: AbortSignal): Promise<AnalysisRunSnapshot> {
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      if (signal.aborted) throw new DOMException("aborted", "AbortError");
      const snapshot = await client.runStatus(jobId, { signal });
      if (snapshot.status !== "running" && snapshot.status !== "queued") return snapshot;
    }
  }

  async function run(): Promise<void> {
    const current = session;
    if (current === null || busy) return;
    busy = true;
    button.disabled = true;
    runAbort.abort();
    runAbort = new AbortController();
    const { signal } = runAbort;
    try {
      await client.ensureReady({ signal });
      setStatus("Ищем рецепт characterization-v1…");
      const recipes = await client.recipes({ signal });
      const recipe = recipes.find((item) => item.name === EXTENDED_RECIPE_NAME);
      if (recipe === undefined) {
        setStatus("Рецепт characterization-v1 не найден в каталоге.");
        return;
      }
      setStatus("Запускаем расширенный анализ…");
      const started = await client.runAnalysis(
        { session: current, recipe_id: recipe.recipe_id },
        { signal },
      );
      const done = await pollDone(started.job_id, signal);
      if (done.status !== "succeeded" || done.artifact_key === null) {
        setStatus(`Расширенный анализ не завершён: ${done.error ?? done.status}.`);
        return;
      }
      setStatus(`Готово. Ключ артефакта: ${done.artifact_key}.`);
      downloads.render(done.artifact_key);
      const raw = await client.artifactBytes(current, done.artifact_key, BUNDLE_FILES[0], {
        signal,
      });
      const summary = parseCharacterizationSummary(decodeJson(raw));
      if (summary === null) {
        setStatus("Сводка не прочитана: characterization.json вне формата.");
        return;
      }
      renderSummary(summary);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setStatus(error instanceof Error ? error.message : "Неизвестная ошибка");
    } finally {
      busy = false;
      button.disabled = false;
    }
  }

  button.addEventListener("click", () => {
    void run();
  });

  return {
    root,
    setSession(next) {
      session = next;
      runAbort.abort();
      runAbort = new AbortController();
      downloads.clear();
      clearElement(summaryHost);
      button.disabled = next === null;
      setStatus(next === null ? "Выберите сессию." : "Готов к запуску.");
    },
    destroy() {
      runAbort.abort();
      root.remove();
    },
  };
}
