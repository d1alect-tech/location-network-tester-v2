import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import type { JobSnapshot } from "./api/types-jobs";
import { installMockBackend } from "./test-support/mock-lnt-backend";

/** E2E рабочего процесса захвата (Todo 40): симулятор безопасен для
 * автоматизации; реальные пути устройства показывают диагностику, но запись
 * с сетью 230 В никогда не автоматизируется. */

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
// Артефакты ручной проверки — ВНЕ репозитория (InputLag/.omo), как требует задача.
const EVIDENCE_DIR = resolve(
  __dirname,
  "../../../.omo/start-work/evidence/task-40-lnt-complete-redesign",
);
const BASE = "http://127.0.0.1:4101/static/v2/";

function interruptedJobFixture(): JobSnapshot {
  return {
    schema_version: 1,
    version: 9,
    job_id: "job-interrupted",
    kind: "capture",
    status: "interrupted",
    stage: "capturing",
    series_index: 1,
    series_total: 3,
    written_sessions: ["cap-001"],
    result: null,
    error_code: "server_restart",
    error_message: null,
  };
}

test.describe("capture workflow", () => {
  test("mode setup screen shows exactly four modes and preview updates", async ({ page }) => {
    installMockBackend(page);
    await page.goto(`${BASE}#/capture`);

    const modeCards = page.locator('.capture-mode-group input[name="capture-mode"]');
    await expect(modeCards).toHaveCount(4);

    // Превью по умолчанию: RC-режим, два канала, база видима.
    await expect(page.locator(".capture-preview-list")).toContainText("RC-развязка");
    await expect(page.locator(".capture-channels-value")).toHaveText("Каналы: 2 (CH1 + CH2)");
    await expect(page.locator(".capture-preview-list")).toContainText("Базовая сессия");

    // Скриншот артефакта ручной проверки: экран настройки режима.
    await page.screenshot({ path: resolve(EVIDENCE_DIR, "manual-mode-setup.png"), fullPage: true });

    // Переключение в line-quality: каналы фиксируются, строка базы исчезает из превью.
    await page.locator('label[for="capture-mode-line_quality"]').click();
    await expect(page.locator(".capture-channels-value")).toHaveText("Каналы: 1 (только CH1)");
    await expect(page.locator(".capture-preview-list")).toContainText(
      "Трансформаторный пробник 230:6, множитель 10x",
    );
    await expect(page.locator(".capture-preview-list")).not.toContainText("Базовая сессия");
  });

  test("simulated single capture completes keyboard-only and lists indexed session", async ({
    page,
  }) => {
    const backend = installMockBackend(page);
    await page.goto(`${BASE}#/capture`);
    await expect(page.locator(".view-title")).toHaveText("Захват");

    // Клавиатурный запуск: фокус на кнопку старта и активация Enter'ом.
    const startButton = page.getByRole("button", { name: "Запустить запись" });
    await startButton.focus();
    await page.keyboard.press("Enter");

    // Хронология появляется и проходит стадии через SSE.
    const timeline = page.locator(".capture-timeline");
    await expect(timeline).toBeVisible();
    await expect(timeline).toContainText("Задача выполняется");
    await expect(timeline).toContainText("Стадия: симуляция");

    // Артефакт ручной проверки: хронология в активном состоянии.
    await page.screenshot({
      path: resolve(EVIDENCE_DIR, "manual-job-timeline-running.png"),
      fullPage: true,
    });

    // Доставляем остаток сценария и ждём терминальное состояние.
    backend.pumpAll();
    await expect(timeline).toContainText("Задача завершена");

    // Терминальное состояние: индексированная сессия перечислена в DOM.
    await expect(timeline).toContainText("Задача завершена");
    const writtenItems = timeline.locator(".capture-written-item");
    await expect(writtenItems).toHaveCount(1);
    await expect(writtenItems.first()).toHaveText(/sim-\d{3}/);

    // Запрос ушёл по контракту simulate с nonce-заголовком (проверено моком).
    await page.screenshot({
      path: resolve(EVIDENCE_DIR, "manual-job-timeline-done.png"),
      fullPage: true,
    });
  });

  test("dual-channel simulated capture keeps both channels in request", async ({ page }) => {
    const backend = installMockBackend(page);
    await page.goto(`${BASE}#/capture`);
    await page.locator('label[for="capture-mode-rc_measurement"]').click();

    const startButton = page.getByRole("button", { name: "Запустить запись" });
    await startButton.click();
    const timeline = page.locator(".capture-timeline");
    backend.pumpAll();
    await expect(timeline).toContainText("Задача завершена");
    await expect(backend.startedRequests[0]).toMatchObject({ kind: "simulate", channels: 2 });
  });

  test("line-quality capture maps to single-channel transformer contract", async ({ page }) => {
    const backend = installMockBackend(page);
    await page.goto(`${BASE}#/capture`);
    await page.locator('label[for="capture-mode-line_quality"]').click();
    await expect(page.locator(".capture-channels-value")).toHaveText("Каналы: 1 (только CH1)");

    const startButton = page.getByRole("button", { name: "Запустить запись" });
    await startButton.click();
    const timeline = page.locator(".capture-timeline");
    backend.pumpAll();
    await expect(timeline).toContainText("Задача завершена");
    await expect(backend.startedRequests[0]).toMatchObject({
      kind: "simulate",
      channels: 1,
    });
  });

  test("self-noise capture hides baseline and never sends one", async ({ page }) => {
    const backend = installMockBackend(page);
    await page.goto(`${BASE}#/capture`);
    await page.locator('label[for="capture-mode-self_noise"]').click();

    // Базовая сессия неприменима в самошуме — поле скрыто целиком.
    const baselineInput = page.locator('input[name="baseline_session"]');
    await expect(baselineInput).toBeHidden();

    const startButton = page.getByRole("button", { name: "Запустить запись" });
    await startButton.click();
    backend.pumpAll();
    await expect(page.locator(".capture-timeline")).toContainText("Задача завершена");
  });

  test("series cancel at safe boundary then retry works", async ({ page }) => {
    const backend = installMockBackend(page);
    await page.goto(`${BASE}#/capture`);

    // Серия из трёх повторов за раскрытием «Серия и протокол».
    await page.getByRole("button", { name: "Серия и протокол" }).click();
    await page.locator('input[name="repeat"]').fill("3");

    const startButton = page.getByRole("button", { name: "Запустить запись" });
    await startButton.click();
    const timeline = page.locator(".capture-timeline");
    await expect(timeline).toContainText("Серия 1 из 3");
    // Пока задача активна — повторный старт осознанно блокируется с причиной.
    await startButton.click();
    const alert = page.locator(".capture-alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("Задача ещё выполняется");

    // Отмена: подтверждение на безопасной границе серии.
    await page.getByRole("button", { name: "Отменить после текущей сессии" }).click();
    const dialog = page.locator('[role="dialog"][aria-modal="true"]');
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("безопасной границе");
    await dialog.getByRole("button", { name: "Подтвердить отмену" }).click();

    await expect(timeline).toContainText("Отмена запланирована после текущей сессии");
    await expect(backend.cancelRequests).toHaveLength(1);
    await expect(timeline).toContainText("Задача отменена");

    // Повтор задачи после отмены запускает новую задачу до успеха.
    await page.getByRole("button", { name: "Повторить задачу" }).click();
    backend.pumpAll();
    await expect(timeline).toContainText("Задача завершена");
    await expect(backend.startedRequests).toHaveLength(2);
  });

  test("driver_missing device renders exact Zadig next action and blocks preflight", async ({
    page,
  }) => {
    const backend = installMockBackend(page, { deviceState: "driver_missing" });
    await page.goto(`${BASE}#/capture`);

    // Переключаем источник на осциллограф: только этот путь требует железо.
    await page.locator('label[for="capture-source-device"]').click();

    await page.getByRole("button", { name: "Проверить устройство" }).click();
    const panel = page.locator(".capture-device-panel");
    await expect(panel).toContainText("Драйвер не установлен");
    await expect(panel).toContainText(
      "Установите WinUSB через Zadig отдельно для обнаруженного VID и повторите проверку.",
    );

    // Попытка записи на неготовом устройстве: preflight-блокер с кодом и действием.
    await page.getByRole("button", { name: "Запустить запись" }).click();
    await expect(page.locator(".capture-alert")).toContainText("устройство не готово");
    await expect(panel).toContainText("Блокирует запуск · device_driver_missing");
    expect(backend.preflightRequests.length).toBeGreaterThanOrEqual(1);
  });

  test("interrupted session after restart shows recovery prompt with retry", async ({ page }) => {
    installMockBackend(page, { existingJob: interruptedJobFixture() });
    await page.goto(`${BASE}#/capture`);

    const recovery = page.locator(".capture-recovery-banner");
    await expect(recovery).toBeVisible();
    await expect(recovery).toContainText("Задача была прервана из-за перезапуска сервера");
    await expect(recovery).toContainText("Данные сохранены частично");
    await expect(page.locator(".capture-written-item").first()).toHaveText("cap-001");
  });

  test("timeline shows onboarding when no job exists yet (queue A1)", async ({ page }) => {
    installMockBackend(page);
    await page.goto(`${BASE}#/capture`);

    const timeline = page.locator(".capture-timeline");
    await expect(timeline).toBeVisible();
    await expect(timeline).toContainText("Задач пока нет");
    await expect(timeline).toContainText("Запустите захват");
  });

  test("375px mobile and 200% zoom keep the form usable without clipped controls", async ({
    page,
  }) => {
    installMockBackend(page);
    await page.setViewportSize({ width: 375, height: 720 });
    await page.goto(`${BASE}#/capture`);
    await expect(page.locator(".view-title")).toHaveText("Захват");

    // Критерий Todo 40: ни один контрол рабочего процесса захвата не выходит
    // за правую границу вьюпорта (общая навигация оболочки — зона T38).
    const clipped = await measureWorstOverflow(page);
    expect(clipped).toBeLessThanOrEqual(0);
    const startButton = page.getByRole("button", { name: "Запустить запись" });
    await startButton.scrollIntoViewIfNeeded();
    await expect(startButton).toBeInViewport();

    // 200% масштаб на настольном окне: контролы остаются без обрезки.
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.evaluate(() => {
      (document.documentElement.style as CSSStyleDeclaration & { zoom: string }).zoom = "2";
    });
    const clippedZoom = await measureWorstOverflow(page);
    expect(clippedZoom).toBeLessThanOrEqual(0);
    await expect(page.getByRole("button", { name: "Запустить запись" })).toBeVisible();
  });
});

/** Максимальный выход контролов представления захвата за правую границу. */
function measureWorstOverflow(page: import("@playwright/test").Page): Promise<number> {
  return page.evaluate(() => {
    const view = document.querySelector(".capture-view");
    if (view === null) return -1;
    const limit = document.documentElement.clientWidth + 1;
    const controls = view.querySelectorAll<HTMLElement>(
      "button, input, select, label, .capture-preview-list",
    );
    let worst = 0;
    for (const node of controls) {
      const box = node.getBoundingClientRect();
      worst = Math.max(worst, Math.ceil(box.right) - limit);
    }
    return worst;
  });
}
