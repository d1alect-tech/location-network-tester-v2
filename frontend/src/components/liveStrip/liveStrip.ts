/** Оболочка полосы liveStrip (задача 14, зона-карта 13): zone-манифест per-tab
 * порождает DOM полосы — 2 линии виджетов (.lnt-live-line), зоны-части
 * pzone/pzone-cont (приём old/flat: зона в одну/обе линии, гравировка
 * только на первой части, хайрлайн продолжается), группы-обёртки
 * [data-ctl]/[data-local]/[data-action]/[data-slot] как точки ре-парента
 * живых узлов, notes/zone-echo, статус-зона [data-band-status] и автокарта
 * [data-zone] — карта не может разойти с DOM (AC2). Полоса НИКОГДА не
 * владеет run-состоянием: кластер и статус-модель ПОТРЕБЛЯЮТ его из
 * live-источника (sharedLiveApi) через LiveStateSource. */

import type { LiveSseDeps, LiveWatchHandle, LiveWatchHandlers } from "../../api/types-live";
import { el } from "../primitives/dom";
import "./liveStrip.css";

/** Узкий порт live-контура для потребителей полосы: подписка на состояние
 * владения без владения самим состоянием (адаптер над LiveApi.watchFrames). */
export interface LiveStateSource {
  watchFrames(handlers: LiveWatchHandlers, deps?: LiveSseDeps): LiveWatchHandle;
}

export interface LiveStripGroupDesc {
  /** Манифестный контроль: обёртка [data-ctl]. */
  ctl?: string;
  /** Локальный контроль: обёртка [data-local]. */
  local?: string;
  /** Действие (задачи 15): обёртка [data-action]. */
  action?: string;
  /** Именованный слот без контекстного атрибута (напр. trigState). */
  slot?: string;
  /** Микроподпись группы над виджетом (линия 1). */
  label?: string;
}

export interface LiveStripRowDesc {
  /** 1 или 2; без поля — авто-нумерация строк зоны. */
  line?: 1 | 2;
  groups: readonly LiveStripGroupDesc[];
  /** Строка-хинт под группами (грамматика тайминга частоты). */
  note?: string;
}

export interface LiveStripZoneDesc {
  zone: string;
  label: string;
  aria?: string;
  rows: readonly LiveStripRowDesc[];
}

export interface LiveZoneMapEntry {
  zone: string;
  label: string;
  parts: HTMLElement[];
  controls: string[];
}

export interface LiveStripHandle {
  readonly root: HTMLElement;
  groupHost(key: string): HTMLElement;
  statusZone(): HTMLElement;
  zoneMap(): readonly LiveZoneMapEntry[];
  destroy(): void;
}

export function mountLiveStrip(zones: readonly LiveStripZoneDesc[]): LiveStripHandle {
  if (!Array.isArray(zones) || zones.length === 0) {
    throw new Error("mountLiveStrip: нужен непустой массив дескрипторов зон");
  }
  const root = el("div", { className: "lnt-live-strip", attrs: { "data-band": "" } });
  const lines: HTMLElement[] = [];
  const lineEl = (n: number): HTMLElement => {
    while (lines.length < n) {
      lines.push(
        el("div", {
          className: "lnt-live-line",
          attrs: { "data-band-line": String(lines.length + 1) },
        }),
      );
    }
    return lines[n - 1] as HTMLElement;
  };
  const hosts = new Map<string, HTMLElement>();
  const notes: HTMLElement[] = [];

  function buildGroup(group: LiveStripGroupDesc): HTMLElement {
    const attrs: Record<string, string> = {};
    let key = "";
    if (group.ctl !== undefined) {
      attrs["data-ctl"] = group.ctl;
      key = group.ctl;
    } else if (group.local !== undefined) {
      attrs["data-local"] = group.local;
      key = group.local;
    } else if (group.action !== undefined) {
      attrs["data-action"] = group.action;
      key = group.action;
    } else if (group.slot !== undefined) {
      attrs["data-slot"] = group.slot;
      key = group.slot;
    }
    const host = el("div", { className: "lnt-live-ctl", attrs });
    if (group.label !== undefined) {
      host.append(el("span", { className: "lnt-live-ctl-label", text: group.label }));
    }
    if (key !== "") hosts.set(key, host);
    return host;
  }

  for (const zone of zones) {
    let auto = 1;
    let first = true;
    for (const row of zone.rows) {
      const n = row.line ?? auto;
      auto = n + 1;
      const part = el("section", {
        className: `lnt-live-pzone${first ? "" : " lnt-live-pzone-cont"}${n > 1 ? " lnt-live-pzone-late" : ""}`,
        attrs: { "data-zone": zone.zone, "aria-label": zone.aria ?? zone.label },
      });
      if (first) {
        part.append(
          el("span", {
            className: "lnt-live-pzone-label",
            text: zone.label,
            attrs: { "aria-hidden": "true" },
          }),
        );
      }
      const prow = el("div", { className: "lnt-live-prow" });
      for (const group of row.groups) prow.append(buildGroup(group));
      part.append(prow);
      if (row.note !== undefined) {
        notes.push(
          el("p", {
            className: "lnt-live-zone-note",
            text: row.note,
            attrs: { "data-readonly": "" },
          }),
        );
      }
      lineEl(n).append(part);
      first = false;
    }
  }
  for (const line of lines) root.append(line);
  const statusZone = el("div", {
    className: "lnt-live-bandstatus",
    attrs: { "data-band-status": "" },
  });
  statusZone.append(...notes);
  root.append(statusZone);

  return {
    root,
    groupHost: (key) => {
      const host = hosts.get(key);
      if (host === undefined) throw new Error(`mountLiveStrip: нет группы «${key}» в манифесте`);
      return host;
    },
    statusZone: () => statusZone,
    // Автокарта зон для машинной проверки (AC2): читает ЖИВОЙ DOM.
    zoneMap: () => {
      const order: LiveZoneMapEntry[] = [];
      const byId = new Map<string, LiveZoneMapEntry>();
      for (const node of [...root.querySelectorAll<HTMLElement>("[data-zone]")]) {
        const id = node.dataset.zone;
        if (id === undefined) continue;
        let entry = byId.get(id);
        if (entry === undefined) {
          entry = {
            zone: id,
            label: node.getAttribute("aria-label") ?? id,
            parts: [],
            controls: [],
          };
          byId.set(id, entry);
          order.push(entry);
        }
        entry.parts.push(node);
        for (const ctl of [
          ...node.querySelectorAll<HTMLElement>("[data-ctl],[data-local],[data-action]"),
        ]) {
          const name = ctl.dataset.ctl ?? ctl.dataset.local ?? ctl.dataset.action;
          if (name !== undefined && !entry.controls.includes(name)) entry.controls.push(name);
        }
      }
      return order;
    },
    destroy: () => {
      root.remove();
    },
  };
}
