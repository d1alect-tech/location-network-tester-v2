/** Расширенный прогон characterization-v1: одна кнопка + скачивание + сводка.
 * Без графиков и управления каталогом рецептов: recipe_id захардкожен через
 * список рецептов по имени characterization-v1. */

import type { AnalysisRunSnapshot } from "../../api/types-analysis";
import { clearElement, el } from "../../components/primitives/dom";

export const EXTENDED_RUN_BUTTON = "Запустить расширенный анализ";
export const EXTENDED_RUN_TITLE = "Расширенный анализ (characterization-v1)";
export const EXTENDED_RECIPE_NAME = "characterization-v1";
export const BUNDLE_FILES = [
  "characterization.json",
  "characterization-arrays.npz",
  "characterization-tables.json",
] as const;

export type BundleFileName = (typeof BUNDLE_FILES)[number];

export type ExtendedRunClient = {
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
  readonly families: readonly { readonly id: string; readonly status: string }[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asFinite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Разбирает characterization.json: f1 из сводки F01 + статусы семейств. */
export function parseCharacterizationSummary(payload: unknown): CharacterizationSummary | null {
  if (!isRecord(payload) || !Array.isArray(payload.families)) return null;
  const families: { id: string; status: string }[] = [];
  for (const item of payload.families) {
    if (!isRecord(item) || typeof item.family_id !== "string" || typeof item.status !== "string") {
      return null;
    }
    families.push({ id: item.family_id, status: item.status });
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

function formatF1(value: number | null): string {
  return value === null ? "н/д" : `${value.toFixed(2)} Гц`;
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
  const downloads = el("div", { className: "lnt-w1-extended-downloads" });
  const summaryHost = el("div", { className: "lnt-w1-extended-summary" });
  const root = el(
    "section",
    {
      className: "lnt-w1-extended",
      attrs: { "aria-label": EXTENDED_RUN_TITLE },
    },
    [el("div", { className: "lnt-w1-toolbar" }, [button]), status, downloads, summaryHost],
  );

  function setStatus(text: string): void {
    status.textContent = text;
  }

  function saveBlob(name: string, buffer: ArrayBuffer): void {
    const url = URL.createObjectURL(new Blob([buffer]));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  function renderDownloads(artifactKey: string): void {
    clearElement(downloads);
    for (const name of BUNDLE_FILES) {
      const link = el("button", {
        className: "lnt-btn",
        text: `Скачать ${name}`,
        attrs: { type: "button", "data-bundle-file": name },
      });
      link.addEventListener("click", () => {
        void (async () => {
          if (session === null) return;
          const bytes = await client.artifactBytes(session, artifactKey, name, {
            signal: runAbort.signal,
          });
          saveBlob(`${artifactKey}-${name}`, bytes);
        })();
      });
      downloads.append(link);
    }
  }

  function renderSummary(summary: CharacterizationSummary): void {
    clearElement(summaryHost);
    const title = el("h3", { text: "Сводка расширенного анализа" });
    const f1 = el("p", {
      className: "lnt-w1-panel-note",
      text: `Частота сети F01: ${formatF1(summary.f1Hz)}`,
    });
    const list = el("ul", { className: "lnt-w1-failures" });
    for (const family of summary.families) {
      list.append(el("li", { text: `${family.id}: ${family.status}` }));
    }
    summaryHost.append(title, f1, list);
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
      renderDownloads(done.artifact_key);
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
      clearElement(downloads);
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
