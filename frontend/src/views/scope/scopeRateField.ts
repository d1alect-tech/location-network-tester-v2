/** Rate-селектор вкладки «Осциллограф» (Todo 9): частота дискретизации из
 * таблицы прибора, стейджится для следующего запуска. На ходу частоту
 * сервис не меняет (POST /api/live/config частоты не несёт) — подпись
 * говорит об этом честно. Таблица — pins PyHT6022/LibUsbScope.py:74-99
 * (Ho-Ro e65d52b); дуал-канальный предел 15 МГц выше всех записей,
 * дополнительная гейтинг-логика не нужна, свип-частот панель не
 * изобретает. Построение DOM + локальное состояние; сеть — в workspace. */

import { DEFAULT_LIVE_START_REQUEST } from "../../api/types-live";
import { el } from "../../components/primitives/dom";

/** Таблица частот прибора: 100 кГц…8 МГц, семь записей. */
export const SCOPE_SAMPLE_RATES_HZ: readonly number[] = [
  100_000, 200_000, 500_000, 1_000_000, 2_000_000, 4_000_000, 8_000_000,
];

const RATE_HINT = "Применяется при запуске захвата; на ходу частота не меняется.";

export function rateLabelHz(hz: number): string {
  return hz >= 1_000_000 ? `${hz / 1_000_000} МГц` : `${hz / 1_000} кГц`;
}

export interface ScopeRateField {
  readonly root: HTMLElement;
  rateHz(): number;
}

/** Rate-селектор: только таблица прибора, дефолт 8 МГц (InstrumentService). */
export function buildScopeRateField(): ScopeRateField {
  let rate = DEFAULT_LIVE_START_REQUEST.sample_rate_hz;
  const buttons = new Map<number, HTMLButtonElement>();
  for (const hz of SCOPE_SAMPLE_RATES_HZ) {
    buttons.set(
      hz,
      el("button", {
        className: "lnt-scope-seg-btn lnt-scope-rate-btn",
        text: rateLabelHz(hz),
        attrs: {
          type: "button",
          "data-scope-rate": String(hz),
          "aria-pressed": String(hz === rate),
        },
      }),
    );
  }
  for (const [hz, button] of buttons) {
    button.addEventListener("click", () => {
      if (hz === rate) return;
      rate = hz;
      for (const [entry, node] of buttons) {
        node.setAttribute("aria-pressed", String(entry === rate));
      }
    });
  }
  return {
    root: el("div", { className: "lnt-scope-field lnt-scope-rate-field" }, [
      el("span", { className: "lnt-scope-field-label", text: "Частота дискретизации" }),
      el(
        "div",
        {
          className: "lnt-scope-seg lnt-scope-rate-seg",
          attrs: { role: "group", "aria-label": "Частота дискретизации" },
        },
        [...buttons.values()],
      ),
      el("p", { className: "t-compact lnt-scope-hint", text: RATE_HINT }),
    ]),
    rateHz: () => rate,
  };
}
