/** Геометрия живых приборных вкладок (задача 17 плана scope-sa-round4):
 * общие измерения и ассерты для scopeGeometry.spec.ts / saGeometry.spec.ts
 * и красной валидации спека (selfcheck). Один и тот же код
 * box-intersection гоняют и основной прогон, и selfcheck — иначе красный
 * self-check ничего бы не доказывал (урок задачи 6 плана r3).
 *
 * Ассерты — перенос прототипной геометрия-машины (задача 9,
 * .omo/prototype/scope/geometry.r4.spec.ts) на продукт :4101:
 *   (a) docScroll == docClient (+1 допуск на субпиксели) — ДОСЛОВНЫЙ
 *       паттерн замороженного frontend/src/showcase-round2/
 *       round2-v6.spec.ts:118-121 (файл заморожен, копия): документ И
 *       главный скроллящийся контейнер вида (#view-container — аналог
 *       .col-main витрины R2) не прокручиваются; зона-карта 13 §9:
 *       «overflow = скролл = красный AC1 задачи 17»;
 *   (b) per-zone box-intersection полосы liveStrip: попарно ноль
 *       пересечений (допуск 0.5px; класс дефекта — перекрытия ≥ 6px,
 *       шрам репо) + зоны целиком в видимом окне вида + карта зон ==
 *       манифесту вкладки (карта не может разойтись с DOM);
 *   (c) интерактивные цели ≥ 44×44 (--lnt-touch-target-min); чекбокс
 *       внутри label меряется по label — label[for] это единая зона
 *       клика (фактическая цель), не сам 16px-инпут;
 *   (d) pure-ридауты [data-readonly] → pointer-events: none;
 *   (e) высоты: полоса ≤ 150 (цель) / 238 (аварийный потолок — замер
 *       спайка r3, architect §3.4), idle и running; экран-доминанта —
 *       AC3: stage ≥ 60 % полезной высоты при 1280×625 (полезная высота
 *       — клиентская высота #view-container; stage — сигнальные окна
 *       вкладки: экран и фигура развёртки).
 *
 * Никаких фиксированных пауз: settle — наблюдаемые сигналы (видимость
 * воркспейса и полосы, document.fonts.ready, счётчик кадров/свипов
 * растёт после Run). */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect } from "@playwright/test";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** Допуск на субпиксельное округление getBoundingClientRect (0.5px);
 * класс дефекта, который ловим — перекрытия зон ≥ 6px (шрам репо). */
export const EPS = 0.5;
export const DEFECT_CLASS_PX = 6;

/** (e) высоты: полоса ≤ 150 (цель); 238 — аварийный потолок (замер спайка
 * r3: живые виджеты без компакт-режима; architect §3.4 порядок упаковки). */
export const BAND_TARGET_PX = 150;
export const BAND_CEILING_PX = 238;

/** AC3 «экран-доминанта»: stage ≥ 60 % полезной высоты при 1280×625. */
export const STAGE_RATIO_MIN = 0.6;
/** Tight-вьюпорт, на котором план требует экран-доминанту (AC3). */
export const VIEW_TIGHT_HEIGHT = 625;

/** A11y floor: цели ≥ 44×44 (--lnt-touch-target-min). */
export const TARGET_MIN_PX = 44;

export const LIVE_BASE = "http://127.0.0.1:4101/static/v2/";

