/** B3 Section-контракт (ui-refactor-2, todo 9): секция инспекции владеет своим
 * DOM, принимает пару одним вызовом и освобождает ресурсы (uPlot sync-key,
 * echarts-инстанции, слушатели) в destroy(). Инспекция монтирует секции, а не
 * собирает их из чужих слотов. */

export type InspectSection = {
  readonly root: HTMLElement;
  /** Смена пары инспекции: секция обновляет всё своё содержимое. */
  setPair(a: string | null, b: string | null): void;
  destroy(): void;
};
