import type { ChartHandle } from "../../components/charts/types";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { el } from "../../components/primitives/dom";
import type { GramMode, GramPairClient, GramPairTile } from "./gramPair";
import { createGramPair } from "./gramPair";
import { createOrientedSpectrogramView } from "./spectrogramOrient";

export type InspectV6GramPanel = {
  readonly gramHost: HTMLElement;
  readonly gramBar: HTMLElement;
};

export type InspectV6GramDeps = {
  readonly client: GramPairClient;
  readonly spectrumPanel: InspectV6GramPanel;
  readonly createView?: (options: UplotViewOptions) => ChartHandle;
};

export type InspectV6GramHandle = {
  refresh(a: string | null, b: string | null): Promise<void>;
  dispose(): void;
};

const MODES = [
  { mode: "a", label: "База" },
  { mode: "b", label: "Сравнение" },
  { mode: "delta", label: "Δ Б−А" },
] as const;

const MISMATCH_NOTE = "сетки спектрограмм не совпадают";
const EMPTY_NOTE = "нет спектрограммы записи";

function assertNever(value: never): never {
  throw new Error(`unhandled ${String(value)}`);
}

function isGramMode(value: string | null): value is GramMode {
  return value === "a" || value === "b" || value === "delta";
}

function formatDb(value: number): string {
  return String(Math.round(value));
}

/** Подпись шкалы: уровень — дБВ/Гц с опорой 1 В²/Гц, дельта — честный min/max в дБ. */
export function scaleText(mode: GramMode, tile: GramPairTile): string {
  switch (mode) {
    case "delta":
      return `${signedDb(tile.minDb)} … ${signedDb(tile.maxDb)} дБ`;
    case "a":
    case "b":
      return `${formatDb(tile.minDb)} … ${formatDb(tile.maxDb)} дБВ/Гц (отн. 1 В²/Гц)`;
    default:
      return assertNever(mode);
  }
}

function signedDb(value: number): string {
  const rounded = Math.round(value);
  return rounded < 0 ? `−${formatDb(-rounded)}` : `+${formatDb(rounded)}`;
}

export function wireInspectV6Gram(deps: InspectV6GramDeps): InspectV6GramHandle {
  const { client, spectrumPanel } = deps;
  const oriented = createOrientedSpectrogramView();
  spectrumPanel.gramHost.append(oriented.root);
  const gramPair = createGramPair({ client });

  const buttons: HTMLButtonElement[] = [];
  for (const item of MODES) {
    buttons.push(
      el("button", {
        className: "gram-mode",
        text: item.label,
        attrs: {
          type: "button",
          "data-spectrogram-mode": item.mode,
          "aria-pressed": "false",
        },
      }),
    );
  }
  const modes = el(
    "div",
    { className: "gram-modes", attrs: { role: "group", "aria-label": "Содержимое спектрограммы" } },
    buttons,
  );
  const readout = el("span", { className: "gram-readout" });
  const scale = el("span", { className: "gram-scale" });
  spectrumPanel.gramBar.append(modes, readout, scale);

  function deltaButton(): HTMLButtonElement | undefined {
    return buttons.find((button) => button.getAttribute("data-spectrogram-mode") === "delta");
  }

  function paintPressed(): void {
    const active = gramPair.mode();
    for (const button of buttons) {
      button.setAttribute(
        "aria-pressed",
        String(button.getAttribute("data-spectrogram-mode") === active),
      );
    }
  }

  function renderCurrent(): void {
    const current = gramPair.current();
    switch (current.kind) {
      case "tile":
        oriented.setDomain({
          timeS: current.tile.times,
          frequencyHz: current.tile.freqs,
        });
        oriented.renderTile(current.tile, current.minDb, current.maxDb);
        scale.textContent = scaleText(gramPair.mode(), current);
        return;
      case "mismatch":
        scale.textContent = MISMATCH_NOTE;
        return;
      default:
        assertNever(current);
    }
  }

  for (const button of buttons) {
    button.addEventListener("click", () => {
      const mode = button.getAttribute("data-spectrogram-mode");
      if (!isGramMode(mode)) return;
      gramPair.setMode(mode);
      paintPressed();
      renderCurrent();
    });
  }

  return {
    async refresh(a, b) {
      if (a === null || a === "") return;
      await gramPair.load(a, b);
      for (const button of buttons) button.disabled = false;
      if (gramPair.empty()) {
        // Ни у одной сессии пары нет артефакта: режимы недоступны, без ошибки.
        for (const button of buttons) {
          button.disabled = true;
          button.setAttribute("aria-pressed", "false");
        }
        scale.textContent = EMPTY_NOTE;
        return;
      }
      const matches = gramPair.gridMatches();
      const delta = deltaButton();
      if (delta !== undefined) delta.disabled = !matches;
      paintPressed();
      renderCurrent();
      // Нота несовпадения — только когда обе сессии загружены, но сетки разные:
      // отсутствие одной сессии не является несовпадением.
      if (gramPair.paired() && !matches) scale.textContent = MISMATCH_NOTE;
    },
    dispose() {
      gramPair.dispose();
      oriented.dispose();
    },
  };
}
