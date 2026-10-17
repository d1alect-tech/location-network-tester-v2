/** Задача r5-7 RED: словарь моушена живых вкладок — планка emil-design-eng.
 * Ассерты по css-источникам (liveStrip.css, views/scope/*.css, views/sa/*.css,
 * style.css): токены press на .app-v6-скоупе (никогда :root) с запиненными
 * ЗНАЧЕНИЯМИ; ноль сырых 120ms/cubic-bezier( вне строк-определений токенов;
 * каждое :active-правило с transform — на var(--lnt-press-scale); длительности
 * ≤ 300 мс; reduced-motion сохраняет color/opacity и гасит только движение.
 * Пин значений: изменение токена требует обновить спеку тем же коммитом. */

import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";

const read = (rel: string): string => readFileSync(`${process.cwd()}/src/${rel}`, "utf8");

/** css-файлы живой поверхности: полоса, обе вкладки, корневой style. */
const FILES: ReadonlyArray<[string, string]> = [
  ["liveStrip.css", "components/liveStrip/liveStrip.css"],
  ["style.css", "style.css"],
  ["v6Shell.css", "shell/v6Shell.css"],
  ...readdirSync(`${process.cwd()}/src/views/scope`)
    .filter((name) => name.endsWith(".css"))
    .map((name) => [`scope/${name}`, `views/scope/${name}`] as [string, string]),
  ...readdirSync(`${process.cwd()}/src/views/sa`)
    .filter((name) => name.endsWith(".css"))
    .map((name) => [`sa/${name}`, `views/sa/${name}`] as [string, string]),
];

