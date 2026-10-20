/** Rate-поле вкладки «Осциллограф» (Todo 9; задача 14 — чип + stateless
 * listbox): частота дискретизации из таблицы прибора, 9 опций > 5 — чип со
 * слотом ПРИМЕНЁННОГО значения и меню, принадлежащим только чипу (Esc/клик
 * мимо закрывают без изменений). Выбор — staged-цель следующего запуска: на
 * ходу частота сервис не меняет (POST /api/live/config частоты не несёт);
 * слот переводит применённое значение статус-модель полосы (scopeStatus).
 * selectRate — программная дорога сброса/автосета (задача 15). Таблица —
 * pins PyHT6022/LibUsbScope.py:74-99 (Ho-Ro e65d52b); директива владельца
 * 2026-10-19: лестница открыта вниз до 20 кГц (SLOW_RATE_CODES бэкенда).
 * Построение DOM и локальное состояние, сеть — в workspace. */

import { DEFAULT_LIVE_START_REQUEST } from "../../api/types-live";
import { createLiveChip } from "../../components/liveStrip/liveChip";
import { el } from "../../components/primitives/dom";

/** Лестница частот прибора: 20 кГц…8 МГц (1-2-5 снизу, целые МГц сверху). */
export const SCOPE_SAMPLE_RATES_HZ: readonly number[] = [
  20_000, 50_000, 100_000, 200_000, 500_000, 1_000_000, 2_000_000, 4_000_000, 8_000_000,
];

export function rateLabelHz(hz: number): string {
  return hz >= 1_000_000 ? `${hz / 1_000_000} МГц` : `${hz / 1_000} кГц`;
}

export interface ScopeRateField {
  readonly root: HTMLElement;
  rateHz(): number;
  /** Программный выбор (сброс/автосет, задача 15): та же staged-дорога. */
  selectRate(hz: number): void;
}

/** Rate-поле: только таблица прибора, дефолт 8 МГц (InstrumentService). */
export function buildScopeRateField(): ScopeRateField {
  let rate = DEFAULT_LIVE_START_REQUEST.sample_rate_hz;
  const chip = createLiveChip(
    {
      key: "rate",
      aria: "Частота дискретизации",
      options: SCOPE_SAMPLE_RATES_HZ.map((hz) => ({
        value: String(hz),
        text: rateLabelHz(hz),
      })),
      current: String(DEFAULT_LIVE_START_REQUEST.sample_rate_hz),
      menuTitle: "Частота · применяется при запуске",
    },
    (value) => {
      rate = Number(value);
    },
  );
  return {
    root: el("div", { className: "lnt-scope-field lnt-scope-rate-field" }, [chip.root]),
    rateHz: () => rate,
    selectRate: (hz: number): void => {
      rate = hz;
      chip.markTarget(String(hz));
    },
  };
}
