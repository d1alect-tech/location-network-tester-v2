/** Масштаб живой развёртки (Todo 8): зеркало таблицы диапазонов и закона
 * масштаба АЦП. Единый источник истины — бэкенд: RANGE_CODES
 * (acquire_validation.py:18), закон raw→V = 5.12·probe/(code<<7)
 * (adc_calibration.py:94, VOLTS_SCALE=5.12, центр 128).
 *
 * Таблица В/дел ОБЩАЯ для обоих каналов — гейн-код драйвера один на пару
 * (OpenHantek modelDSO6022.cpp @ 836cd98: 9 шагов 20 мВ/дел..5 В/дел);
 * MVP — только три LNT-верифицированных кода {5.0, 1.0, 0.5} В/дел
 * (полная шкала ±5.12/код В), остальные 6 шагов OpenHantek вне MVP.
 * Чистые функции без DOM. */

export const VOLTS_SCALE = 5.12;
export const ADC_CENTER = 128;
export const ADC_HALF_SPAN = 128;

/** Номинал В/дел -> код гейна драйвера (зеркало RANGE_CODES бэкенда). */
export const RANGE_CODES: Readonly<Record<number, number>> = { 5: 1, 1: 5, 0.5: 10 };

/** Доступные шаги В/дел — только LNT-верифицированные коды. */
export const VDIV_STEPS: readonly number[] = [5, 1, 0.5];

/** Пробник CH1 1×/10× (паттерн acquire.py _ch1_probe_multiplier). */
export const PROBE_STEPS: readonly number[] = [1, 10];

export interface ScopeDisplaySettings {
  /** Шаг В/дел из общей таблицы каналов; в железо уходит со следующим Run. */
  vDiv: number;
  /** Пробник CH1: масштабирует закон, окно сетки и readout-подписи. */
  probe: number;
  invertCh1: boolean;
  invertCh2: boolean;
}

export const DEFAULT_SCOPE_SETTINGS: ScopeDisplaySettings = {
  vDiv: 5,
  probe: 1,
  invertCh1: false,
  invertCh2: false,
};

/** Код гейна драйвера для выбранного В/дел; вне тройки — ошибка входа. */
export function rangeCodeOf(vDiv: number): number {
  const code = RANGE_CODES[vDiv];
  if (code === undefined) {
    throw new Error(`диапазон ${vDiv} В/дел не поддерживается: допустимы 5/1/0.5`);
  }
  return code;
}

/** Вольт на LSB: 5.12·probe/(code<<7) — adc_calibration.py:94. */
export function voltsPerLsb(rangeCode: number, probe: number): number {
  return (VOLTS_SCALE * probe) / (rangeCode << 7);
}

/** raw uint8 -> вольты: (raw − 128)·закон. */
export function rawToVolts(raw: number, vDiv: number, probe: number): number {
  return (raw - ADC_CENTER) * voltsPerLsb(rangeCodeOf(vDiv), probe);
}

/** Полная шкала диапазона (половина окна оси Y): ±5.12·probe/код В. */
export function halfSpanVolts(vDiv: number, probe: number): number {
  return ADC_HALF_SPAN * voltsPerLsb(rangeCodeOf(vDiv), probe);
}

/** Окно оси Y: симметричное ±полная шкала — сетка стабильна между кадрами. */
export function yAxisRange(vDiv: number, probe: number): [number, number] {
  const half = halfSpanVolts(vDiv, probe);
  return [-half, half];
}

/** Эффективные В/дел с пробником (масштаб readout-подписи): vDiv·probe. */
export function effectiveVDiv(vDiv: number, probe: number): number {
  return vDiv * probe;
}

/** Подпись «N В/дел» / «N мВ/дел» для readout и опций селектора. */
export function formatVDiv(vDiv: number): string {
  if (vDiv >= 1) return `${vDiv} В/дел`;
  return `${Math.round(vDiv * 1000)} мВ/дел`;
}