export interface ZoneBox {
  zone: string;
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface ScrollBox {
  scrollH: number;
  clientH: number;
  scrollW: number;
  clientW: number;
}

export interface BoxRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface LiveGeometrySnapshot {
  doc: ScrollBox;
  view: ScrollBox;
  viewBox: BoxRect;
  band: BoxRect;
  statusHeight: number;
  line1Height: number;
  line2Height: number;
  zones: ZoneBox[];
  screens: Record<string, number>;
  viewportW: number;
  viewportH: number;
}

/** Вкладка для геометрия-гейта; зоны — копия манифеста полосы вкладки. */
export interface LiveTabSpec {
  readonly route: "scope" | "sa";
  readonly title: string;
  readonly workspace: string;
  readonly runButton: string;
  /** Счётчик живого потока (наблюдаемый settle-сигнал после Run). */
  readonly counter: string;
  /** Зоны манифеста вкладки (SCOPE_STRIP_ZONES / SA_STRIP_ZONES). */
  readonly zones: readonly string[];
  /** Число [data-zone]-частей (ТРИГГ scope продолжается в линию 2). */
  readonly zoneParts: number;
  /** Селекторы сигнальных окон вкладки (экран-доминанта, AC3). */
  readonly screens: readonly string[];
}

/** «Осциллограф»: манифест scopeStripManifest.ts — vert/horiz/trig/run/
 * measure; экран + фигура развёртки — два сигнальных окна продукта. */
export const SCOPE_LIVE_TAB: LiveTabSpec = {
  route: "scope",
  title: "Осциллограф",
  workspace: ".lnt-scope-workspace",
  runButton: "#lnt-scope-run",
  counter: ".lnt-scope-frame-count",
  zones: ["vert", "horiz", "trig", "run", "measure"],
  zoneParts: 6,
  screens: [".lnt-scope-viewport", ".lnt-scope-figure"],
};

/** «Спектроанализатор»: манифест SA_STRIP_ZONES (saStrip.ts) — 6 зон. */
export const SA_LIVE_TAB: LiveTabSpec = {
  route: "sa",
  title: "Спектроанализатор",
  workspace: ".lnt-sa-workspace",
  runButton: "#lnt-sa-run",
  counter: ".lnt-sa-sweep",
  zones: ["span", "rbw", "run", "traces", "markers", "peaks"],
  zoneParts: 6,
  screens: [".lnt-sa-figure"],
};

export interface ViewportSpec {
  readonly width: number;
  readonly height: number;
}

/** Вьюпорты задачи 17: {1280×720, 1920×1080, 1280×625 tight}. */
export const LIVE_VIEWPORTS: readonly ViewportSpec[] = [
  { width: 1280, height: 720 },
  { width: 1920, height: 1080 },
  { width: 1280, height: 625 },
];

/** Открыть вкладку: вьюпорт ДО навигации, settle по наблюдаемым сигналам
 * (воркспейс и полоса видимы, шрифты готовы) — без фиксированных пауз. */
export async function openLiveTab(page: Page, tab: LiveTabSpec, vp: ViewportSpec): Promise<void> {
  await page.setViewportSize({ width: vp.width, height: vp.height });
  await page.goto(`${LIVE_BASE}#/${tab.route}`);
  await expect(page.locator(tab.workspace)).toBeVisible();
  await expect(page.locator(".lnt-live-strip")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

/** Снимок геометрии вкладки: документ, окно вида, полоса, зоны, экраны. */
export async function collectLiveGeometry(
  page: Page,
  tab: LiveTabSpec,
): Promise<LiveGeometrySnapshot> {
  return page.evaluate(
    (spec: { screens: string[] }) => {
      const round = (n: number): number => Math.round(n * 10) / 10;
      const rect = (el: Element): BoxRect => {
        const r = el.getBoundingClientRect();
        return { x: round(r.x), y: round(r.y), width: round(r.width), height: round(r.height) };
      };
      const doc = document.documentElement;
      const view = document.querySelector("#view-container");
      if (!(view instanceof HTMLElement)) throw new Error("нет #view-container");
      const band = document.querySelector("[data-band]");
      if (!(band instanceof HTMLElement)) throw new Error("нет полосы [data-band]");
      const zones: ZoneBox[] = [];
      for (const node of document.querySelectorAll("[data-band] [data-zone]")) {
        const r = node.getBoundingClientRect();
        zones.push({
          zone: node.getAttribute("data-zone") ?? "",
          left: round(r.left),
          top: round(r.top),
          right: round(r.right),
          bottom: round(r.bottom),
        });
      }
      const screens: Record<string, number> = {};
      for (const sel of spec.screens) {
        const node = document.querySelector(sel);
        screens[sel] = node === null ? 0 : round(node.getBoundingClientRect().height);
      }
      const line1 = document.querySelector('[data-band-line="1"]');
      const line2 = document.querySelector('[data-band-line="2"]');
      const status = document.querySelector("[data-band-status]");
      return {
        doc: {
          scrollH: doc.scrollHeight,
          clientH: doc.clientHeight,
          scrollW: doc.scrollWidth,
          clientW: doc.clientWidth,
        },
        view: {
          scrollH: view.scrollHeight,
          clientH: view.clientHeight,
          scrollW: view.scrollWidth,
          clientW: view.clientWidth,
        },
        viewBox: rect(view),
        band: rect(band),
        statusHeight: status === null ? 0 : round(status.getBoundingClientRect().height),
        line1Height: line1 === null ? 0 : round(line1.getBoundingClientRect().height),
        line2Height: line2 === null ? 0 : round(line2.getBoundingClientRect().height),
        zones,
        screens,
        viewportW: window.innerWidth,
        viewportH: window.innerHeight,
      };
    },
    { screens: [...tab.screens] },
  );
}

/** (a) docScroll == docClient — паттерн round2-v6.spec.ts:118-121
 * (заморожен, копия; +1 на субпиксели), документ И окно вида:
 * вкладка обязана целиком жить в одном окне без прокрутки. */
export function collectScrollViolations(geo: LiveGeometrySnapshot): string[] {
  const bad: string[] = [];
  if (geo.doc.scrollH > geo.doc.clientH + 1) {
    bad.push(
      `(a) прокрутка документа: docScroll ${geo.doc.scrollH} > docClient ${geo.doc.clientH}`,
    );
  }
  if (geo.doc.scrollW > geo.doc.clientW + 1) {
    bad.push(
      `(a) горизонтальный выход документа: docScrollW ${geo.doc.scrollW} > docClientW ${geo.doc.clientW}`,
    );
  }
  if (geo.view.scrollH > geo.view.clientH + 1) {
    bad.push(
      `(a) прокрутка вида #view-container: viewScroll ${geo.view.scrollH} > viewClient ${geo.view.clientH} — контент не влезает в окно (AC1)`,
    );
  }
  if (geo.view.scrollW > geo.view.clientW + 1) {
    bad.push(
      `(a) горизонтальный выход вида: viewScrollW ${geo.view.scrollW} > viewClientW ${geo.view.clientW}`,
    );
  }
  return bad;
}

/** (b) карта зон == манифесту вкладки: карта не может разойтись с DOM. */
export function collectZoneMapViolations(geo: LiveGeometrySnapshot, tab: LiveTabSpec): string[] {
  const bad: string[] = [];
  const unique = [...new Set(geo.zones.map((z) => z.zone))];
  const expected = [...tab.zones];
  const sameSet =
    unique.length === expected.length && expected.every((zone) => unique.includes(zone));
  if (!sameSet) {
    bad.push(
      `(b) карта зон ≠ манифесту: DOM [${unique.join(", ")}] против манифеста [${expected.join(", ")}]`,
    );
  }
  if (geo.zones.length !== tab.zoneParts) {
    bad.push(`(b) частей зон [data-zone] ${geo.zones.length} ≠ ${tab.zoneParts} по манифесту`);
  }
  return bad;
}

/** (b) per-zone box-intersection: попарно ноль пересечений (допуск 0.5px;
 * класс дефекта — перекрытия ≥ 6px, шрам репо: 6px-overlap однажды
 * объявили «нет пересечений»). Тот же код гоняет selfcheck (AC16). */
export function collectZoneOverlaps(geo: LiveGeometrySnapshot): string[] {
  const overlaps: string[] = [];
  for (let i = 0; i < geo.zones.length; i += 1) {
    for (let j = i + 1; j < geo.zones.length; j += 1) {
      const a = geo.zones[i]!;
      const b = geo.zones[j]!;
      const ow = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const oh = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ow > EPS && oh > EPS) {
        overlaps.push(
          `(b) пересечение зон ${a.zone} ∩ ${b.zone}: ${ow.toFixed(1)}×${oh.toFixed(1)} px (класс дефекта ≥ ${DEFECT_CLASS_PX}px)`,
        );
      }
    }
  }
  return overlaps;
}

/** (b) зоны целиком в видимом окне вида: полоса не ниже первого экрана. */
export function collectZoneEscapeViolations(geo: LiveGeometrySnapshot): string[] {
  const bad: string[] = [];
  const viewBottom = geo.viewBox.y + geo.viewBox.height;
  const viewRight = geo.viewBox.x + geo.viewBox.width;
  for (const z of geo.zones) {
    if (z.left < geo.viewBox.x - EPS) {
      bad.push(`(b) зона ${z.zone}: left ${z.left} за левым краем окна вида ${geo.viewBox.x}`);
    }
    if (z.top < geo.viewBox.y - EPS) {
      bad.push(`(b) зона ${z.zone}: top ${z.top} за верхним краем окна вида ${geo.viewBox.y}`);
    }
    if (z.right > viewRight + EPS) {
      bad.push(`(b) зона ${z.zone}: right ${z.right} > правого края окна вида ${viewRight}`);
    }
    if (z.bottom > viewBottom + EPS) {
      bad.push(
        `(b) зона ${z.zone}: bottom ${z.bottom} > низа окна вида ${viewBottom} — полоса ниже первого экрана`,
      );
    }
  }
  return bad;
}

/** (c) интерактивные цели полосы ≥ 44×44: button/input/select и роли;
 * чекбокс/радио меряется по родительскому label[for] — единая зона клика. */
export async function collectTargetViolations(page: Page): Promise<string[]> {
  return page.evaluate((minPx: number) => {
    const bad: string[] = [];
    const nodes = document.querySelectorAll(
      "[data-band] button, [data-band] input, [data-band] select, " +
        "[data-band] [role='switch'], [data-band] [role='spinbutton'], [data-band] [role='slider']",
    );
    for (const node of nodes) {
      if (node.getClientRects().length === 0) continue; /* скрытые не в счёт */
      const el = node;
      const boxInput =
        el instanceof HTMLInputElement && (el.type === "checkbox" || el.type === "radio");
      const label = boxInput ? el.closest("label") : null;
      const measure = label instanceof HTMLElement ? label : el;
      const r = measure.getBoundingClientRect();
      const name =
        el.getAttribute("data-value") ??
        el.getAttribute("aria-label") ??
        el.getAttribute("data-sa-trace") ??
        el.id ??
        el.tagName;
      if (r.width < minPx - 0.5 || r.height < minPx - 0.5) {
        bad.push(`(c) цель «${name}»: ${r.width.toFixed(1)}×${r.height.toFixed(1)} < ${minPx}`);
      }
    }
    return bad;
  }, TARGET_MIN_PX);
}

/** (d) pure-ридауты [data-readonly] → pointer-events: none. */
export async function collectReadonlyViolations(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const bad: string[] = [];
    for (const node of document.querySelectorAll("[data-band] [data-readonly]")) {
      if (node.getClientRects().length === 0) continue; /* скрытые не в счёт */
      const pe = getComputedStyle(node).pointerEvents;
      if (pe !== "none") {
        const el = node;
        bad.push(`(d) ридаут «${el.className || el.tagName}»: pointer-events: ${pe}`);
      }
    }
    return bad;
  });
}

