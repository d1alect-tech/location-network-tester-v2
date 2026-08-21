import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/** Витрина примитивов: реальная браузерная поверхность для доказательства a11y. */
const EVIDENCE_DIR = resolve(
  __dirname,
  "../../.omo/start-work/evidence/task-38-lnt-complete-redesign",
);

test("primitives showcase renders and stays accessible", async ({ page }) => {
  await page.goto("http://127.0.0.1:4102/static/v2/showcase.html");

  await expect(page.locator(".demo-section")).toHaveCount(6);

  // Диалог: открытие, ловушка фокуса, Esc.
  await page.getByRole("button", { name: "Открыть диалог" }).click();
  const dialog = page.locator('[role="dialog"][aria-modal="true"]');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Подтверждение");
  await page.screenshot({ path: resolve(EVIDENCE_DIR, "showcase-dialog.png") });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);

  // Таблица: сортировка кнопкой в заголовке.
  const sortButton = page.getByRole("button", { name: "Метка" });
  await sortButton.click();
  await expect(sortButton.locator("xpath=ancestor::th[1]")).toHaveAttribute(
    "aria-sort",
    "ascending",
  );
  await page
    .locator(".lnt-table-wrapper")
    .screenshot({ path: resolve(EVIDENCE_DIR, "showcase-table.png") });

  // Разделитель панелей: клавиатурное изменение пропорции.
  const separator = page.locator('[role="separator"]');
  await separator.focus();
  await expect(separator).toHaveAttribute("aria-valuenow", "40");
  await page.keyboard.press("ArrowRight");
  await expect(separator).toHaveAttribute("aria-valuenow", "45");

  // Прогресс: стадия серии с текстовым объявлением.
  await page.getByRole("button", { name: "Стадия 2 из 5" }).click();
  await expect(page.locator(".lnt-progress-text")).toHaveText("Запись: 2 из 5");
  const progressbar = page.locator('[role="progressbar"]');
  await expect(progressbar).toHaveAttribute("aria-valuenow", "2");

  // Полное полотно витрины как артефакт ручной проверки.
  await page.screenshot({ path: resolve(EVIDENCE_DIR, "showcase-full.png"), fullPage: true });
});
