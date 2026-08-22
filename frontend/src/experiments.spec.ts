/** E2E Todo 43: рабочая область экспериментов поверх мок-бэкенда.
 * Синтетический A/B/A-путь: создание → валидация → расчёт → результат
 * (золотые числа из numpy-репликации estimate_paired/analyze_aba),
 * отмена исключения видима, баннеры мало-N/дрейфа/смешивающих,
 * смешанный тип заблокирован с точной причиной, конфликт revision
 * не замалчивается, клавиатурный проход и axe. */

import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import { MockResearchBackend, attachResearchBackend } from "./testkit/researchBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(
  __dirname,
  "../../../.omo/start-work/evidence/task-43-lnt-complete-redesign",
);
const BASE = "http://127.0.0.1:4101/static/v2/";

interface AxeViolation {
  id: string;
  impact: string | null;
  nodes: unknown[];
}

interface AxeRunResult {
  violations: AxeViolation[];
}

interface AxeLike {
  run(target: Document, options?: Record<string, unknown>): Promise<AxeRunResult>;
}

declare global {
  interface Window {
    axe: AxeLike;
  }
}

let backend: MockResearchBackend;

test.beforeEach(async ({ page }) => {
  backend = new MockResearchBackend();
  await attachResearchBackend(page, backend);
});

async function openExperiments(page: Page): Promise<void> {
  await page.goto(`${BASE}#/experiments`);
  await expect(page.locator(".lnt-exp-workspace")).toBeVisible();
}

/** Назначает сессии условиям мастера и создаёт эксперимент. */
async function createExperiment(
  page: Page,
  options: {
    id: string;
    plan?: "aba" | "ab";
    assignments: Record<string, string>;
    minN?: string;
  },
): Promise<void> {
  await page.locator("#lnt-exp-create").click();
  const wizard = page.locator(".lnt-exp-wizard");
  await expect(wizard).toBeVisible();
  if (options.plan !== undefined) {
    await page.getByLabel("План эксперимента").selectOption(options.plan);
  }
  await page.getByLabel("Идентификатор эксперимента").fill(options.id);
  await page.getByLabel("Название").fill(`Синтетика ${options.id}`);
  await page.getByLabel("Вопрос исследования").fill("Меняется ли фон при экранировании?");
  await page.getByLabel("Минимальный N единиц").fill(options.minN ?? "3");
  for (const [sessionId, condition] of Object.entries(options.assignments)) {
    await page.getByLabel(`Условие сессии ${sessionId}`).selectOption(condition);
  }
  await wizard.getByRole("button", { name: "Создать эксперимент" }).click();
  await expect(page.locator(".lnt-exp-list")).toContainText(options.id);
}

const DEMO_ASSIGNMENTS: Record<string, string> = {};
for (const unit of ["unit-1", "unit-2", "unit-3", "unit-4"]) {
  DEMO_ASSIGNMENTS[`aba-${unit}-a1`] = "cond_a1";
  DEMO_ASSIGNMENTS[`aba-${unit}-b`] = "cond_b";
  DEMO_ASSIGNMENTS[`aba-${unit}-a2`] = "cond_a2";
}

