/** Примитив рамки панелей (todo 2, ui-refactor-2): DOM-структура канонической
 * рамки, описанной в primitives/panel.css — единственном источнике правил
 * .panel/.panel-hd/.panel-title/.panel-bd/.field/.ctl. Плотность и геометрия
 * видов остаются в их scoped CSS и здесь не решаются. */

import { type ElOptions, el } from "./dom";

function withClass(base: string, options: ElOptions): ElOptions {
  return { ...options, className: options.className ? `${base} ${options.className}` : base };
}

/** section.panel — контейнер рамки: фон панели, колонка, hairline-стыки. */
export function panel(options: ElOptions = {}, children: Node[] = []): HTMLElement {
  return el("section", withClass("panel", options), children);
}

/** div.panel-hd — шапка рамки: 30px, полоса темнее фона, hairline снизу. */
export function panelHd(options: ElOptions = {}, children: Node[] = []): HTMLElement {
  return el("div", withClass("panel-hd", options), children);
}

/** Заголовок .panel-title (h2 — идиома живых панелей capture/reports). */
export function panelTitle(text: string, options: ElOptions = {}): HTMLElement {
  return el("h2", { ...withClass("panel-title", options), text });
}

export interface PanelBdOptions extends ElOptions {
  /** Тело без отступов и прокрутки: канонический модификатор .panel-bd.is-bare. */
  readonly bare?: boolean;
}

/** div.panel-bd — тело рамки: растёт на всю панель, прокрутка внутри. */
export function panelBd(options: PanelBdOptions = {}, children: Node[] = []): HTMLElement {
  const { bare, ...rest } = options;
  return el("div", withClass(bare ? "panel-bd is-bare" : "panel-bd", rest), children);
}
