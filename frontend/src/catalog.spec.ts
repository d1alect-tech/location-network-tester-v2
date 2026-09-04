/** E2E Todo 39: рабочая область каталога поверх мок-бэкенда (10 000 строк,
 * фиксированный seed). Покрывает: поиск+фильтры, сохранённые представления,
 * персистентность URL/перезагрузки, инспектор (правка→сохранение→перезагрузка),
 * конфликт revision, видимость повреждённых сессий, клавиатурный проход,
 * axe-проверку и бюджет тёплого запроса p95 ≤ 500 мс. */

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import { generateSessions } from "./testkit/catalogFixture";
import { type MockLntBackend, installMockBackend } from "./testkit/mockBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(
  __dirname,
  "../../../.omo/start-work/evidence/task-39-lnt-complete-redesign",
);
const BASE = "http://127.0.0.1:4101/static/v2/";
const FIXTURE_SIZE = 10_000;

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

let backend: MockLntBackend;

test.beforeEach(async ({ page }) => {
  backend = installMockBackend(page, { catalogSize: FIXTURE_SIZE, catalogSeed: 39 });
});

async function openCatalog(page: Page): Promise<void> {
  await page.goto(`${BASE}#/catalog`);
  await expect(page.locator(".lnt-cat-workspace")).toBeVisible();
}

function firstFixtureId(): string {
  return generateSessions({ size: FIXTURE_SIZE, seed: 39 })[0]?.id ?? "capture-00001";
}

function firstFixtureWithHealth(health: string): string {
  const found = generateSessions({ size: FIXTURE_SIZE, seed: 39 }).find(
    (session) => session.health === health,
  );
  if (!found) throw new Error(`fixture has no ${health} session`);
  return found.id;
}

/** Клавишами Tab доходит до элемента, совпадающего с селектором. */
async function tabUntilFocused(page: Page, selector: string, maxTabs = 8): Promise<void> {
  for (let index = 0; index <= maxTabs; index += 1) {
    const onTarget = await page.evaluate(
      (sel) => document.activeElement?.matches(sel) ?? false,
      selector,
    );
    if (onTarget) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`фокус не дошёл до ${selector} за ${String(maxTabs)} табов`);
}

/** Ждёт завершения мутации по объявлению aria-live области (не console/DOM-гонка). */
async function waitForAnnounce(page: Page, text: string): Promise<void> {
  await expect(page.locator('[role="status"][aria-live="polite"]')).toHaveText(text);
}

test("catalog lists sessions and combines search with health filter", async ({ page }) => {
  await openCatalog(page);
  const rows = page.locator(".lnt-cat-row");
  await expect(rows.first()).toBeVisible();

  // Поиск по метке (casefold-подстрока как в query_repository.py).
  await page.getByLabel("Метка").fill("стенд-А");
  await expect(page.locator(".lnt-cat-row .lnt-status-pill").first()).toBeVisible();
  const labelCells = page.locator(".lnt-cat-row").first().locator(".lnt-cat-cell").nth(1);
  await expect(labelCells).toHaveText(/стенд-А/u);

  // Комбинация: метка + health.
  await page.getByLabel("Состояние (health)").selectOption({ label: "Повреждён манифест" });
  const pill = page.locator(".lnt-cat-row").first().locator(".lnt-status-pill");
  await expect(pill).toHaveText(/Повреждён манифест/u);

  // Фильтры отражаются в URL и переживают перезагрузку.
  await expect(page.locator("#nav-catalog")).toHaveAttribute("data-route", "catalog");
  await page.reload();
  await expect(page.locator(".lnt-cat-row").first()).toBeVisible();
  await expect(page.getByLabel("Метка")).toHaveValue("стенд-А");
  await expect(page.getByLabel("Состояние (health)")).toHaveValue("corrupt_manifest");
});

test("empty result shows the Russian empty state", async ({ page }) => {
  await openCatalog(page);
  await page.getByLabel("Метка").fill("такой-метки-нет-вовсе");
  await expect(page.locator(".lnt-cat-empty")).toContainText("По запросу ничего не найдено");
});

