/** Контракт раскладки «Захват»: строки-футеры растут по содержимому, а не
 * обрезают его. Регрессия (замер 1440×900 и 1280×720): .statusbar задаёт
 * height:32px, .capture-job-actions наследует эту фиксированную высоту и
 * режет кнопку 44px — clientH 31 против scrollH 52, из-за чего
 * .capture-timeline тоже теряет 21px (166 против 187).
 *
 * jsdom не считает раскладку, поэтому контракт проверяется по каскаду:
 * реальные селекторы реальных CSS-файлов сопоставляются с реальным DOM. */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import type { JobSnapshot } from "../api/types-jobs";
import { el } from "../components/primitives/dom";
import { applySnapshot, initialTimeline } from "./jobTimeline";
import { createJobTimelineView } from "./jobTimelineView";

interface StyleRule {
  readonly selector: string;
  readonly body: string;
  readonly order: number;
}

/** Верхнеуровневые правила каскада; @-блоки (в т.ч. @media 767px) пропускаются. */
function topLevelRules(css: string, offset: number): StyleRule[] {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const rules: StyleRule[] = [];
  let index = 0;
  while (index < clean.length) {
    const open = clean.indexOf("{", index);
    if (open === -1) break;
    const prelude = clean.slice(index, open).trim();
    let depth = 1;
    let cursor = open + 1;
    while (cursor < clean.length && depth > 0) {
      if (clean[cursor] === "{") depth += 1;
      else if (clean[cursor] === "}") depth -= 1;
      cursor += 1;
    }
    if (!prelude.startsWith("@")) {
      rules.push({
        selector: prelude,
        body: clean.slice(open + 1, cursor - 1),
        order: offset + index,
      });
    }
    index = cursor;
  }
  return rules;
}

