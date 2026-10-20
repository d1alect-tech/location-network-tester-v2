/** Масштаб живой развёртки (Todo 8; директива владельца 2026-10-19): закон
 * АЦП + ЭКРАННЫЕ деления. Единый источник истины — бэкенд: RANGE_CODES
 * (acquire_validation.py:18), закон raw→V = 5.12·probe/(code<<7)
 * (adc_calibration.py:94, центр 128). Экран несёт 8 вертикальных делений:
 * окно оси Y = ±4·В/дел·пробник, полная шкала АЦП = ±5.12/код В.
 * В/дел — ЭКРАННАЯ шкала с лестницей 1-2-5 до 10 мВ/дел; гейн-код драйвера
 * один на пару каналов, и ниже полной шкалы самого чувствительного кода
 * (±512 мВ) младшие шаги — экранное усиление тех же 8 бит: ярлык
 * vdivTagText честно называет вход АЦП («unavailable, never fabricated»).
 * Нулевые линии каналов — поля groundCh1V/groundCh2V: сдвиг ОТОБРАЖЕНИЯ,
 * измерения считаются по payload и сдвига не видят. Чистые функции без DOM. */

export const VOLTS_SCALE = 5.12;
export const ADC_CENTER = 128;
export const ADC_HALF_SPAN = 128;

/** Номинал В/дел -> код гейна драйвера (зеркало RANGE_CODES бэкенда). */
export const RANGE_CODES: Readonly<Record<number, number>> = { 5: 1, 1: 5, 0.5: 10 };

/** Лестница В/дел 1-2-5 от 5 В до 10 мВ (директива владельца 2026-10-19). */
export const VDIV_STEPS: readonly number[] = [5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01];

/** Пробник CH1 1×/10× (паттерн acquire.py _ch1_probe_multiplier). */
export const PROBE_STEPS: readonly number[] = [1, 10];

/** Вертикальных делений экрана: окно оси Y = ±SCREEN_DIVISIONS/2·В/дел. */
export const SCREEN_DIVISIONS = 8;

export interface ScopeDisplaySettings {
  /** Шаг В/дел экрана; в железо со следующим Run уходит диапазон пары. */
  vDiv: number;
  /** Пробник CH1: масштабирует закон, окно сетки и readout-подписи. */
  probe: number;
  invertCh1: boolean;
  invertCh2: boolean;
  /** Нулевая линия CH1 на экране, В: положение 0 В канала (drag ручки). */
  groundCh1V: number;
  /** Нулевая линия CH2 на экране, В. */
  groundCh2V: number;
}

export const DEFAULT_SCOPE_SETTINGS: ScopeDisplaySettings = {
  vDiv: 1,
  probe: 1,
  invertCh1: false,
  invertCh2: false,
  groundCh1V: 0,
  groundCh2V: 0,
};

/** Код гейна драйвера для номинала АЦП-таблицы; вне тройки — ошибка входа. */
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

/** Полная шкала диапазона АЦП (половина окна по коду): ±5.12·probe/код В. */
export function halfSpanVolts(vDiv: number, probe: number): number {
  return ADC_HALF_SPAN * voltsPerLsb(rangeCodeOf(vDiv), probe);
}

/** Половина окна оси Y экрана: 4·В/дел·пробник (SCREEN_DIVISIONS делений). */
export function windowHalfVolts(vDiv: number, probe: number): number {
  return (SCREEN_DIVISIONS / 2) * vDiv * probe;
}

/** Окно оси Y: симметричное ±4·В/дел — сетка стабильна между кадрами. */
export function yAxisRange(vDiv: number, probe: number): [number, number] {
  const half = windowHalfVolts(vDiv, probe);
  return [-half, half];
}

/** Диапазон АЦП для В/дел (тело запуска, код один на пару каналов): самый
 *  чувствительный код, чья полная шкала вмещает окно экрана; шире — 5 В. */
export function hardwareRangeFor(vDiv: number): number {
  const half = windowHalfVolts(vDiv, 1);
  let range = 5;
  for (const step of [1, 0.5]) {
    if (halfSpanVolts(step, 1) >= half) range = step;
  }
  return range;
}

/** Подпись вольта ярлыков: «5.12 В» / «512 мВ». */
export function formatVolts(value: number): string {
  return value >= 1 ? `${value} В` : `${Math.round(value * 1000)} мВ`;
}

/** Ярлык честности вертикали (прецедент ФНЧ — «программный, не аналоговый
 *  предел»): экранное усиление ≥2× или сетка шире входа АЦП; null — честно. */
export function vdivTagText(vDiv: number, probe: number): string | null {
  const range = hardwareRangeFor(vDiv);
  const hwHalf = halfSpanVolts(range, probe);
  const half = windowHalfVolts(vDiv, probe);
  if (half > hwHalf) {
    return `В/дел ${formatVDiv(vDiv)} — сетка шире входа АЦП ±${formatVolts(hwHalf)}`;
  }
  const gain = hwHalf / half;
  if (gain >= 2) {
    const head = `В/дел ${formatVDiv(vDiv)} — экранное усиление ×${gain.toFixed(1)}`;
    return `${head}, вход АЦП ±${formatVolts(hwHalf)}`;
  }
  return null;
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