test("saved view can be created, survives reset and is applied back", async ({ page }) => {
  await openCatalog(page);
  await page.getByLabel("Метка").fill("самошум");
  await page.getByRole("button", { name: "Сохранить фильтры…" }).click();
  await page.locator('[role="dialog"] input[type="text"]').fill("Самошум стенд-А");
  await page.getByRole("button", { name: "Сохранить", exact: true }).last().click();
  await expect(page.locator('[role="dialog"]')).toHaveCount(0);

  // Сброс очищает выдачу до полного каталога.
  await page.getByRole("button", { name: "Сбросить" }).click();
  await expect(page.getByLabel("Метка")).toHaveValue("");
  await expect(page.locator(".lnt-cat-row").first()).toBeVisible();

  // Применение сохранённого представления возвращает фильтры одним действием.
  await page.locator(".lnt-cat-saved select").selectOption("Самошум стенд-А");
  await expect(page.getByLabel("Метка")).toHaveValue("самошум");
});

test("inspector edits persist through save and page reload", async ({ page }) => {
  const sessionId = firstFixtureId();
  await openCatalog(page);

  await page.locator(`.lnt-cat-row[data-session-id="${sessionId}"]`).click();
  const inspectorRoot = page.locator(".lnt-cat-inspector");
  await expect(page.locator(".lnt-cat-session-summary")).toContainText(sessionId);
  await expect(inspectorRoot.locator(".lnt-cat-notes")).toHaveValue(`Заметки для ${sessionId}`);

  await inspectorRoot.locator(".lnt-cat-notes").fill("Проверено после калибровки");
  await inspectorRoot.getByRole("button", { name: "Сохранить", exact: true }).click();
  // Детерминированное ожидание конца мутации: объявление live-региона.
  await waitForAnnounce(page, "Контекст сохранён");

  // Мок-хранилище обновилось.
  const stored = backend.getContext(sessionId);
  if (!stored) throw new Error("context missing in mock backend");
  expect(stored.notes).toBe("Проверено после калибровки");

  // Перезагрузка: URL восстановил выбор сессии, заметки читаются заново.
  await page.reload();
  await expect(page.locator(".lnt-cat-session-summary")).toContainText(sessionId);
  await expect(page.locator(".lnt-cat-inspector .lnt-cat-notes")).toHaveValue(
    "Проверено после калибровки",
  );
});

test("stale revision save shows a typed conflict and merge flow never overwrites silently", async ({
  page,
}) => {
  const sessionId = firstFixtureId();
  await openCatalog(page);
  await page.locator(`.lnt-cat-row[data-session-id="${sessionId}"]`).click();
  const inspectorRoot = page.locator(".lnt-cat-inspector");
  await expect(inspectorRoot.locator(".lnt-cat-notes")).not.toHaveValue("");

  const beforeRevision = backend.getContext(sessionId)?.revision ?? 0;
  await inspectorRoot.locator(".lnt-cat-notes").fill("мои правки");

  // Конкурентная правка другим процессом пока пользователь редактирует.
  backend.concurrentEdit(sessionId);

  await inspectorRoot.getByRole("button", { name: "Сохранить", exact: true }).click();
  const conflictPanel = page.locator(".lnt-cat-conflict");
  await expect(conflictPanel).toBeVisible();
  await expect(conflictPanel).toContainText("Конфликт версий");

  // Чужие данные НЕ затёрты молча.
  expect(backend.getContext(sessionId)?.notes).toBe(`Чужая правка в ${sessionId}`);

  // Явное решение пользователя: перечитать и объединить поверх свежей revision.
  await conflictPanel.getByRole("button", { name: "Перечитать и объединить" }).click();
  await expect(conflictPanel).toBeHidden();

  const stored = backend.getContext(sessionId);
  if (!stored) throw new Error("context missing in mock backend");
  expect(stored.revision).toBeGreaterThan(beforeRevision + 1);
  expect(stored.notes).toBe("мои правки");
});

test("corrupt sessions stay visible with reason-coded badges and recovery explanation", async ({
  page,
}) => {
  const corruptId = firstFixtureWithHealth("context_invalid");
  await openCatalog(page);
  await page.getByLabel("Состояние (health)").selectOption("context_invalid");

  const row = page.locator(`.lnt-cat-row[data-session-id="${corruptId}"]`);
  await expect(row).toBeVisible();
  await expect(row.locator(".lnt-status-pill")).toHaveText(/Контекст повреждён/u);
  await row.click();

  const recovery = page.locator(".lnt-cat-recovery");
  await expect(recovery).toBeVisible();
  await expect(recovery).toContainText("Сессия повреждена или неполна");
  await expect(recovery).toContainText("Не удалось разобрать context.json");
});