const stripComments = (text: string): string => text.replace(/\/\*[\s\S]*?\*\//g, "");

interface StyleRule {
  readonly selector: string;
  readonly decls: string;
}

/** Плоские пары «селектор { декларации }»; обёртки @media/@keyframes
 * пропускаются, вложенные правила читаются как отдельные пары. */
function styleRules(text: string): StyleRule[] {
  const out: StyleRule[] = [];
  for (const match of stripComments(text).matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selector = (match[1] ?? "").trim();
    if (selector.startsWith("@")) continue;
    out.push({ selector, decls: match[2] ?? "" });
  }
  return out;
}

/** Тело @media-блока prefers-reduced-motion (подсчёт фигурных скобок). */
function reducedMotionBlock(text: string): string {
  const src = stripComments(text);
  const at = src.indexOf("@media (prefers-reduced-motion: reduce)");
  if (at === -1) return "";
  let depth = 0;
  let body = "";
  for (const ch of src.slice(at)) {
    if (ch === "{") {
      depth += 1;
      continue;
    }
    if (ch === "}") {
      depth -= 1;
      if (depth === 0) return body;
      continue;
    }
    if (depth > 0) body += ch;
  }
  return body;
}

/** Селекторы :active-press-правил (transform через токен масштаба). */
const pressSelectors = (text: string): string[] =>
  styleRules(text)
    .filter(
      (rule) => rule.selector.includes(":active") && rule.decls.includes("var(--lnt-press-scale)"),
    )
    .map((rule) => rule.selector);

describe("motionTokens: словарь моушена живых вкладок (r5-7)", () => {
  const styleCss = read("style.css");
  const stripCss = read("components/liveStrip/liveStrip.css");

  it("токены press объявлены в .app-v6-скоупе (не :root), значения запинены", () => {
    const css = stripComments(styleCss);
    expect(css).toMatch(/\.app-v6[^{}]*\{[^}]*--lnt-t-press:\s*160ms/);
    expect(css).toMatch(/\.app-v6[^{}]*\{[^}]*--lnt-press-scale:\s*0\.97/);
    expect(css).toMatch(
      /\.app-v6[^{}]*\{[^}]*--lnt-ease-out:\s*cubic-bezier\(0\.23, 1, 0\.32, 1\)/,
    );
    expect(css).not.toMatch(/:root[^{}]*\{[^}]*--lnt-(t-press|press-scale)/);
  });

  it("ноль сырых 120ms/cubic-bezier( вне строк-определений токенов", () => {
    for (const [name, rel] of FILES) {
      const text = read(rel);
      for (const line of stripComments(text).split("\n")) {
        if (!/120ms|cubic-bezier\(/.test(line)) continue;
        // Разрешение — только строка-объявление кастомного свойства (токен).
        expect(line, `${name}: ${line.trim()}`).toMatch(/^\s*--[a-z0-9-]+\s*:/);
      }
    }
  });

  it("каждое :active-правило с transform ссылается на var(--lnt-press-scale)", () => {
    for (const [name, rel] of FILES) {
      const text = read(rel);
      for (const rule of styleRules(text)) {
        if (!rule.selector.includes(":active")) continue;
        // Не-press :active (cursor: grabbing у линии триггера) transform не несёт.
        if (!/transform\s*:/.test(rule.decls)) continue;
        expect(rule.decls, `${name}: ${rule.selector}`).toContain("var(--lnt-press-scale)");
      }
    }
  });

  it("семейства контролов обеих вкладок несут press-правила на токене", () => {
    const strip = pressSelectors(stripCss);
    // Полоса: run-кластер (обе вкладки), сегменты В/дел/RBW, сегменты
    // триггера, чип частоты, степперы, действия (автосет/сброс), тумблеры SA.
    expect(strip.some((s) => s.includes("lnt-live-runctl > button:active"))).toBe(true);
    expect(strip.some((s) => s.includes("lnt-live-seg-btn:active"))).toBe(true);
    expect(strip.some((s) => s.includes("lnt-scope-seg-btn:active"))).toBe(true);
    expect(strip.some((s) => s.includes("lnt-live-chip-btn:active"))).toBe(true);
    expect(strip.some((s) => s.includes("lnt-live-step-btn:active"))).toBe(true);
    expect(strip.some((s) => s.includes("lnt-live-action-btn:active"))).toBe(true);
    expect(strip.some((s) => s.includes("lnt-sa-check:active"))).toBe(true);
    // Воркспейс SA: маркеры/пики (.btn), селекторы окно/детектор (.ctl).
    const sa = pressSelectors(read("views/sa/sa.css"));
    expect(sa.some((s) => s.includes(".btn:active"))).toBe(true);
    expect(sa.some((s) => s.includes(".ctl:active"))).toBe(true);
    expect(sa.some((s) => s.includes("lnt-sa-check:active"))).toBe(true);
    // Воркспейс scope: кнопки, сегменты триггера, тумблеры инверсии.
    const scope = pressSelectors(read("views/scope/scope.css"));
    expect(scope.some((s) => s.includes(".btn:active"))).toBe(true);
    expect(scope.some((s) => s.includes("lnt-scope-seg-btn:active"))).toBe(true);
    expect(scope.some((s) => s.includes("lnt-scope-check:active"))).toBe(true);
  });

  it("reduced-motion сохраняет color/opacity, гасит только движение", () => {
    for (const [name, text] of [
      ["style.css", styleCss],
      ["liveStrip.css", stripCss],
      ["v6Shell.css", read("shell/v6Shell.css")],
    ] as const) {
      const block = reducedMotionBlock(text);
      expect(block.length, `${name}: нет reduced-motion-блока`).toBeGreaterThan(0);
      expect(block, name).not.toMatch(/transition:\s*none/);
      expect(block, name).toMatch(/transition-property:[^;}]*\bcolor\b/);
      expect(block, name).toMatch(/transition-property:[^;}]*\bopacity\b/);
      // Press остаётся мгновенным состоянием, не удаляется.
      expect(block, name).not.toMatch(/transform:\s*none/);
    }
  });

  it("длительности в живой поверхности не превышают 300 мс", () => {
    for (const [name, rel] of FILES) {
      const text = read(rel);
      for (const match of stripComments(text).matchAll(/(\d+)ms/g)) {
        expect(Number(match[1]), `${name}: ${match[0]}`).toBeLessThanOrEqual(300);
      }
    }
  });

  it("ad-hoc :active-сайты (captureForms/settingsBase) мигрированы на токен", () => {
    for (const rel of ["capture/captureForms.css", "views/settings/settingsBase.css"]) {
      const active = styleRules(read(rel)).filter((rule) => rule.selector.includes(":active"));
      expect(active.length, rel).toBeGreaterThan(0);
      for (const rule of active) {
        expect(rule.decls, `${rel}: ${rule.selector}`).toContain("var(--lnt-press-scale)");
      }
    }
  });
});