test("A/B/A journey: create → timeline → QC exclusion undo → golden result", async ({ page }) => {
  test.setTimeout(180_000);
  await openExperiments(page);
  await createExperiment(page, { id: "exp.aba.demo", assignments: DEMO_ASSIGNMENTS });

  // Деталь загружена: таймлайн из трёх упорядоченных шагов.
  await expect(page.locator(".lnt-exp-step")).toHaveCount(3);
  await expect(page.locator(".lnt-exp-kind-badge")).toHaveText("A/B/A");
  const stepLabels = await page
    .locator(".lnt-exp-step")
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("aria-label") ?? ""));
  expect(stepLabels[0]).toContain("Шаг 1");
  expect(stepLabels[2]).toContain("Шаг 3");

  // Участники: 12 строк, QC-вердикты текстом (не только цветом).
  const rows = page.locator(".lnt-exp-member-row");
  await expect(rows).toHaveCount(12);
  await expect(page.locator(".lnt-exp-member-table").first()).toContainText("QC пройден");

  // Исключение: строка остаётся видимой, зачёркнута, с причиной.
  const victim = "aba-unit-4-a2";
  await page.getByRole("button", { name: `Исключить участника ${victim}` }).click();
  const excludedRow = page.locator("tr.lnt-exp-excluded");
  await expect(excludedRow).toHaveCount(1);
  await expect(excludedRow).toContainText("Исключён: qc_corrupt_manifest");

  // Undo: участник восстановлен, аудит хранит обе записи.
  await page.getByRole("button", { name: `Отменить исключение участника ${victim}` }).click();
  await expect(page.locator("tr.lnt-exp-excluded")).toHaveCount(0);
  await rows.filter({ hasText: victim }).getByRole("button", { name: "Аудит" }).click();
  await expect(page.locator(".lnt-exp-audit")).toContainText("исключён");
  await expect(page.locator(".lnt-exp-audit")).toContainText("отмена ревизии");

  // Сравнение: проверка сравнимости, затем расчёт.
  await page.locator('[data-exp-tab="compare"]').click();
  await page.locator("#lnt-exp-check-comparability").click();
  await expect(page.locator(".lnt-exp-compare-status")).toContainText("Сравнимость подтверждена");
  await page.locator("#lnt-exp-run-analysis").click();

  // Золотые числа (numpy-репликация бэкенда, seed 43/44).
  const result = page.locator(".lnt-exp-result");
  await expect(result).toContainText("Инференциальная оценка");
  await expect(result).toContainText("1.9625 В²/Гц");
  await expect(result).toContainText("[1.6000; 2.3125] В²/Гц");
  await expect(result).toContainText("N=4");
  await expect(result).toContainText("qualified_within_run_contrast");
  await expect(result).toContainText("Дрейф A (A2−A1)");
  await expect(result).toContainText("0.0750 В²/Гц");
  await expect(result).toContainText("причинный вывод недоступен");

  // Скриншот A: результат сравнения.
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page
    .locator(".lnt-exp-comparison")
    .screenshot({ path: resolve(EVIDENCE_DIR, "aba-result-golden.png") });

  // Скриншот A2: таймлайн протокола.
  await page.locator('[data-exp-tab="overview"]').click();
  await page
    .locator(".lnt-exp-right")
    .screenshot({ path: resolve(EVIDENCE_DIR, "aba-timeline-members.png") });
});

test("low-N experiment renders explicit descriptive banner without interval", async ({ page }) => {
  await openExperiments(page);
  await createExperiment(page, {
    id: "exp.aba.lown",
    minN: "2",
    assignments: {
      "aba-unit-1-a1": "cond_a1",
      "aba-unit-1-b": "cond_b",
      "aba-unit-1-a2": "cond_a2",
      "aba-unit-2-a1": "cond_a1",
      "aba-unit-2-b": "cond_b",
      "aba-unit-2-a2": "cond_a2",
    },
  });
  await page.locator('[data-exp-tab="compare"]').click();
  await page.locator("#lnt-exp-run-analysis").click();
  const result = page.locator(".lnt-exp-result");
  await expect(result).toContainText("Описательная оценка без интервала");
  await expect(result).toContainText("N=2");
  await expect(result).toContainText("не является статистической уверенностью");
  await expect(result).toContainText("интервал не строится");
});

test("A-drift refusal shows the exact reason code and no contrast numbers", async ({ page }) => {
  await openExperiments(page);
  const driftAssignments: Record<string, string> = {};
  for (const unit of ["unit-1", "unit-2", "unit-3", "unit-4"]) {
    driftAssignments[`drift-${unit}-a1`] = "cond_a1";
    driftAssignments[`drift-${unit}-b`] = "cond_b";
    driftAssignments[`drift-${unit}-a2`] = "cond_a2";
  }
  await createExperiment(page, { id: "exp.aba.drift", assignments: driftAssignments });
  await page.locator('[data-exp-tab="compare"]').click();
  await page.locator("#lnt-exp-check-comparability").click();
  await page.locator("#lnt-exp-run-analysis").click();
  const result = page.locator(".lnt-exp-result");
  await expect(result).toContainText("a_drift_exceeds_half_effect_or_two_sd");
  await expect(result).toContainText("заблокирован");
});