/** Специфичность id/класс/тег — достаточная для селекторов раздела. */
function specificity(selector: string): number {
  const ids = (selector.match(/#[\w-]+/g) ?? []).length;
  const classes = (selector.match(/[.:[][\w-]+/g) ?? []).length;
  const types = (selector.match(/(?:^|[\s>+~])[a-zA-Z][\w-]*/g) ?? []).length;
  return ids * 10000 + classes * 100 + types;
}

function declaration(body: string, property: string): string | null {
  const match = new RegExp(`(?:^|;)\\s*${property}\\s*:\\s*([^;]+)`).exec(body);
  const value = match?.[1];
  return value === undefined ? null : value.trim();
}

/** Чтение реального CSS раздела: корень vitest — frontend/, запуск из репо тоже. */
function readCss(relative: string): string {
  const roots = [
    resolve(process.cwd(), "src/capture"),
    resolve(process.cwd(), "frontend/src/capture"),
  ];
  for (const root of roots) {
    const path = resolve(root, relative);
    if (existsSync(path)) return readFileSync(path, "utf8");
  }
  throw new Error(`не найден CSS ${relative}`);
}

const SHEET: StyleRule[] = [
  ...topLevelRules(readCss("../shell/v6Shell.css"), 0),
  ...topLevelRules(readCss("./captureCore.css"), 1_000_000),
];

/** Выигравшее объявление свойства для элемента (специфичность, затем порядок). */
function effective(element: Element, property: string): string | null {
  let winner: string | null = null;
  let bestRank = -1;
  let bestOrder = -1;
  for (const rule of SHEET) {
    const value = declaration(rule.body, property);
    if (value === null) continue;
    for (const part of rule.selector.split(",")) {
      const selector = part.trim();
      if (selector === "" || !element.matches(selector)) continue;
      const rank = specificity(selector);
      if (rank > bestRank || (rank === bestRank && rule.order > bestOrder)) {
        winner = value;
        bestRank = rank;
        bestOrder = rule.order;
      }
    }
  }
  return winner;
}

const isFixedPx = (value: string | null): boolean => value !== null && /^-?[\d.]+px$/.test(value);

function snap(overrides: Partial<JobSnapshot>): JobSnapshot {
  return {
    schema_version: 1,
    version: 1,
    job_id: "job-1",
    kind: "capture",
    status: "queued",
    stage: "queued",
    series_index: null,
    series_total: null,
    written_sessions: [],
    result: null,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

/** Хронология внутри корня раздела — селекторы каскада scoped под .capture-view. */
function mountTimeline() {
  const view = createJobTimelineView({ onCancel: vi.fn(), onRetry: vi.fn() });
  const root = el("section", { className: "capture-view t-page" }, [view.root]);
  document.body.replaceChildren(root);
  return { view, root };
}

const requireEl = (root: Element, selector: string): HTMLElement => {
  const found = root.querySelector<HTMLElement>(selector);
  if (found === null) throw new Error(`нет ${selector}`);
  return found;
};

describe("захват: полоса действий задачи растёт по содержимому", () => {
  it("«.capture-job-actions» не несёт фиксированную высоту .statusbar", () => {
    // Given: смонтированная хронология без задачи
    const { view } = mountTimeline();
    view.update(initialTimeline);

    // When
    const actions = requireEl(view.root, ".capture-job-actions");
    const height = effective(actions, "height");

    // Then: фиксированные 32px режут кнопку отмены 44px (clientH 31 < scrollH 52)
    expect(
      isFixedPx(height),
      `обрезка снизу: .capture-job-actions получает height:${height} из .statusbar — кнопка «Отменить после текущей сессии» (44px) не помещается в фиксированную полосу`,
    ).toBe(false);
  });

  it("ритм полосы держится через min-height, а не height", () => {
    // Given
    const { view } = mountTimeline();
    view.update(initialTimeline);

    // When
    const actions = requireEl(view.root, ".capture-job-actions");

    // Then: 32px kit §5.5 остаются нижней границей, потолка нет
    expect(effective(actions, "min-height")).toBe("32px");
  });

  it("«.capture-timeline» не несёт фиксированную высоту", () => {
    // Given
    const { view } = mountTimeline();
    view.update(initialTimeline);

    // Then: панель считалась 166px при содержимом 187px
    expect(isFixedPx(effective(view.root, "height"))).toBe(false);
  });
});

describe("захват: непустое состояние задачи не обрезается", () => {
  it("при записанных сессиях и активной отмене полоса действий остаётся растяжимой", () => {
    // Given: живой снимок с сериями и записанными сессиями (без железа)
    const { view } = mountTimeline();
    view.update(
      applySnapshot(
        initialTimeline,
        snap({
          version: 2,
          status: "running",
          stage: "capturing",
          series_index: 2,
          series_total: 5,
          written_sessions: ["2026-09-05T10-00-00_rc_measurement", "2026-09-05T10-01-00_rc"],
        }),
      ),
    );

    // When: контейнеры с содержимым внутри хронологии
    const actions = requireEl(view.root, ".capture-job-actions");
    const written = requireEl(view.root, ".capture-job-written");

    // Then
    expect(view.root.textContent).toContain("Записанные сессии:");
    expect(isFixedPx(effective(actions, "height"))).toBe(false);
    expect(isFixedPx(effective(written, "height"))).toBe(false);
    expect(isFixedPx(effective(view.root, "height"))).toBe(false);
  });

  it("ни один переносящий flex-контейнер раздела не заперт фиксированной высотой", () => {
    // Given
    const { view, root } = mountTimeline();
    view.update(
      applySnapshot(initialTimeline, snap({ version: 2, status: "running", stage: "capturing" })),
    );

    // When: контейнер с flex-wrap:wrap обязан расти на вторую строку
    const locked = [...root.querySelectorAll<HTMLElement>("*")].filter(
      (node) => effective(node, "flex-wrap") === "wrap" && isFixedPx(effective(node, "height")),
    );

    // Then
    expect(
      locked.map((node) => node.className),
      "перенос строк невозможен при фиксированной высоте — содержимое уходит за границу",
    ).toEqual([]);
  });
});