/** Задача r5-9 (E5/E7): клавиатурный флип состояния мгновенен — цвет-транзишен
 * живёт ТОЛЬКО в :hover-правиле (обратная связь указателя), базовое правило
 * сегментов/run-клавиш несёт только press-transform. Hover-обратная связь
 * всей полосы/воркспейса scope гейтится @media (hover:hover)+(pointer:fine). */

/** :hover-правила вне гейта @media (hover: hover) and (pointer: fine). */
function hoverGateViolations(text: string): string[] {
  const src = stripComments(text);
  const bad: string[] = [];
  const stack: string[] = [];
  let prelude = "";
  for (const ch of src) {
    if (ch === "{") {
      stack.push(prelude.trim());
      prelude = "";
      continue;
    }
    if (ch === "}") {
      const opened = stack.pop() ?? "";
      if (!opened.startsWith("@") && opened.includes(":hover")) {
        const gated = stack.some(
          (p) => /@media[^{]*hover:\s*hover/.test(p) && /@media[^{]*pointer:\s*fine/.test(p),
        );
        if (!gated) bad.push(opened.replace(/\s+/g, " "));
      }
      prelude = "";
      continue;
    }
    prelude += ch;
  }
  return bad;
}

/** Базовые правила (без псевдоклассов) по вхождению селектора. */
const baseRules = (text: string, needle: string): StyleRule[] =>
  styleRules(text).filter(
    (rule) =>
      rule.selector.includes(needle) &&
      !/:[a-z-]/.test(rule.selector.replace(/::?(before|after)/g, "")),
  );

describe("motionTokens: планка emil r5-9 (E5 клавиатура, E7 hover-гейт)", () => {
  const stripCssLocal = read("components/liveStrip/liveStrip.css");
  const scopeCss = read("views/scope/scope.css");
  const waveCss = read("views/scope/scopeWaveform.css");
  const saCss = read("views/sa/sa.css");

  it("E5: базовые правила флип-контролов (сегменты, run-клавиши) без color-транзишена", () => {
    for (const [name, text, needle] of [
      ["liveStrip.css", stripCssLocal, ".lnt-live-seg-btn"],
      ["liveStrip.css", stripCssLocal, ".lnt-live-runctl > button"],
      ["liveStrip.css", stripCssLocal, ".lnt-scope-seg-btn"],
      ["scope.css", scopeCss, ".lnt-scope-seg-btn"],
    ] as const) {
      const rules = baseRules(text, needle);
      expect(rules.length, `${name}: нет базового правила ${needle}`).toBeGreaterThan(0);
      for (const rule of rules) {
        expect(
          /transition[^;]*background|transition[^;]*border-color/.test(rule.decls),
          `${name}: ${rule.selector} — color-транзишен в базовом правиле`,
        ).toBe(false);
      }
    }
  });

  it("E5: color-транзишен сегментов живёт в :hover-правиле (указатель, не клавиатура)", () => {
    const hover = styleRules(stripCssLocal).filter((rule) =>
      rule.selector.includes(".lnt-live-seg-btn:hover"),
    );
    expect(hover.length, "нет :hover-правила сегментов").toBeGreaterThan(0);
    expect(hover.some((rule) => /transition[^;]*background/.test(rule.decls))).toBe(true);
    const trigHover = styleRules(stripCssLocal).filter((rule) =>
      rule.selector.includes(".lnt-scope-seg-btn:hover"),
    );
    expect(trigHover.some((rule) => /transition[^;]*background/.test(rule.decls))).toBe(true);
  });

  it("E7: каждое :hover-правило полосы и воркспейсов обеих вкладок — внутри hover-гейта", () => {
    for (const [name, text] of [
      ["liveStrip.css", stripCssLocal],
      ["scope.css", scopeCss],
      ["scopeWaveform.css", waveCss],
      ["sa.css", saCss],
      ["style.css", read("style.css")],
      ["v6Shell.css", read("shell/v6Shell.css")],
    ] as const) {
      const ungated = hoverGateViolations(text);
      expect(ungated, `${name}: :hover вне @media (hover: hover) and (pointer: fine)`).toEqual([]);
    }
  });
});

/** Задача r5-11: хром — словарь моушена доведён до таббара оболочки и app-css
 * (press-токены вместо литералов, hover-гейт E7, политика reduced-motion),
 * плюс net-removal полосы по частотной таблице emil: свойство transition без
 * анимируемого события (меню мгновенно, hover — только border-color,
 * :disabled — opacity) удаляется, а не комментируется. */

describe("motionTokens: хром r5-11 (таббар, net-removal полосы)", () => {
  const shellCss = read("shell/v6Shell.css");
  const stripCssLocal = read("components/liveStrip/liveStrip.css");

  it("r5-11: press таббара — токены словаря (scale, длительность), не литералы", () => {
    const active = styleRules(shellCss).filter((rule) =>
      rule.selector.includes(".hdr .tabbar .snav-item:active"),
    );
    expect(active.length, "нет :active-правила таббара").toBeGreaterThan(0);
    for (const rule of active) {
      expect(rule.decls).toContain("scale(var(--lnt-press-scale))");
    }
    const base = baseRules(shellCss, ".hdr .tabbar .snav-item");
    expect(base.length, "нет базового правила таббара").toBeGreaterThan(0);
    // Press-семейство — t-press 160ms ease-out (словарь r5-7), не motion-fast.
    expect(
      base.some((rule) =>
        /transform\s+var\(--lnt-t-press\)\s+var\(--lnt-ease-out\)/.test(rule.decls),
      ),
    ).toBe(true);
    expect(base.some((rule) => /transform\s+var\(--lnt-motion-fast\)/.test(rule.decls))).toBe(
      false,
    );
  });

  it("r5-11: токены press доходят до таббара — скоуп .hdr в списке style.css", () => {
    const css = stripComments(read("style.css"));
    expect(css).toMatch(/\.app-v6[^{}]*\.hdr[^{}]*\{[^}]*--lnt-t-press:/);
  });

  it("r5-11 net-removal: мёртвый background-транзишен снят с chip/step/.btn полосы", () => {
    for (const needle of [".lnt-live-chip-btn", ".lnt-live-step-btn", ".lnt-live-strip .btn"]) {
      const rules = baseRules(stripCssLocal, needle);
      expect(rules.length, `нет базового правила ${needle}`).toBeGreaterThan(0);
      for (const rule of rules) {
        // Частотная таблица, вопрос 1 («должно ли это анимироваться?»):
        // у семейства нет события, меняющего фон, — свойство удалено (r5-11).
        expect(rule.decls, `${needle}: background в transition`).not.toMatch(
          /transition[^;]*\bbackground\b/,
        );
        // Выжившие строки словаря: hover-цвет (border-color) и press-transform.
        expect(rule.decls, `${needle}: border-color-транзишен`).toMatch(
          /transition[^;]*border-color\s+var\(--lnt-t-fast\)\s+var\(--lnt-ease\)/,
        );
        expect(rule.decls, `${needle}: press-transform`).toMatch(
          /transform\s+var\(--lnt-t-press\)\s+var\(--lnt-ease-out\)/,
        );
      }
    }
  });
});