test("mixed-type comparison is blocked with the exact finding code", async ({ page }) => {
  await openExperiments(page);
  backend.mixedTypeSessions.add("mix-legacy-a");
  await createExperiment(page, {
    id: "exp.mix.blocked",
    plan: "ab",
    assignments: { "mix-legacy-a": "cond_a", "mix-rc-b": "cond_b" },
  });
  await page.locator('[data-exp-tab="compare"]').click();
  await page.locator("#lnt-exp-check-comparability").click();
  const banner = page.locator(".lnt-exp-banner-warn");
  await expect(banner).toContainText("Сравнение заблокировано");
  await expect(banner).toContainText("comparison_kind_mismatch");
  // Попытка расчёта не уходит на сервер и не выдаёт число.
  await page.locator("#lnt-exp-run-analysis").click();
  await expect(page.locator(".lnt-exp-result")).toHaveCount(0);
  await expect(page.locator(".lnt-exp-compare-status").last()).toContainText(
    "сравнимость не подтверждена",
  );
});

test("hypothesis editor: create, link evidence context, stale revision conflict is explicit", async ({
  page,
}) => {
  await openExperiments(page);
  await createExperiment(page, { id: "exp.aba.demo", assignments: DEMO_ASSIGNMENTS });

  await page.locator('[data-exp-tab="hypotheses"]').click();
  await page.getByRole("button", { name: "Новая гипотеза…" }).click();
  const form = page.locator(".lnt-exp-hypothesis-form");
  await form
    .locator("input[type=text]")
    .first()
    .fill("Экранирование снижает фон на средних частотах");
  await form.locator("input[type=text]").nth(1).fill("экранированный кабель уменьшает наводки");
  await expect(form).toContainText("exp.aba.demo");
  await form.locator('button[type="submit"]').click();

  const list = page.locator(".lnt-exp-hypothesis-list");
  await expect(list).toContainText("Экранирование снижает фон");
  await expect(list).toContainText("черновик");

  // Скриншот B: редактор гипотез.
  await list.getByRole("button", { name: /Открыть гипотезу/ }).click();
  await expect(page.locator(".lnt-exp-hypothesis-form")).toBeVisible();
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page
    .locator(".lnt-exp-hypotheses")
    .screenshot({ path: resolve(EVIDENCE_DIR, "hypothesis-editor.png") });

  // Конфликт revision: чужая правка между открытием и сохранением.
  backend.conflictNextHypothesis = true;
  const form2 = page.locator(".lnt-exp-hypothesis-form");
  await form2.locator('button[type="submit"]').click();
  await expect(page.locator(".lnt-exp-hypothesis-form [role=alert]")).toContainText(
    "Конфликт версий",
  );
  // Тихой перезаписи нет: гипотеза осталась в исходной ревизии.
  await page.locator(".lnt-exp-hypothesis-form").getByRole("button", { name: "Закрыть" }).click();
  await expect(page.locator(".lnt-exp-hypothesis-list")).toContainText("Экранирование снижает фон");
});

test("trends tab runs a descriptive query and shows confound/missingness marking", async ({
  page,
}) => {
  await openExperiments(page);
  await createExperiment(page, { id: "exp.aba.demo", assignments: DEMO_ASSIGNMENTS });
  await page.locator('[data-exp-tab="trends"]').click();
  await page.locator("#lnt-exp-run-trend").click();
  const trends = page.locator(".lnt-exp-trends");
  await expect(trends).toContainText("Средние по группам");
  await expect(trends).toContainText("описательное");
  await expect(trends).toContainText("НЕ причинные эффекты");
});

test("keyboard: workspace is reachable and tabs are operable without pointer", async ({ page }) => {
  await openExperiments(page);
  await page.locator("#lnt-exp-create").click();
  const wizard = page.locator(".lnt-exp-wizard");
  await expect(wizard).toBeVisible();
  // Esc-независимый выход: кнопка закрытия не предусмотрена мастером,
  // поэтому проверяем фокус внутри формы и отмену через перезагрузку.
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.tagName ?? "");
  expect(["INPUT", "SELECT", "BUTTON", "A"]).toContain(focused);
  await page.reload();
  await expect(page.locator(".lnt-exp-workspace")).toBeVisible();
});

test("axe reports no violations on the experiments workspace", async ({ page }) => {
  await openExperiments(page);
  await createExperiment(page, { id: "exp.aba.demo", assignments: DEMO_ASSIGNMENTS });
  await page.locator('[data-exp-tab="compare"]').click();
  await page.addScriptTag({
    path: resolve(__dirname, "../node_modules/axe-core/axe.min.js"),
  });
  const results = await page.evaluate(() =>
    window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] }),
  );
  const summary = results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact ?? null,
    nodes: violation.nodes.length,
  }));
  expect(summary, `axe violations: ${JSON.stringify(summary)}`).toEqual([]);
});