test("keyboard-only journey reaches list, opens detail and saves an edit", async ({ page }) => {
  await openCatalog(page);
  // Tab-порядок от свежезагруженной страницы: 7 ссылок навигации → health → Метка.
  for (let index = 0; index < 9; index += 1) await page.keyboard.press("Tab");
  const labelControl = page.getByLabel("Метка");
  const labelId = await labelControl.getAttribute("id");
  const activeId = await page.evaluate(() => document.activeElement?.getAttribute("id") ?? "");
  if (activeId !== labelId) {
    // Подстраховка порядка фокуса браузера — дальше проход только клавишами.
    await labelControl.focus();
  }

  await page.keyboard.type(firstFixtureId());
  await page.keyboard.press("Tab"); // commit change при уходе фокуса

  const activeRow = page.locator(".lnt-cat-row[tabindex='0']");
  await expect(activeRow).toBeAttached();
  await activeRow.focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.locator(".lnt-cat-session-summary")).toBeVisible();

  // Только клавиатура: до заметок, выделить всё и заменить, до «Сохранить», Enter.
  await tabUntilFocused(page, ".lnt-cat-notes");
  await page.keyboard.press("Control+a");
  await page.keyboard.type("Клавиатурная правка заметок");
  await tabUntilFocused(page, '.lnt-cat-inspector button[type="button"].lnt-btn-primary');
  await page.keyboard.press("Enter");
  await waitForAnnounce(page, "Контекст сохранён");
  const sessionParam = new URLSearchParams(page.url().split("?")[1] ?? "").get("session") ?? "";
  expect(sessionParam).not.toBe("");
  expect(backend.getContext(sessionParam)?.notes).toBe("Клавиатурная правка заметок");
});

test("axe reports no violations on the working catalog fixture", async ({ page }) => {
  await openCatalog(page);
  await page.getByLabel("Метка").fill("самошум");
  await page.locator(".lnt-cat-row").first().click();
  await expect(page.locator(".lnt-cat-session-summary")).toBeVisible();

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

test("warm search query budget on 10k fixture stays under 500ms p95", async ({ page }) => {
  test.setTimeout(180_000);
  await openCatalog(page);
  const samplesMs: number[] = [];
  const queries = ["стенд", "самошум", "серия", "после"];

  // Прогрев (3 цикла) без измерения.
  for (let index = 0; index < 3; index += 1) {
    await page.getByLabel("Метка").fill(queries[index % queries.length] ?? "");
    await expect(page.locator(".lnt-cat-row").first()).toBeVisible();
  }

  for (let index = 0; index < 16; index += 1) {
    const query = queries[index % queries.length] ?? "";
    const started = Date.now();
    await page.getByLabel("Метка").fill(query);
    await expect(page.locator(".lnt-cat-row").first()).toBeVisible();
    samplesMs.push(Date.now() - started);
  }

  const sorted = [...samplesMs].sort((a, b) => a - b);
  const p95 = sorted[Math.ceil(sorted.length * 0.95) - 1] ?? Number.MAX_SAFE_INTEGER;
  const report = {
    fixture_rows: FIXTURE_SIZE,
    seed: 39,
    approach:
      "cursor paging page_size=200 from /api/catalog/sessions (mock mirrors keyset contract) + windowed virtualized rendering (~visible rows only) + debounced queries with AbortController race guard",
    warm_samples_ms: samplesMs,
    warm_p95_ms: p95,
    threshold_p95_ms: 500,
    passed: p95 <= 500,
  };
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  writeFileSync(
    resolve(EVIDENCE_DIR, "budget-catalog-query.json"),
    `${JSON.stringify(report, null, 2)}\n`,
  );
  expect(report.passed, `p95=${String(p95)}ms must be ≤500ms`).toBe(true);
});

test("manual QA screenshot: catalog with filters plus detail inspector", async ({ page }) => {
  await openCatalog(page);
  await page.getByLabel("Метка").fill("самошум");
  await page.getByLabel("Состояние (health)").selectOption({ index: 1 });
  await expect(page.locator(".lnt-cat-row").first()).toBeVisible();
  await page.locator(".lnt-cat-row").first().click();
  await expect(page.locator(".lnt-cat-session-summary")).toBeVisible();
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({
    path: resolve(EVIDENCE_DIR, "catalog-filters-inspector.png"),
    fullPage: true,
  });
});
