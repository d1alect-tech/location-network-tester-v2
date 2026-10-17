import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";
import type { CatalogSession } from "./api/types";
import type { JobSnapshot } from "./api/types-jobs";
import { installMockBackend } from "./testkit/mockBackend";

/** E2E визарда «Захвата» (G4, ui-refactor-2 todo 7): полный путь по шагам и
 * worst-case рамки — устройство отсутствует, задача в полёте, длинные имена
 * сессий, пустые необязательные поля, 375px на всех шагах, моушен-контракт. */

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
// Артефакты break-ui — в .omo ворктри (gitignored), путь от корня репозитория.
const EVIDENCE_DIR = resolve(__dirname, "../../.omo/evidence/ui-refactor-2/task-7/break-ui");
const BASE = "http://127.0.0.1:4101/static/v2/";

async function gotoStep2(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Далее: параметры" }).click();
  await expect(page.locator('.capture-step[data-capture-step="2"]')).toBeVisible();
}

async function gotoStep3(page: Page): Promise<void> {
  await gotoStep2(page);
  await page.getByRole("button", { name: "Далее: запуск" }).click();
  await expect(page.locator('.capture-step[data-capture-step="3"]')).toBeVisible();
}

function shot(name: string): string {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  return resolve(EVIDENCE_DIR, name);
}

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