/** (e) высоты: полоса ≤ 150 (цель; аварийный потолок 238 — замер спайка
 * r3): полоса не расширяется, не влезающее вырезается (architect §3.4). */
export function collectBandHeightViolations(
  geo: LiveGeometrySnapshot,
  state: "idle" | "running",
): string[] {
  if (geo.band.height > BAND_TARGET_PX) {
    return [
      `(e) полоса (${state}): ${geo.band.height}px > ${BAND_TARGET_PX} (цель; аварийный потолок ${BAND_CEILING_PX}px)`,
    ];
  }
  return [];
}

/** (e) экран-доминанта (AC3): при 1280×625 stage ≥ 60 % полезной высоты;
 * stage — сумма высот сигнальных окон вкладки, полезная высота — клиентская
 * высота #view-container. Экран обязана существовать на любом вьюпорте. */
export function collectScreenDominanceViolations(
  geo: LiveGeometrySnapshot,
  tab: LiveTabSpec,
): string[] {
  const bad: string[] = [];
  let stage = 0;
  for (const sel of tab.screens) {
    const h = geo.screens[sel] ?? 0;
    if (h <= 0) {
      bad.push(`(e) сигнальное окно ${sel} не найдено или вырождено`);
      continue;
    }
    stage += h;
  }
  if (geo.viewportH === VIEW_TIGHT_HEIGHT) {
    const ratio = stage / geo.view.clientH;
    if (ratio < STAGE_RATIO_MIN) {
      bad.push(
        `(e) экран-доминанта (AC3, 1280×625): stage ${stage}px = ${Math.round(ratio * 1000) / 10}% полезной высоты ${geo.view.clientH}px < ${STAGE_RATIO_MIN * 100}%`,
      );
    }
  }
  return bad;
}

