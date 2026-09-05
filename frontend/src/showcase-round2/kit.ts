/** Общий скелет раунда 2 (ТЗ 2026-08-29): DOM-хелпер, шелл, каталог, спектр, KPI.
 *  Все варианты используют одни секции; скелеты различаются только сеткой и плотностью. */
import type uPlot from "uplot";

import "../showcase-redesign/fonts/fonts.css";
import "./tokens.css";
import "./kit.css";
import { JOB, SESSIONS } from "../showcase-redesign/data";
import { type SpectrumStyle, renderSpectrum } from "../showcase-redesign/spectrum";

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  cls = "",
  attrs: Readonly<Record<string, string>> = {},
  kids: readonly (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  for (const [key, val] of Object.entries(attrs)) node.setAttribute(key, val);
  for (const kid of kids) node.append(kid);
  return node;
}

export const NAV_ITEMS = [
  "Каталог",
  "Захват",
  "Инспекция",
  "Эксперименты",
  "Отчёты",
  "Настройки",
] as const;

/** Вертикальная навигация: пункт 30px, активный — 2px акцентная полоса (§2.3). */
export function buildNav(active: string): HTMLElement {
  const nav = h("nav", "snav", { "aria-label": "Разделы" });
  for (const item of NAV_ITEMS) {
    const link = h(
      "a",
      `snav-item${item === active ? " is-active" : ""}`,
      { href: "#", "aria-current": item === active ? "page" : "" },
      [item],
    );
    link.addEventListener("click", (event) => event.preventDefault());
    nav.append(link);
  }
  return nav;
}

/** Таб-бар в шапке для варианта с верхними вкладками (V3). */
export function buildTabbar(active: string): HTMLElement {
  const nav = h("nav", "tabbar", { "aria-label": "Разделы" });
  for (const item of NAV_ITEMS) {
    const link = h(
      "a",
      `snav-item${item === active ? " is-active" : ""}`,
      { href: "#", "aria-current": item === active ? "page" : "" },
      [item],
    );
    link.addEventListener("click", (event) => event.preventDefault());
    nav.append(link);
  }
  return nav;
}

/** Шапка 32px: прибор, активная задача, действия (§5.5). */
export function buildHeader(withTabs: boolean): HTMLElement {
  const header = h("header", "hdr", {}, [
    h("span", "hdr-brand", {}, ["LNT"]),
    h("span", "hdr-status", {}, [
      h("span", "dot", { "aria-hidden": "true" }),
      "Hantek 6022BE · готов",
    ]),
  ]);
  if (withTabs) {
    header.append(buildTabbar("Инспекция"));
  }
  header.append(
    h("span", "hdr-status", {}, [`${JOB.status} — ${JOB.stage} · ${JOB.series}`]),
    h("div", "hdr-actions", {}, [
      h("button", "btn-quiet", { type: "button" }, ["Открыть корень"]),
      h("button", "btn-quiet", { type: "button" }, ["Отмена серии"]),
    ]),
  );
  return header;
}

/** Статус-бар 32px: глобальный статус и корень сессий (§5.5). */
export function buildStatusbar(): HTMLElement {
  return h("footer", "statusbar", {}, [
    h("span", "statusbar-item", {}, [
      h("span", "dot", { "aria-hidden": "true" }),
      `${JOB.status} — ${JOB.stage} · ${JOB.series}`,
    ]),
    h("span", "statusbar-spacer", {}),
    h("span", "statusbar-item num", {}, ["Корень: C:\\lnt-sessions"]),
  ]);
}

