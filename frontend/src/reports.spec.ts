/** E2E Todo 44: рабочая область «Отчёты» поверх мок-бэкенда.
 * Полный путь исследователя: эксперимент создаётся в UI → отчёт собирается
 * из statistics-runs → превью показывает provenance/единицы/N/плоскости/
 * ограничения → выгрузка .md содержит те же данные. Плюс: отказ расчёта,
 * axe без серьёзных нарушений, снимки 375/768/1280. */

import { mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import { injectAxe, seriousAxeViolations } from "./testkit/axe";
import { installMockBackend } from "./testkit/mockBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(
  __dirname,
  "../../../.omo/start-work/evidence/task-44-lnt-complete-redesign",
);
const BASE = "http://127.0.0.1:4101/static/v2/";

test.beforeEach(async ({ page }) => {
  installMockBackend(page);
});

async function openReports(page: Page): Promise<void> {
  await page.goto(`${BASE}#/reports`);
  await expect(page.locator(".lnt-rep-workspace")).toBeVisible();
}

const DEMO_ASSIGNMENTS: Record<string, string> = {};
for (const unit of ["unit-1", "unit-2", "unit-3", "unit-4"]) {
  DEMO_ASSIGNMENTS[`aba-${unit}-a1`] = "cond_a1";
  DEMO_ASSIGNMENTS[`aba-${unit}-b`] = "cond_b";
  DEMO_ASSIGNMENTS[`aba-${unit}-a2`] = "cond_a2";
}

/** Создаёт канонический A/B/A-эксперимент через UI «Экспериментов». */
async function createDemoExperiment(page: Page): Promise<void> {
  await page.goto(`${BASE}#/experiments`);
  await expect(page.locator(".lnt-exp-workspace")).toBeVisible();
  await page.locator("#lnt-exp-create").click();
  const wizard = page.locator(".lnt-exp-wizard");
  await expect(wizard).toBeVisible();
  await page.getByLabel("План эксперимента").selectOption("aba");
  await page.getByLabel("Идентификатор эксперимента").fill("exp.aba.demo");
  await page.getByLabel("Название").fill("Синтетика exp.aba.demo");
  await page.getByLabel("Вопрос исследования").fill("Меняется ли фон при экранировании?");
  await page.getByLabel("Минимальный N единиц").fill("3");
  for (const [sessionId, condition] of Object.entries(DEMO_ASSIGNMENTS)) {
    await page.getByLabel(`Условие сессии ${sessionId}`).selectOption(condition);
  }
  await wizard.getByRole("button", { name: "Создать эксперимент" }).click();
  await expect(page.locator(".lnt-exp-list")).toContainText("exp.aba.demo");
}

test("report journey: experiment → build preview with provenance → download .md", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await createDemoExperiment(page);
  await openReports(page);

  await page.locator(".lnt-exp-open", { hasText: "exp.aba.demo" }).click();
  await expect(page.locator("#lnt-rep-build")).toBeEnabled();

  await page.locator("#lnt-rep-build").click();
  const preview = page.locator(".lnt-rep-preview");
  await expect(preview).toBeVisible();

  // Provenance и обязательная маркировка.
  await expect(preview).toContainText("Происхождение (provenance)");
  await expect(preview).toContainText("exp.aba.demo");
  await expect(preview).toContainText("Оцениваемый признак");
  await expect(preview).toContainText("band_mid_total");
  await expect(preview).toContainText("Единицы и объём выборки");
  await expect(preview).toContainText("В²/Гц");
  await expect(preview).toContainText("4 (measurement_session)");
  // Золотые числа из numpy-репликации бэкенда (seed 43).
  await expect(preview).toContainText("[1.6000; 2.3125] В²/Гц");
  // Плоскости: у здоровых сессий приведение ко входу доступно.
  await expect(preview).toContainText("Плоскости измерения");
  await expect(preview.locator(".lnt-rep-planes li").first()).toContainText("приведён ко входу");
  // Ограничения: не только цвет — коды текстом; причинность объявлена;
  // замечание здоровья коррумпированной сессии зафиксировано честно.
  await expect(preview).toContainText("Ограничения");
  await expect(preview).toContainText("causal_inference_not_available");
  await expect(preview).toContainText("sessions_with_health_notes");
  await expect(preview).toContainText("aba-unit-4-a2 (corrupt_manifest)");
  await expect(page.locator("#lnt-rep-download")).toBeEnabled();

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page
    .locator(".lnt-rep-preview")
    .screenshot({ path: resolve(EVIDENCE_DIR, "report-preview.png") });

  const downloadPromise = page.waitForEvent("download");
  await page.locator("#lnt-rep-download").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("report-exp.aba.demo.md");
  const markdown = readFileSync(await download.path(), "utf8");
  expect(markdown).toContain("# Отчёт: Синтетика exp.aba.demo");
  expect(markdown).toContain("job_id: `job-1`");
  expect(markdown).toContain("[1.6000; 2.3125]");
  expect(markdown).toContain("## Ограничения");
  expect(markdown).toContain("## Рецепты анализа");
});