/** Строка высот для квитанции (heights.json, инкрементально). */
export function liveGeometryRow(
  geo: LiveGeometrySnapshot,
  state: "idle" | "running",
): Record<string, number | string | boolean> {
  const stage = Object.values(geo.screens).reduce((sum, h) => sum + h, 0);
  return {
    state,
    band: geo.band.height,
    bandY: geo.band.y,
    status: geo.statusHeight,
    line1: geo.line1Height,
    line2: geo.line2Height,
    docScroll: geo.doc.scrollH,
    docClient: geo.doc.clientH,
    viewScroll: geo.view.scrollH,
    viewClient: geo.view.clientH,
    zoneParts: geo.zones.length,
    screens: Object.entries(geo.screens)
      .map(([sel, h]) => `${sel}=${h}`)
      .join(" "),
    stageSum: stage,
    stageRatio: Math.round((stage / geo.view.clientH) * 1000) / 1000,
    bandTarget: geo.band.height <= BAND_TARGET_PX,
    viewport: `${geo.viewportW}x${geo.viewportH}`,
  };
}

/** Инкрементальная запись строки высот в квитанцию задачи 17 (ВНЕ
 * outputDir: playwright чистит outputDir при каждом запуске; этот файл
 * пишем сами, паттерн recordHeights задачи 9). Прогоны сериальны (workers 1). */