/** Каталог сессий: таблица с краевой строкой и переносом длинных путей (§1.2, §6). */
export function buildCatalog(): HTMLElement {
  const thead = h("thead", "", {}, [
    h("tr", "", {}, [
      h("th", "", { scope: "col", "aria-label": "Состояние" }, [""]),
      h("th", "", { scope: "col" }, ["Метка"]),
      h("th", "", { scope: "col" }, ["Тип"]),
      h("th", "", { scope: "col" }, ["Дата"]),
    ]),
  ]);
  const tbody = h("tbody");
  SESSIONS.forEach((session, index) => {
    const edge = Boolean(session.storagePath);
    const row = h("tr", index === 0 ? "is-selected" : "", {
      "data-row": edge ? "edge" : session.id,
    });
    row.append(
      h("td", "", {}, [
        h(
          "span",
          `glyph glyph-${session.health}`,
          { title: session.healthLabel, "aria-label": session.healthLabel },
          [session.glyph],
        ),
      ]),
      h("td", "cell-ellipsis", { title: session.label }, [session.label]),
      h("td", "cell-ellipsis", { title: session.typeLabel }, [session.typeLabel]),
      h("td", "num", {}, [session.date]),
    );
    const sub = h("tr");
    sub.append(
      h("td", "cell-path", { colspan: "4" }, [
        h("span", `sub-health glyph-${session.health}`, {}, [session.healthLabel]),
        session.storagePath ?? session.id,
      ]),
    );
    tbody.append(row, sub);
  });
  return h("section", "panel", { "data-showcase": "catalog" }, [
    h("div", "panel-hd", {}, [h("h2", "panel-title", {}, ["Каталог сессий"])]),
    h("div", "panel-bd is-bare", {}, [
      h("div", "tbl-wrap", {}, [h("table", "tbl tbl-tight tbl-cat", {}, [thead, tbody])]),
    ]),
  ]);
}

/** §4: акцент — трасса А сплошная ●, трасса Б #E68619 штриховая ■. */
export const SPECTRUM_STYLE: SpectrumStyle = {
  traceA: "#5681FF",
  traceB: "#E68619",
  grid: "#3F3F3F",
  axisText: "#D1D1D1",
  lineWidth: 1.5,
  dash: [6, 4],
  axisFont: '500 10px "Source Code Pro Variable", monospace',
  height: 300,
};

/** Хуки варианта к графику: перерисовка слоя аннотаций и доступ к экземпляру uPlot. */
export interface SpectrumHooks {
  onDraw?: (plot: uPlot) => void;
  onPlot?: (plot: uPlot) => void;
  /** Подписи трасс: вариант может назвать реальные сессии вместо «Сессия А/Б». */
  labels?: { a: string; b: string };
  /** Заголовок панели; по умолчанию «Спектр мощности». */
  title?: string;
  /** Подпись оси X; пустая строка сжимает ось до строки тиков (общая шкала с дорожкой). */
  xLabel?: string;
}

/** Спектр в канве #1D1D1D: сигнал отделён от хрома (§5.1). */
export function buildSpectrumPanel(height: number, hooks: SpectrumHooks = {}): HTMLElement {
  const host = h("div", "frame");
  const header = h("div", "panel-hd", {}, [
    h("h2", "panel-title", {}, [hooks.title ?? "Спектр мощности"]),
  ]);
  const plot = renderSpectrum(
    host,
    { ...SPECTRUM_STYLE, height, xLabel: hooks.xLabel ?? "Частота, Гц" },
    hooks.labels ?? { a: "Сессия А", b: "Сессия Б" },
    { header, onDraw: hooks.onDraw },
  );
  hooks.onPlot?.(plot);
  return h("section", "panel", { "data-showcase": "spectrum" }, [
    header,
    h("div", "panel-bd", {}, [host]),
  ]);
}

export interface KpiItem {
  label: string;
  value: string;
  unit?: string;
}

/** Ряд KPI одной строкой (V3) и плитки (V4): числовые показания рядом с контролами (§5.4). */
export function buildKpiRow(items: readonly KpiItem[], kind: "row" | "tiles"): HTMLElement {
  const row = h("div", kind === "row" ? "kpi-row" : "kpi-row kpi-tiles");
  for (const item of items) {
    const value = h("span", "meter-value", {}, [item.value]);
    if (item.unit) value.append(h("span", "t-unit", {}, [item.unit]));
    row.append(h("div", "kpi", {}, [h("span", "meter-label", {}, [item.label]), value]));
  }
  return row;
}
