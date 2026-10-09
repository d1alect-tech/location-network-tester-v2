import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import type { CatalogSession } from "./api/types";
import { type MockLntBackend, installMockBackend } from "./testkit/mockBackend";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const BASE = "http://127.0.0.1:4101/static/v2/index.html";
// Артефакты ручной проверки — в .omo ворктри (gitignored). Путь отсчитывается
// ОТ КОРНЯ РЕПОЗИТОРИЯ: ../../.omo из frontend/src (а не ../../../ — баг
// первой волны MINOR-5 уводил артефакты за пределы репозитория).
const EVIDENCE_DIR = resolve(__dirname, "../../.omo/evidence/ui-refactor-2/task-4");

/** Мок-задача вида simulate пишет сессию sim-001 (testkit/mockJobStore:
 *  префикс по виду + счётчик, дополненный до трёх знаков). */
const WRITTEN_ID = "sim-001";

let backend: MockLntBackend;

/** Инспекция обязана найти сессию, которую записал захват. */
function writtenSession(id: string): CatalogSession {
  return {
    id,
    health: "ok",
    created_utc: "2026-09-05T10:00:00Z",
    source: "simulator",
    session_type: "rc_measurement",
    profile: "bad",
    label: null,
    storage_path: `/sessions/${id}`,
  };
}

test.beforeEach(async ({ page }) => {
  backend = installMockBackend(page);
  backend.seedCatalog([writtenSession(WRITTEN_ID)]);
});

/** Запускает симуляцию и доводит задачу до записанной сессии. */
async function completeMockCapture(page: Page): Promise<void> {
  await page.goto(`${BASE}#/capture`);
  await expect(page.locator(".view-title")).toHaveText("Захват");
  await page.getByRole("button", { name: "Запустить запись" }).click();
  backend.pumpAll();
  await expect(page.locator(".capture-timeline")).toContainText("Задача завершена");
}

test("записанная сессия захвата открывается в инспекции по клику", async ({ page }) => {
  await completeMockCapture(page);
  const timeline = page.locator(".capture-timeline");

  // Пины capture.spec.ts:94,215 сохранены: элемент и его текст не изменились.
  const item = timeline.locator(".capture-written-item");
  await expect(item).toHaveCount(1);
  await expect(item.first()).toHaveText(WRITTEN_ID);

  const link = item.locator("a");
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", `#/inspect?a=${WRITTEN_ID}`);

  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({ path: resolve(EVIDENCE_DIR, "capture-written-session-link.png") });

  await link.click();

  // Маршрут сменился: инспекция с этой сессией в слоте А, захвата больше нет.
  await expect(page).toHaveURL(new RegExp(`#/inspect\\?a=${WRITTEN_ID}$`));
  await expect(page.locator(".capture-written-item")).toHaveCount(0);
  await expect(page.locator(".pairbar [data-pair='a']")).toContainText(WRITTEN_ID);
  await expect(page.locator(".col-cat [data-session='sim-001']")).toHaveCount(1);
  // Общая оболочка следует за маршрутом: активный пункт таббара — инспекция.
  await expect(page.locator(".snav-item.is-active")).toHaveAttribute("data-route", "inspect");

  await page.screenshot({ path: resolve(EVIDENCE_DIR, "inspect-from-written-session.png") });
});

test("записанная сессия достижима с клавиатуры и открывается по Enter", async ({ page }) => {
  await completeMockCapture(page);
  const link = page.locator(".capture-written-item a");

  await link.focus();
  await expect(link).toBeFocused();
  await link.press("Enter");

  await expect(page).toHaveURL(new RegExp(`#/inspect\\?a=${WRITTEN_ID}$`));
  await expect(page.locator(".pairbar [data-pair='a']")).toContainText(WRITTEN_ID);
});