test("refusal result renders typed refusal limitation without effect numbers", async ({ page }) => {
  await createDemoExperiment(page);
  // Дрейфовый набор: a2 = a1 + 3 гарантированно даёт refusal от бэкенда.
  await createDriftExperiment(page);
  await openReports(page);
  await page.locator(".lnt-exp-open", { hasText: "exp.aba.drift" }).click();
  await page.locator("#lnt-rep-build").click();
  const preview = page.locator(".lnt-rep-preview");
  await expect(preview).toContainText("Расчёт заблокирован бэкендом");
  await expect(preview).toContainText("a_drift_exceeds_half_effect_or_two_sd");
  await expect(preview).toContainText("statistics_refusal");
});

async function createDriftExperiment(page: Page): Promise<void> {
  const assignments: Record<string, string> = {};
  for (const unit of ["unit-1", "unit-2", "unit-3", "unit-4"]) {
    assignments[`drift-${unit}-a1`] = "cond_a1";
    assignments[`drift-${unit}-b`] = "cond_b";
    assignments[`drift-${unit}-a2`] = "cond_a2";
  }
  await page.goto(`${BASE}#/experiments`);
  await expect(page.locator(".lnt-exp-workspace")).toBeVisible();
  await page.locator("#lnt-exp-create").click();
  await page.getByLabel("План эксперимента").selectOption("aba");
  await page.getByLabel("Идентификатор эксперимента").fill("exp.aba.drift");
  await page.getByLabel("Название").fill("Дрейфовый набор");
  await page.getByLabel("Вопрос исследования").fill("Есть ли дрейф между A-фазами?");
  await page.getByLabel("Минимальный N единиц").fill("3");
  for (const [sessionId, condition] of Object.entries(assignments)) {
    await page.getByLabel(`Условие сессии ${sessionId}`).selectOption(condition);
  }
  await page
    .locator(".lnt-exp-wizard")
    .getByRole("button", { name: "Создать эксперимент" })
    .click();
  await expect(page.locator(".lnt-exp-list")).toContainText("exp.aba.drift");
}

test("disabled buttons explain themselves until report is built (queue A1)", async ({ page }) => {
  await openReports(page);
  await expect(page.locator("#lnt-rep-hint")).toContainText("Сначала выберите эксперимент");
  await createDemoExperiment(page);
  await openReports(page);
  await page.locator(".lnt-exp-open", { hasText: "exp.aba.demo" }).click();
  const download = page.locator("#lnt-rep-download");
  await expect(download).toBeDisabled();
  await expect(download).toHaveAttribute("title", "Станет доступна после сборки отчёта");
  await expect(page.locator("#lnt-rep-hint")).toContainText("Собрать отчёт");
});

test("empty workspace explains where experiments are created (no dead end)", async ({ page }) => {
  await openReports(page);
  await expect(page.locator(".lnt-rep-left")).toContainText(
    "Экспериментов пока нет. Создайте их в разделе «Эксперименты».",
  );
});

for (const width of [375, 768, 1280]) {
  test(`responsive snapshot ${width}px: no horizontal document overflow`, async ({ page }) => {
    await createDemoExperiment(page);
    await openReports(page);
    await page.setViewportSize({ width, height: 800 });
    await expect(page.locator(".lnt-rep-workspace")).toBeVisible();
    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
    mkdirSync(EVIDENCE_DIR, { recursive: true });
    await page.screenshot({ path: resolve(EVIDENCE_DIR, `reports-${width}.png`), fullPage: false });
  });
}

test("axe reports no serious or critical violations on the reports workspace", async ({ page }) => {
  await createDemoExperiment(page);
  await openReports(page);
  await page.locator(".lnt-exp-open", { hasText: "exp.aba.demo" }).click();
  await page.locator("#lnt-rep-build").click();
  await expect(page.locator(".lnt-rep-preview")).toBeVisible();
  await injectAxe(page);
  const summary = await seriousAxeViolations(page);
  expect(summary, `axe serious/critical: ${JSON.stringify(summary)}`).toEqual([]);
});
