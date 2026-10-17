import { expect, test } from "@playwright/test";
import { installMockBackend } from "../../testkit/mockBackend";
import { REASON_NO_ARTIFACT } from "./pairLoadOutcome";

/** Задача 7 (G1/Q3 = A): причина отсутствия analysis-v2 живёт SIBLING-узлом
 * в <summary> рядом со счётчиком — видна БЕЗ ручного клика по раскрытию.
 * 25/26 сессий корпуса не несут указателя v2: непроанализированная база
 * обязана называть причину уже на первом рендере свёрнутой шапки. */

const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";
/** Непроанализированная сессия корпуса (dir first-capture): манифест есть,
 * metrics.json нет; loadKey не-duplicate строки — её session_id. */
const UNANALYZED_ID = "cap-20260805-163312-1e5bc5a7";

test("T7-1: непроанализированная база — причина видна в свёрнутой шапке", async ({ page }) => {
  installMockBackend(page, { corpus: true });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  // Замена базы пары: кнопка «А» непроанализированного ряда (dir-ключ).
  const row = page.locator(`.col-cat tr[data-rowkey="${UNANALYZED_ID}"]`);
  await expect(row).toBeVisible();
  await row.locator('[data-assign="a"]').click();

  // Раскрытие НЕ открывалось — причина обязана жить в самой <summary>.
  const w1 = page.locator('.v6-extras details[data-extra="w1"]');
  await expect(w1).toHaveJSProperty("open", false);
  const reason = w1.locator("> summary [data-role=w1-absence-reason]");
  await expect(reason).toBeVisible();
  await expect(reason).toHaveText(REASON_NO_ARTIFACT);
  // Узел — сиблинг счётчика, значение счётчика не перезаписано.
  await expect(w1.locator("> summary [data-role=w1-sum-value]")).toBeVisible();
});

test("T7-2: analyzed-база (указатель v2 на месте) — узел причины скрыт", async ({ page }) => {
  installMockBackend(page, { corpus: true });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  // Boot выбрал CORPUS_V2_DIR — единственный каталог корпуса с указателем v2;
  // дожидаемся дочитки панелей (чипы отсутствующих артефактов).
  const w1 = page.locator('.v6-extras details[data-extra="w1"]');
  await expect(w1.locator("[data-absent-panel]")).toHaveCount(6);
  await expect(w1).toHaveJSProperty("open", false);
  await expect(w1.locator("> summary [data-role=w1-absence-reason]")).toHaveCount(1);
  await expect(w1.locator("> summary [data-role=w1-absence-reason]")).toBeHidden();
});
