/** Скачивание артефактов бандла characterization-v1: кнопки, видимая ошибка, повтор.
 *
 * Отказ скачивания раньше гасился в строке статуса прогона и не имел повтора;
 * здесь ошибка живёт собственной строкой `role="alert"` рядом с кнопками,
 * объявляется вежливо и повторяется одной кнопкой «Повторить».
 */

import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";

export const BUNDLE_FILES = [
  "characterization.json",
  "characterization-arrays.npz",
  "characterization-tables.json",
] as const;

export type BundleFileName = (typeof BUNDLE_FILES)[number];

/** Чтение байтов артефакта; форма совпадает с `ExtendedRunClient.artifactBytes`. */
export type ArtifactFetcher = (
  session: string,
  key: string,
  filename: string,
  options?: { readonly signal?: AbortSignal },
) => Promise<ArrayBuffer>;

export type ExtendedDownloadsHandle = {
  readonly root: HTMLElement;
  /** Рисует три кнопки скачивания для ключа артефакта. */
  render(artifactKey: string): void;
  /** Убирает кнопки и строку ошибки (смена сессии, teardown). */
  clear(): void;
};

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

export function createExtendedDownloads(options: {
  readonly fetchBytes: ArtifactFetcher;
  readonly session: () => string | null;
  readonly signal: () => AbortSignal;
}): ExtendedDownloadsHandle {
  const row = el("div", { className: "lnt-w1-extended-downloads" });
  const errorHost = el("div", { className: "lnt-xr-error-host" });
  const root = el("div", { className: "lnt-xr-downloads" }, [row, errorHost]);
  let artifactKey: string | null = null;

  function clearError(): void {
    clearElement(errorHost);
  }

  function showError(name: BundleFileName, error: unknown): void {
    if (error instanceof DOMException && error.name === "AbortError") return;
    const message = error instanceof Error ? error.message : "Неизвестная ошибка";
    const text = `Не скачано: ${name} — ${message}`;
    const retry = el("button", {
      className: "lnt-btn",
      text: "Повторить",
      attrs: { type: "button", "data-download-retry": name },
    });
    retry.addEventListener("click", () => {
      void download(name);
    });
    clearError();
    errorHost.append(
      el(
        "div",
        { className: "lnt-xr-error", attrs: { role: "alert", "data-download-error": name } },
        [el("span", { className: "lnt-xr-error-text", text }), retry],
      ),
    );
    announcePolite(text);
  }

  async function download(name: BundleFileName): Promise<void> {
    const session = options.session();
    const key = artifactKey;
    if (session === null || key === null) return;
    clearError();
    try {
      const bytes = await options.fetchBytes(session, key, name, { signal: options.signal() });
      saveBlob(`${key}-${name}`, bytes);
    } catch (error) {
      showError(name, error);
    }
  }

  return {
    root,
    render(key) {
      artifactKey = key;
      clearError();
      clearElement(row);
      for (const name of BUNDLE_FILES) {
        const link = el("button", {
          className: "lnt-btn",
          text: `Скачать ${name}`,
          attrs: { type: "button", "data-bundle-file": name },
        });
        link.addEventListener("click", () => {
          void download(name);
        });
        row.append(link);
      }
    },
    clear() {
      artifactKey = null;
      clearError();
      clearElement(row);
    },
  };
}
