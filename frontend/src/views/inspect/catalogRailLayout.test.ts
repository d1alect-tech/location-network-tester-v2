/** Контракт раскладки рельса каталога на «#/inspect» (F-T14-01): левая колонка
 * прокручивается внутри себя, а не вытекает за фолд.
 *
 * Регрессия (живой замер 1440×900, 24 сессии → 30 строк): `.col-cat > .panel`
 * не владеет областью прокрутки, поэтому `table.tbl-cat` рисуется наружу —
 * 4 строки уходят до +92px ниже `div.view-container` (`overflow:hidden`,
 * bottom 867), а две из них (rect 814…843 и 843…872) накрывают полношириный
 * `.banner.banner-inline` «Сервер вернул ошибку.» (rect 834…867): глифы
 * накладываются и оба текста нечитаемы.
 *
 * jsdom не считает раскладку, поэтому контракт проверяется по каскаду:
 * реальные селекторы реальных CSS-файлов сопоставляются с реальным DOM. */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import type { CatalogSession } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { createCatalogColumn } from "./catalogColumn";
import { createPairState } from "./pairState";

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
      rules.push({ selector: prelude, body: clean.slice(open + 1, cursor - 1), order: offset + index });
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

/** Чтение реального CSS: корень vitest — frontend/, запуск из репо тоже. */
function readCss(relative: string): string {
  const roots = [
    resolve(process.cwd(), "src/views/inspect"),
    resolve(process.cwd(), "frontend/src/views/inspect"),
  ];
  for (const root of roots) {
    const path = resolve(root, relative);
    if (existsSync(path)) return readFileSync(path, "utf8");
  }
  throw new Error(`не найден CSS ${relative}`);
}

const SHEET: StyleRule[] = [
  ...topLevelRules(readCss("../../style.css"), 0),
  ...topLevelRules(readCss("../experiments/experimentsCore.css"), 1_000_000),
  ...topLevelRules(readCss("./v6.css"), 2_000_000),
];

/** `:has()` и прочие селекторы, не поддержанные jsdom, не должны ронять каскад. */
function safeMatches(element: Element, selector: string): boolean {
  try {
    return element.matches(selector);
  } catch {
    // no-excuse-ok: catch — граница движка селекторов jsdom
    return false;
  }
}

/** Выигравшее объявление одного из свойств (специфичность, затем порядок). */
function effectiveAny(element: Element, properties: readonly string[]): string | null {
  let winner: string | null = null;
  let bestRank = -1;
  let bestOrder = -1;
  for (const rule of SHEET) {
    for (const property of properties) {
      const value = declaration(rule.body, property);
      if (value === null) continue;
      for (const part of rule.selector.split(",")) {
        const selector = part.trim();
        if (selector === "" || !safeMatches(element, selector)) continue;
        const rank = specificity(selector);
        if (rank > bestRank || (rank === bestRank && rule.order >= bestOrder)) {
          winner = value;
          bestRank = rank;
          bestOrder = rule.order;
        }
      }
    }
  }
  return winner;
}

const effective = (element: Element, property: string): string | null =>
  effectiveAny(element, [property]);

/** Ось Y прокрутки: longhand `overflow-y` и shorthand `overflow` — один каскад. */
const scrollAxisY = (element: Element): string | null =>
  effectiveAny(element, ["overflow-y", "overflow"]);

const SCROLLABLE = new Set(["auto", "scroll", "overlay"]);
const owns = (value: string | null): boolean =>
  value !== null && SCROLLABLE.has(value.split(/\s+/)[0] ?? "");

function session(id: string, createdUtc: string, label: string): CatalogSession {
  return {
    id,
    health: "ok",
    created_utc: createdUtc,
    source: "hardware",
    session_type: "capture",
    profile: "lab",
    label,
  };
}

/** 24 сессии живого data-root — ровно то наполнение, что вскрыло F-T14-01. */
const SESSIONS: CatalogSession[] = Array.from({ length: 24 }, (_, index) =>
  session(
    `cap-2026080${index % 8}-0${index % 6}0000-${index}`,
    `2026-08-0${(index % 8) + 1}T1${index % 10}:00:00Z`,
    `сессия-${index}`,
  ),
);

const requireEl = (root: Element, selector: string): HTMLElement => {
  const found = root.querySelector<HTMLElement>(selector);
  if (found === null) throw new Error(`нет ${selector}`);
  return found;
};

/** Реальный рельс в реальной обвязке «#/inspect»: цепочка селекторов каскада. */
async function mountRail() {
  const column = createCatalogColumn({
    client: { catalogSessions: async () => ({ items: SESSIONS }) },
    pair: createPairState(),
    onPick: vi.fn(),
  });
  const colCat = el("div", { className: "col-cat" }, [column.root]);
  const body = el("div", { className: "app-body" }, [colCat, el("div", { className: "col-main" })]);
  const appV6 = el("div", { className: "app-v6" }, [body]);
  document.body.replaceChildren(el("div", { className: "view-container" }, [appV6]));
  await column.reload();
  return { appV6, body, colCat, panel: column.root };
}

describe("инспектор: рельс каталога прокручивается внутри своей колонки", () => {
  it("«.col-cat > .panel» владеет собственной областью прокрутки", async () => {
    // Given: рельс с наполнением живого data-root
    const { panel, colCat } = await mountRail();
    expect(colCat.querySelectorAll("tbody tr").length).toBeGreaterThan(24);

    // When
    const overflow = scrollAxisY(panel);

    // Then: без своей прокрутки таблица рисуется наружу и накрывает баннер
    expect(
      owns(overflow),
      `рельс каталога вытекает за фолд: .app-v6 .col-cat > .panel получает overflow-y:${overflow ?? "visible"} — 30 строк уходят до +92px ниже div.view-container (overflow:hidden, bottom 867) и накрывают .banner.banner-inline «Сервер вернул ошибку.» (rect 834…867)`,
    ).toBe(true);
  });

  it("прокрутку берёт панель, а не сама таблица: overflow к display:table не применяется", async () => {
    // Given
    const { panel, colCat } = await mountRail();

    // When
    const table = requireEl(colCat, "table.tbl-cat");

    // Then: <table> не создаёт scroll-контейнер, поэтому клип обязан быть на панели
    expect(
      scrollAxisY(table),
      "overflow на <table> игнорируется движком — правило здесь бесполезно",
    ).toBeNull();
    expect(owns(scrollAxisY(panel))).toBe(true);
  });

  it("цепочка flex/grid обнуляет min-height — иначе клип невозможен", async () => {
    // Given: .app-v6 → .app-body → .col-cat → .panel
    const { appV6, body, colCat, panel } = await mountRail();

    // Then: любой ненулевой min-height в цепочке распирает колонку под фолд
    for (const node of [appV6, body, colCat, panel]) {
      expect(
        effective(node, "min-height"),
        `${node.className}: min-height обязан быть 0, иначе flex/grid-ребёнок не сжимается и рельс вылезает за .view-container`,
      ).toBe("0");
    }
  });
});
