/** E2E T12: warn-баннер захвата, pairbar A/B/A, кнопка .md-экспорта + axe.
 * Все пути поверх моков (без живого бэкенда); селекторы существующих спек
 * только читаются, разметка ими не меняется. */

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { injectAxe } from "./testkit/axe";
import type { AxeSeriousSummary } from "./testkit/axe";
import { installMockBackend } from "./testkit/mockBackend";

/** Axe по поддереву фичи: чужие узлы страницы (оверлей/таймлайн) — не предмет T12. */
async function seriousAxeViolationsIn(page: Page, selector: string): Promise<AxeSeriousSummary[]> {
  const results = await page.evaluate((sel) => {
    const axe = (
      window as unknown as {
        axe?: {
          run(
            t: Record<string, unknown>,
            o?: Record<string, unknown>,
          ): Promise<{
            violations: {
              id: string;
              impact: string | null;
              nodes: { html: string; any: { id: string; message: string }[] }[];
            }[];
          }>;
        };
      }
    ).axe;
    if (!axe) throw new Error("axe не загружен на страницу");
    return axe.run(
      { include: [[sel]] },
      {
        runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
      },
    );
  }, selector);
  return results.violations
    .filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""))
    .map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      nodes: violation.nodes.map((node) => ({
        html: node.html,
        checks: node.any.map((check) => `${check.id}: ${check.message}`),
      })),
    }));
}

const BASE = "http://127.0.0.1:4101/static/v2/";

const ASSIGNMENTS: Record<string, string> = {};
for (const unit of ["unit-1", "unit-2", "unit-3", "unit-4"]) {
  ASSIGNMENTS[`aba-${unit}-a1`] = "cond_a1";
  ASSIGNMENTS[`aba-${unit}-b`] = "cond_b";
  ASSIGNMENTS[`aba-${unit}-a2`] = "cond_a2";
}

async function createAbaExperiment(page: Page, id: string): Promise<void> {
  await page.goto(`${BASE}#/experiments`);
  await expect(page.locator(".lnt-exp-workspace")).toBeVisible();
  await page.locator("#lnt-exp-create").click();
  await page.getByLabel("План эксперимента").selectOption("aba");
  await page.getByLabel("Идентификатор эксперимента").fill(id);
  await page.getByLabel("Название").fill(`Синтетика ${id}`);
  await page.getByLabel("Вопрос исследования").fill("Меняется ли фон при экранировании?");
  await page.getByLabel("Минимальный N единиц").fill("3");
  for (const [sessionId, condition] of Object.entries(ASSIGNMENTS)) {
    await page.getByLabel(`Условие сессии ${sessionId}`).selectOption(condition);
  }
  await page
    .locator(".lnt-exp-wizard")
    .getByRole("button", { name: "Создать эксперимент" })
    .click();
  await expect(page.locator(".lnt-exp-list")).toContainText(id);
}

test("T12.1: занятый захват — warn-полоса, axe чист", async ({ page }) => {
  installMockBackend(page);
  await page.goto(`${BASE}#/capture`);

  const startButton = page.getByRole("button", { name: "Запустить запись" });
  await startButton.click();
  await expect(page.locator(".capture-timeline")).toContainText("Задача выполняется");

  // Повторный старт при активной задаче — тот же алёрт, но warn-тон.
  await startButton.click();
  const alert = page.locator(".capture-alert");
  await expect(alert).toBeVisible();
  await expect(alert).toContainText("Задача ещё выполняется");
  await expect(alert).toHaveClass(/banner-warn/);

  await injectAxe(page);
  const summary = await seriousAxeViolationsIn(page, ".capture-alert");
  expect(summary, `axe serious/critical: ${JSON.stringify(summary)}`).toEqual([]);
});

test.describe("T12.2/T12.3 поверх research-мока", () => {
  test.beforeEach(async ({ page }) => {
    installMockBackend(page);
  });

  test("T12.2: pairbar показывает условия A/B/A с N, axe чист", async ({ page }) => {
    test.setTimeout(180_000);
    await createAbaExperiment(page, "exp.t12.aba");
    await page.locator('[data-exp-tab="compare"]').click();

    const pairbar = page.locator(".lnt-exp-comparison .pairbar");
    await expect(pairbar).toBeVisible();
    await expect(pairbar).toHaveAttribute("aria-label", /A\/B\/A/);
    const slots = pairbar.locator(".pair-slot");
    await expect(slots).toHaveCount(3);
    await expect(slots.nth(0)).toHaveAttribute("data-condition", "cond_a1");
    await expect(slots.nth(1)).toHaveAttribute("data-condition", "cond_b");
    await expect(slots.nth(2)).toHaveAttribute("data-condition", "cond_a2");
    await expect(slots.nth(0).locator(".pair-role")).toHaveText("A");
    await expect(slots.nth(1).locator(".pair-role")).toHaveText("Б");
    await expect(slots.nth(2).locator(".pair-role")).toHaveText("A2");
    await expect(slots.nth(0).locator(".pair-meta")).toContainText("N=");

    await injectAxe(page);
    const summary = await seriousAxeViolationsIn(page, ".pairbar");
    expect(summary, `axe serious/critical: ${JSON.stringify(summary)}`).toEqual([]);
  });

  test("T12.3: кнопка выгрузки даёт .md с именем report-<id>.md", async ({ page }) => {
    test.setTimeout(180_000);
    await createAbaExperiment(page, "exp.aba.demo");
    await page.goto(`${BASE}#/reports`);
    await expect(page.locator(".lnt-rep-workspace")).toBeVisible();

    await page.locator(".lnt-exp-open", { hasText: "exp.aba.demo" }).click();
    await expect(page.locator("#lnt-rep-build")).toBeEnabled();
    await page.locator("#lnt-rep-build").click();
    await expect(page.locator(".lnt-rep-preview")).toBeVisible();

    // Превью показывает ровно тот markdown, что уйдёт в файл.
    await expect(page.locator(".lnt-rep-preview .md")).toContainText("# Отчёт:");

    const downloadButton = page.locator("#lnt-rep-download");
    await expect(downloadButton).toBeEnabled();
    await expect(downloadButton).toHaveAttribute("data-export-format", "md");
    const downloadPromise = page.waitForEvent("download");
    await downloadButton.click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("report-exp.aba.demo.md");
  });
});
