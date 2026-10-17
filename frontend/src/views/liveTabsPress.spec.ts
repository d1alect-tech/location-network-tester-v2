/** Задача r5-7 e2e: :active-press-правила существуют для именованных
 * ключ-контролов обеих вкладок (scope: run/stop, сегменты триггера;
 * sa: селекторы, трассы). Проверка — по живой CSSOM страницы (vite :4101,
 * mock-бэкенд): правило с transform: scale(var(--lnt-press-scale)) матчит
 * сам контрол (базовый селектор без :active), а не только существует. */

import { type Locator, expect, test } from "@playwright/test";
import { installMockBackend } from "../testkit/mockBackend";

const BASE = "http://127.0.0.1:4101/static/v2/";

test.beforeEach(async ({ page }) => {
  installMockBackend(page);
});

/** У элемента есть :active-правило с press-токеном, чей базовый селектор
 * (без :active) матчит элемент. */
async function hasPressRule(target: Locator): Promise<boolean> {
  return target.evaluate((el) => {
    const walk = (rules: CSSRuleList): boolean => {
      for (const rule of Array.from(rules)) {
        if (rule instanceof CSSMediaRule) {
          if (walk(rule.cssRules)) return true;
          continue;
        }
        if (!(rule instanceof CSSStyleRule) || !rule.selectorText.includes(":active")) continue;
        if (!rule.style.getPropertyValue("transform").includes("var(--lnt-press-scale)")) continue;
        try {
          if (el.matches(rule.selectorText.replace(/:active/g, ""))) return true;
        } catch {
          // Селектор после снятия :active некорректен — пропускаем.
        }
      }
      return false;
    };
    for (const sheet of Array.from(document.styleSheets)) {
      let rules: CSSRuleList;
      try {
        rules = sheet.cssRules;
      } catch {
        continue;
      }
      if (walk(rules)) return true;
    }
    return false;
  });
}

test("press-правила :active существуют для ключ-контролов обеих вкладок", async ({ page }) => {
  await page.goto(`${BASE}#/scope`);
  await expect(page.locator(".lnt-scope-workspace")).toBeVisible();
  // scope: run/stop run-кластера, сегменты триггера, сегменты В/дел.
  expect(await hasPressRule(page.locator(".lnt-live-runctl > button").first())).toBe(true);
  expect(await hasPressRule(page.locator(".lnt-scope-seg-btn").first())).toBe(true);
  expect(await hasPressRule(page.locator(".lnt-live-seg-btn").first())).toBe(true);

  await page.goto(`${BASE}#/sa`);
  await expect(page.locator(".lnt-sa-workspace")).toBeVisible();
  // sa: селекторы (RBW-сегменты, окно/детектор), тумблеры трасс.
  expect(await hasPressRule(page.locator(".lnt-live-seg-btn").first())).toBe(true);
  expect(await hasPressRule(page.locator(".lnt-sa-workspace .ctl").first())).toBe(true);
  expect(await hasPressRule(page.locator(".lnt-sa-check").first())).toBe(true);
});
