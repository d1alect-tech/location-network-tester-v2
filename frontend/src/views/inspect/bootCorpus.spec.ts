import { expect, test } from "@playwright/test";
import { CORPUS_V2_DIR, corpusRows } from "../../testkit/catalogFixture";
import { installMockBackend } from "../../testkit/mockBackend";

/** Задача 6 (D1a/C1): boot по JOIN на корпус-фикстуре — первый АНАЛИЗИРОВАННЫЙ
 * ряд в keyset-порядке, клик дубля грузится по dir-name (200, без 409),
 * v2-dir кажет v2-disclosure, слепые ряды видны, но не выбраны. */

const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";

const DUP_DIRS = [
  "sim-quiet-20261005-150929",
  "sim-quiet-20261005-151017",
  "sim-quiet-20261005-151028",
];

test("T6-1: boot выбирает первый analyzed — тот же ряд, что первый видимый", async ({ page }) => {
  installMockBackend(page, { corpus: true });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  // Первый ВИДИМЫЙ ряд рейла — CORPUS_V2_DIR (newest + analyzed).
  const firstRow = page.locator(".col-cat tr[data-session]").first();
  await expect(firstRow).toBeVisible();
  await expect(firstRow).toHaveAttribute("data-rowkey", CORPUS_V2_DIR);
  await expect(firstRow.locator("[data-cat-analyzed='yes']")).toHaveCount(1);

  // Boot выбрал тот же ряд: роль A на нём, слот A — id той же строки.
  await expect(firstRow.locator("[data-cat-role='a']")).toHaveCount(1);
  const slotA = page.locator(".pairbar [data-pair='a']");
  await expect(slotA).toContainText("syn-quiet-seed6022");
});

test("T6-2: клик каждого дубля грузится по dir-name — 200 без 409-ленты", async ({ page }) => {
  installMockBackend(page, { corpus: true });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  for (const dir of DUP_DIRS) {
    const row = page.locator(`.col-cat tr[data-rowkey="${dir}"]`);
    await expect(row).toBeVisible();
    await row.click();
    // При dir-ключе лента ошибок остаётся скрыта (409 только по id).
    await expect(page.locator("[data-inspect-error]")).toBeHidden();
  }
});

test("T6-3: v2-dir кликабелен и extras показывает disclosure анализа", async ({ page }) => {
  installMockBackend(page, { corpus: true });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  const row = page.locator(`.col-cat tr[data-rowkey="${CORPUS_V2_DIR}"]`);
  await expect(row).toBeVisible();
  await row.click();

  // Пара держит dir-ключ (слот показывает id строки), disclosure анализа живёт.
  await expect(page.locator(".pairbar [data-pair='a']")).toContainText("syn-quiet-seed6022");
  await expect(
    page.locator(`.col-cat tr[data-rowkey="${CORPUS_V2_DIR}"] [data-cat-role='a']`),
  ).toHaveCount(1);
  const w1 = page.locator('.v6-extras details[data-extra="w1"]');
  await w1.locator("> summary").click();
  await expect(w1.locator("[data-role=panels-title]")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("[data-inspect-error]")).toBeHidden();
});

test("T6-4: manifest-less виден в рейле, но boot его не выбирает", async ({ page }) => {
  installMockBackend(page, { corpus: true });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  const blind = page.locator('.col-cat tr[data-session="06.08.2026 11-37"]');
  await expect(blind).toBeVisible();
  await expect(blind.locator("[data-cat-analyzed]")).toHaveCount(0);

  await expect(page.locator(".pairbar [data-pair='a']")).not.toContainText("06.08.2026 11-37");
});

test("T6-5: ноль analyzed — честное пустое состояние пары, без фабрикации", async ({ page }) => {
  const rows = corpusRows().map((row) => ({ ...row, metrics: false }));
  installMockBackend(page, { corpus: rows });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  // Оба слота пустые — unanalyzed в A не подставляется.
  await expect(page.locator(".pairbar [data-pair='a'] .pair-name")).toHaveText("—");
  await expect(page.locator(".pairbar [data-pair='b'] .pair-name")).toHaveText("—");
  // Лента анализа — честные «н/д», лента ошибок скрыта.
  await expect(page.locator("[data-inspect-error]")).toBeHidden();
});
