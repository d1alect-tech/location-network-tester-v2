/** Контракты графиков workbench (todo 41): рендер-запросы и хэндлы,
 * не зависящие от конкретной библиотеки. uPlot-реализация — в uplotView. */

/** Пик спектра из analysis.spectrum.peaks (контракт metrics.json v2). */
export interface ChartPeak {
  frequency_hz: number;
  level_db: number;
  prominence_db: number;
  q_factor: number;
}

export interface ChartRenderSeries {
  label: string;
  values: readonly number[];
  /** Цвет линии из дизайн-токенов (--lnt-accent-a/b). */
  color: string;
  /** Шаблон штриха [штрих, пробел]; undefined — сплошная линия. */
  dash?: readonly [number, number];
  /** Символ нецветовой метки серии для сводки (DESIGN.md 4.2): ● / ■. */
  marker?: string;
}

export interface ChartRenderRequest {
  xLabel: string;
  yLabel: string;
  /** Логарифмические оси: данные обязаны быть log-safe (filterLogSafePairs). */
  xLog?: boolean;
  yLog?: boolean;
  x: readonly number[];
  series: readonly ChartRenderSeries[];
  /** Вертикальные аннотации пиков (только спектр). */
  peaks?: readonly ChartPeak[];
}

export interface ChartHandle {
  /** Постоянный контейнер содержимого графика для ChartShell.setContent. */
  readonly root: HTMLElement;
  render(request: ChartRenderRequest): void;
  applyTheme(): void;
  /** Выровненные данные последнего рендера — для паритетных фикстур. */
  getData(): unknown;
  destroy(): void;
}

/** Символы A/B по DESIGN.md 4.2: круг у А, квадрат у Б. */
export const MARKER_A = "●";
export const MARKER_B = "■";
