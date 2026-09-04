/** B3: селекторы RBW/окна спектр-панели. Опции 10/30/50/100/300 Гц и 4 окна
 * повторяют бэкенд-контракт RBW_OPTIONS_HZ/WINDOW_OPTIONS. Подпись файла
 * (RBW/окно/ENBW) — из payload; выбор пользователя хранится локально,
 * пометка честно говорит: применится при следующем анализе. */

import type { SpectrumPayload } from "../../api/types-plots";
import { el, nextId } from "../../components/primitives/dom";
import { ruHz } from "./spectrumReadout";

export const MARKER_RBW_OPTIONS = [10, 30, 50, 100, 300] as const;
export const MARKER_WINDOW_OPTIONS = ["hann", "flattop", "kaiser", "blackman"] as const;
export const MARKER_WINDOW_LABELS: Record<string, string> = {
  hann: "Ханн",
  flattop: "Флэт-топ",
  kaiser: "Кайзер",
  blackman: "Блэкман",
};

const RBW_STORAGE_KEY = "lnt.spectrum.rbw";
const WINDOW_STORAGE_KEY = "lnt.spectrum.window";

export interface SpectrumSelectors {
  readonly root: HTMLElement;
  paint(payload: SpectrumPayload): void;
}

function storedChoice(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storeChoice(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* приватный режим: выбор живёт до перезагрузки */
  }
}

function nearestRbw(value: number): number {
  let best: number = MARKER_RBW_OPTIONS[0] ?? 50;
  for (const option of MARKER_RBW_OPTIONS) {
    if (Math.abs(option - value) < Math.abs(best - value)) best = option;
  }
  return best;
}

export function createSpectrumSelectors(): SpectrumSelectors {
  const rbwId = nextId("spectrum-rbW");
  const windowId = nextId("spectrum-window");
  const rbwSelect = el("select", { attrs: { id: rbwId, "data-spectrum-rbW-select": "" } });
  for (const option of MARKER_RBW_OPTIONS) {
    rbwSelect.append(el("option", { text: `${option} Гц`, attrs: { value: String(option) } }));
  }
  const windowSelect = el("select", {
    attrs: { id: windowId, "data-spectrum-window-select": "" },
  });
  for (const option of MARKER_WINDOW_OPTIONS) {
    windowSelect.append(
      el("option", {
        text: MARKER_WINDOW_LABELS[option] ?? option,
        attrs: { value: option },
      }),
    );
  }
  const meta = el("span", {
    className: "selectors-meta num",
    attrs: { "data-spectrum-selector-meta": "" },
  });
  const note = el("span", {
    className: "selectors-note",
    attrs: { "data-spectrum-selector-note": "", role: "status" },
  });
  const root = el(
    "div",
    { className: "spectrum-selectors", attrs: { "data-spectrum-selectors": "" } },
    [
      el("label", { text: "RBW", attrs: { for: rbwId } }, [rbwSelect]),
      el("label", { text: "Окно", attrs: { for: windowId } }, [windowSelect]),
      meta,
      note,
    ],
  );

  let fileRbw: number | null = null;
  let fileWindow: string | null = null;

  function repaintNote(): void {
    const selectedRbw = rbwSelect.value;
    const selectedWindow = windowSelect.value;
    const fileOption = fileRbw === null ? null : String(nearestRbw(fileRbw));
    if (selectedRbw === fileOption && selectedWindow === (fileWindow ?? "hann")) {
      note.textContent = "";
      note.toggleAttribute("hidden", true);
      return;
    }
    const windowLabel = MARKER_WINDOW_LABELS[selectedWindow] ?? selectedWindow;
    note.textContent = `Выбор: RBW ${selectedRbw} Гц · окно ${windowLabel} — применится при следующем анализе`;
    note.removeAttribute("hidden");
  }

  rbwSelect.addEventListener("change", () => {
    storeChoice(RBW_STORAGE_KEY, rbwSelect.value);
    repaintNote();
  });
  windowSelect.addEventListener("change", () => {
    storeChoice(WINDOW_STORAGE_KEY, windowSelect.value);
    repaintNote();
  });

  return {
    root,
    paint(payload) {
      const raw = payload as SpectrumPayload & { window?: unknown; enbw_hz?: unknown };
      const windowName = typeof raw.window === "string" ? raw.window : null;
      const enbwHz =
        typeof raw.enbw_hz === "number" && Number.isFinite(raw.enbw_hz) ? raw.enbw_hz : null;
      const df = payload.resolution_hz;
      fileRbw = typeof df === "number" && df > 0 ? (enbwHz ?? 1.5 * df) : null;
      fileWindow = windowName;
      const signature =
        fileRbw === null
          ? null
          : `RBW ≈ ${ruHz.format(fileRbw)} Гц · окно ${MARKER_WINDOW_LABELS[windowName ?? ""] ?? "Ханн"}${enbwHz === null ? "" : ` · ENBW ${ruHz.format(enbwHz)} Гц`}`;
      meta.textContent = signature ?? "";
      meta.toggleAttribute("hidden", signature === null);
      rbwSelect.value = String(fileRbw === null ? 50 : nearestRbw(fileRbw));
      windowSelect.value = windowName ?? "hann";
      const storedRbw = storedChoice(RBW_STORAGE_KEY);
      const storedWindow = storedChoice(WINDOW_STORAGE_KEY);
      if (storedRbw !== null) rbwSelect.value = storedRbw;
      if (storedWindow !== null) windowSelect.value = storedWindow;
      repaintNote();
    },
  };
}