function jobFixture(overrides: Partial<JobSnapshot>): JobSnapshot {
  return {
    schema_version: 1,
    version: 2,
    job_id: "job-wizard",
    kind: "capture",
    status: "running",
    stage: "capturing",
    series_index: 1,
    series_total: 3,
    written_sessions: [],
    result: null,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

/** Максимальный выход контролов представления за правую границу вьюпорта. */
function measureWorstOverflow(page: Page): Promise<number> {
  return page.evaluate(() => {
    const view = document.querySelector(".capture-view");
    if (view === null) return -1;
    const limit = document.documentElement.clientWidth + 1;
    const controls = view.querySelectorAll<HTMLElement>(
      "button, input, select, label, .capture-preview-list, .capture-written-item",
    );
    let worst = 0;
    for (const node of controls) {
      const box = node.getBoundingClientRect();
      worst = Math.max(worst, Math.ceil(box.right) - limit);
    }
    return worst;
  });
}

test.describe("capture wizard (G4)", () => {
  test("полный путь: режим → параметры → запуск → журнал → инспектор", async ({ page }) => {
    const backend = installMockBackend(page);
    backend.seedCatalog([writtenSession("sim-001")]);
    await page.goto(`${BASE}#/capture`);

    // Шаг 1: выбор режима (radio-cards сохранены) и переход «Далее».
    await expect(page.locator('.capture-step[data-capture-step="1"]')).toBeVisible();
    // A11y-пол: крупные цели рельса и навигации ≥ 44px.
    const railBox = await page.locator('.capture-stepitem[data-step="1"]').boundingBox();
    expect(railBox?.height ?? 0).toBeGreaterThanOrEqual(44);
    const nextBox = await page.getByRole("button", { name: "Далее: параметры" }).boundingBox();
    expect(nextBox?.height ?? 0).toBeGreaterThanOrEqual(44);
    await page.locator('label[for="capture-mode-single_channel"]').click();
    await gotoStep2(page);

    // Шаг 2: эхо выбора чипами, параметры, превью в боковой колонке.
    await expect(page.locator(".capture-echo")).toContainText("Одноканальный захват");
    await expect(page.locator(".capture-echo")).toContainText("симулятор");
    await expect(page.locator(".capture-channels-value")).toHaveText("Каналы: 1 (только CH1)");
    await expect(page.locator(".capture-preview-list")).toContainText("RC-развязка");
    await expect(page.locator('.capture-stepitem[data-step="1"]')).toHaveAttribute(
      "data-state",
      "done",
    );
    await page.screenshot({ path: shot("wizard-step2-params.png"), fullPage: true });

    // Шаг 3: запуск (мок), журнал доводится до терминального состояния.
    await page.getByRole("button", { name: "Далее: запуск" }).click();
    await expect(page.locator('.capture-step[data-capture-step="3"]')).toBeVisible();
    await expect(page.locator('.capture-stepitem[data-step="3"]')).toHaveAttribute(
      "data-state",
      "current",
    );
    await page.getByRole("button", { name: "Запустить запись" }).click();
    await expect(page.locator(".capture-timeline")).toContainText("Задача выполняется");
    await page.screenshot({ path: shot("wizard-step3-running.png"), fullPage: true });
    backend.pumpAll();
    await expect(page.locator(".capture-timeline")).toContainText("Задача завершена");

    // Журнал → записанная сессия → инспектор (шов todo 4 живёт на шаге 3).
    const link = page.locator(".capture-written-item a");
    await expect(link).toHaveAttribute("href", "#/inspect?a=sim-001");
    await page.screenshot({ path: shot("wizard-step3-done.png"), fullPage: true });
    await link.click();
    await expect(page).toHaveURL(/#\/inspect\?a=sim-001$/);
    await expect(page.locator(".pairbar [data-pair='a']")).toContainText("sim-001");
  });

  test("worst-case: устройство отсутствует — старт на шаге 3 блокирован с кодом", async ({
    page,
  }) => {
    const backend = installMockBackend(page, { deviceState: "device_absent" });
    await page.goto(`${BASE}#/capture`);
    await page.locator('label[for="capture-source-device"]').click();
    await gotoStep3(page);

    await page.getByRole("button", { name: "Запустить запись" }).click();
    const alert = page.locator(".capture-alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("устройство не готово");
    const panel = page.locator(".capture-device-panel");
    await expect(panel).toContainText("Устройство не найдено");
    await expect(panel).toContainText("Блокирует запуск · device_device_absent");
    expect(backend.startedRequests).toHaveLength(0);
    await page.screenshot({ path: shot("wizard-worst-device-absent.png"), fullPage: true });
  });

  test("worst-case: задача в полёте блокирует повторный старт с причиной", async ({ page }) => {
    const backend = installMockBackend(page, { existingJob: jobFixture({}) });
    await page.goto(`${BASE}#/capture`);

    // Живая задача на сервере: визард сразу открывает шаг 3 (журнал).
    await expect(page.locator('.capture-step[data-capture-step="3"]')).toBeVisible();
    await expect(page.locator(".capture-timeline")).toContainText("Задача выполняется");

    await page.getByRole("button", { name: "Запустить запись" }).click();
    const alert = page.locator(".capture-alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("Задача ещё выполняется");
    expect(backend.startedRequests).toHaveLength(0);
    await page.screenshot({ path: shot("wizard-worst-inflight.png"), fullPage: true });
  });

  test("worst-case: имя сессии 60+ символов переносится в журнале без overflow", async ({
    page,
  }) => {
    const longName = `2026-09-05T10-00-00_rc_measurement_${"x".repeat(48)}`;
    expect(longName.length).toBeGreaterThan(60);
    installMockBackend(page, {
      existingJob: jobFixture({
        status: "interrupted",
        error_code: "server_restart",
        written_sessions: [longName],
      }),
    });
    await page.goto(`${BASE}#/capture`);

    // Прерванная задача: шаг 3 открыт сразу, журнал несёт длинное имя.
    await expect(page.locator('.capture-step[data-capture-step="3"]')).toBeVisible();
    const item = page.locator(".capture-written-item").first();
    await expect(item).toHaveText(longName);

    // Перенос без горизонтального скролла: документ и контролы в границах.
    const docOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(docOverflow).toBeLessThanOrEqual(0);
    expect(await measureWorstOverflow(page)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot("wizard-worst-long-name.png"), fullPage: true });
  });

  test("worst-case: пустые необязательные поля проходят шаг 2 и старт", async ({ page }) => {
    const backend = installMockBackend(page);
    await page.goto(`${BASE}#/capture`);
    await gotoStep2(page);

    // Метка и базовая сессия пусты: гейт «Далее» это не блокирует.
    await page.locator('input[name="label"]').fill("");
    await page.locator('input[name="baseline_session"]').fill("");
    await expect(page.locator(".capture-preview-list")).toContainText("Метка");
    await page.getByRole("button", { name: "Далее: запуск" }).click();
    await expect(page.locator('.capture-step[data-capture-step="3"]')).toBeVisible();

    await page.getByRole("button", { name: "Запустить запись" }).click();
    backend.pumpAll();
    await expect(page.locator(".capture-timeline")).toContainText("Задача завершена");
    // Пустые опциональные поля не подменяются значениями: ключей в запросе нет.
    expect(backend.startedRequests[0]).not.toHaveProperty("label");
    expect(backend.startedRequests[0]).not.toHaveProperty("baseline_session");
  });

  test("worst-case: 375px — все три шага без горизонтального overflow", async ({ page }) => {
    installMockBackend(page);
    await page.setViewportSize({ width: 375, height: 720 });
    await page.goto(`${BASE}#/capture`);

    expect(await measureWorstOverflow(page)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot("wizard-mobile-step1.png"), fullPage: true });
    await gotoStep2(page);
    expect(await measureWorstOverflow(page)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot("wizard-mobile-step2.png"), fullPage: true });
    await page.getByRole("button", { name: "Далее: запуск" }).click();
    await expect(page.locator('.capture-step[data-capture-step="3"]')).toBeVisible();
    expect(await measureWorstOverflow(page)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot("wizard-mobile-step3.png"), fullPage: true });
  });

  test("моушен-контракт: вход на монтировании, шаг без анимации, reduced-motion", async ({
    page,
  }) => {
    installMockBackend(page);
    await page.goto(`${BASE}#/capture`);

    // Переход между шагами — частое действие: панель появляется без анимации.
    await gotoStep2(page);
    const stepAnimation = await page
      .locator('.capture-step[data-capture-step="2"]')
      .evaluate((node) => getComputedStyle(node).animationName);
    expect(stepAnimation).toBe("none");

    // CSS-контракт: монтажный вход есть и снимается в prefers-reduced-motion.
    const motion = await page.evaluate(() => {
      let entrance = false;
      let reduced = false;
      for (const sheet of Array.from(document.styleSheets)) {
        let rules: CSSRuleList;
        try {
          rules = sheet.cssRules;
        } catch {
          continue;
        }
        const walk = (list: CSSRuleList, inReduced: boolean): void => {
          for (const rule of Array.from(list)) {
            if (rule instanceof CSSMediaRule) {
              walk(
                rule.cssRules,
                inReduced || rule.conditionText.includes("prefers-reduced-motion"),
              );
              continue;
            }
            if (!(rule instanceof CSSStyleRule)) continue;
            if (!rule.selectorText.includes(".capture-step-main.is-entering")) continue;
            const animation = rule.style.getPropertyValue("animation");
            const animationName = rule.style.getPropertyValue("animation-name");
            if (inReduced && (animationName === "none" || animation === "none")) reduced = true;
            if (!inReduced && animation.includes("lnt-capture-in")) entrance = true;
          }
        };
        walk(rules, false);
      }
      return { entrance, reduced };
    });
    expect(motion.entrance).toBe(true);
    expect(motion.reduced).toBe(true);
  });
});