export function recordLiveGeometryRow(
  key: string,
  row: Record<string, number | string | boolean>,
): void {
  const dir = resolve(__dirname, "../../../.omo/evidence/scope-sa-round4/task-17");
  const file = join(dir, "heights.json");
  let all: Record<string, Record<string, number | string | boolean>> = {};
  try {
    all = JSON.parse(readFileSync(file, "utf8")) as Record<
      string,
      Record<string, number | string | boolean>
    >;
  } catch {
    /* первый прогон — файла ещё нет */
  }
  all[key] = row;
  const sorted: Record<string, Record<string, number | string | boolean>> = {};
  for (const k of Object.keys(all).sort()) sorted[k] = all[k]!;
  mkdirSync(dir, { recursive: true });
  writeFileSync(file, `${JSON.stringify(sorted, null, 2)}\n`, "utf8");
}

/** Полный геометрия-гейт одной комбинации вкладка × вьюпорт:
 * idle-измерение и все ассерты (a)-(e), затем живой захват (Run,
 * settle по счётчику кадров/свипов) и повторный гейт высоты полосы.
 * Нарушения собираются ВСЕ до первого падения — красный лог несёт
 * полную картину, а не первый промах. */
export async function runLiveGeometryGate(
  page: Page,
  tab: LiveTabSpec,
  vp: ViewportSpec,
  record: (key: string, row: Record<string, number | string | boolean>) => void,
): Promise<void> {
  await openLiveTab(page, tab, vp);
  const idle = await collectLiveGeometry(page, tab);
  const violations: string[] = [
    ...collectScrollViolations(idle),
    ...collectZoneMapViolations(idle, tab),
    ...collectZoneOverlaps(idle),
    ...collectZoneEscapeViolations(idle),
    ...collectBandHeightViolations(idle, "idle"),
    ...collectScreenDominanceViolations(idle, tab),
    ...(await collectTargetViolations(page)),
    ...(await collectReadonlyViolations(page)),
  ];
  record(`${tab.route}-${vp.width}x${vp.height}-idle`, liveGeometryRow(idle, "idle"));

  // Живой захват: полоса не растёт при running (settle — счётчик растёт).
  await page.locator(tab.runButton).click();
  const counter = page.locator(tab.counter);
  await expect(counter).not.toHaveText("—");
  const first = (await counter.textContent()) ?? "";
  await expect(counter).not.toHaveText(first);
  const running = await collectLiveGeometry(page, tab);
  violations.push(...collectBandHeightViolations(running, "running"));
  record(`${tab.route}-${vp.width}x${vp.height}-running`, liveGeometryRow(running, "running"));

  expect(
    violations,
    `геометрия вкладки «${tab.title}» @ ${vp.width}×${vp.height} (${violations.length} нарушений)`,
  ).toEqual([]);
}
