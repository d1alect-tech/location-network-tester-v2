import { type Page, expect, test } from "@playwright/test";
import { CORPUS_DUPLICATE_SESSION_ID, type CorpusRow } from "../../testkit/catalogFixture";
import { installMockBackend } from "../../testkit/mockBackend";

/** M1-клик-протокол выбора A/B (план inspect-v1-selection-ux, todo 6; IS-4:
 * паритет с прототипом V1 — приёмка task-11/m1-rework/acceptance.txt, пункты
 * 1-10). Машиночитаемые значения только: атрибуты, токены, счётчики; никаких
 * тайминг-ассертов на транзиенты — пульс ловится MutationObserver-ом по
 * токену [data-pulse] (ставится/снимается), не по часам. */

const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";

/** Мини-мир: boot-пара alpha+beta (первые две analyzed в keyset-порядке),
 * gamma — незапаренная analyzed, дубль-триплет с одним session_id,
 * отказной ch2-ряд (metrics нет) и каталог без манифеста. */
function row(seed: Partial<CorpusRow> & { readonly dir: string }): CorpusRow {
  return {
    sessionId: null,
    health: "ok",
    createdUtc: null,
    sessionType: "capture",
    profile: null,
    label: null,
    manifest: true,
    manifestError: null,
    metrics: false,
    spectrum: false,
    waveform: true,
    ch2: false,
    analysisV2: false,
    ...seed,
  };
}

const DIR_COPY = "sim-quiet-20261005-151017";
const DIR_ARCHIVE = "sim-quiet-20261005-151028";
const DIR_DUP_BASE = "sim-quiet-20261005-150929";
const REFUSED_ID = "cap-refused-ch2-9f";

const WORLD: readonly CorpusRow[] = [
  row({
    dir: "sess-alpha",
    sessionId: "sess-alpha",
    createdUtc: "2026-10-10T10:00:00Z",
    metrics: true,
    spectrum: true,
    label: "стенд-А",
  }),
  row({
    dir: "sess-beta",
    sessionId: "sess-beta",
    createdUtc: "2026-10-09T10:00:00Z",
    metrics: true,
    spectrum: true,
    label: "стенд-Б",
  }),
  row({
    dir: "sess-gamma",
    sessionId: "sess-gamma",
    createdUtc: "2026-10-08T10:00:00Z",
    metrics: true,
    spectrum: true,
    label: "стенд-В",
  }),
  row({
    dir: DIR_DUP_BASE,
    sessionId: CORPUS_DUPLICATE_SESSION_ID,
    health: "duplicate_id",
    createdUtc: "2026-10-05T15:09:29Z",
    sessionType: "simulate",
  }),
  row({
    dir: DIR_COPY,
    sessionId: CORPUS_DUPLICATE_SESSION_ID,
    health: "duplicate_id",
    createdUtc: "2026-10-05T15:10:17Z",
    sessionType: "simulate",
    label: "копия",
  }),
  row({
    dir: DIR_ARCHIVE,
    sessionId: CORPUS_DUPLICATE_SESSION_ID,
    health: "duplicate_id",
    createdUtc: "2026-10-05T15:10:28Z",
    sessionType: "simulate",
    label: "архив",
  }),
  row({
    dir: "cap-refused-ch2",
    sessionId: REFUSED_ID,
    createdUtc: "2026-08-05T16:39:15Z",
    ch2: true,
    label: "отказ-ch2",
  }),
  row({ dir: "06.10.2026 11-37", health: "corrupt_manifest", manifest: false, waveform: false }),
];

/** Токен-лог пульса: MutationObserver в контексте страницы пишет data-assign
 * каждой кнопки, на которой появился [data-pulse]. Транзиент ловится без
 * гонки с 200ms animationend. */
function installPulseObserver(page: Page): Promise<void> {
  return page.evaluate(() => {
    const log = { pulses: [] as string[] };
    (window as unknown as { __m1Pulse: string[] }).__m1Pulse = log.pulses;
    new MutationObserver((records) => {
      for (const record of records) {
        const target = record.target as Element;
        if (target.hasAttribute("data-pulse")) {
          log.pulses.push(target.getAttribute("data-assign") ?? "");
        }
      }
    }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ["data-pulse"] });
  });
}

async function pulseCount(page: Page): Promise<number> {
  return page.evaluate(
    () => (window as unknown as { __m1Pulse?: string[] }).__m1Pulse?.length ?? -1,
  );
}

test("M1: кнопки А/Б видимы на каждой строке; клик тела → B; «А»/«Б» — move; no-op; слот-клик — фокус+пульс без мутации; KeyA/KeyB", async ({
  page,
}) => {
  installMockBackend(page, { corpus: WORLD });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  // (1) обе кнопки на КАЖДОЙ строке видимы без hover.
  const rows = page.locator(".tbl-cat tbody tr[data-session]");
  await expect(rows).toHaveCount(8);
  await expect(rows.locator('[data-assign="a"]')).toHaveCount(8);
  await expect(rows.locator('[data-assign="b"]')).toHaveCount(8);
  for (const button of await rows.locator('[data-assign="a"], [data-assign="b"]').all()) {
    await expect(button).toBeVisible();
  }

  const slotA = page.locator(".pairbar [data-pair='a']");
  const slotB = page.locator(".pairbar [data-pair='b']");
  await expect(slotA).toContainText("стенд-А");
  await expect(slotB).toContainText("стенд-Б");

  // (2) клик тела незапаренной строки → B, эхо data-in-pair="b".
  const gamma = page.locator('tr[data-rowkey="sess-gamma"]');
  await gamma.click();
  await expect(slotA).toContainText("стенд-А");
  await expect(slotB).toContainText("стенд-В");
  await expect(gamma).toHaveAttribute("data-in-pair", "b");

  // (3) «А» на строке в B → move: строка в A, B освобождён.
  await gamma.locator('[data-assign="a"]').click();
  await expect(slotA).toContainText("стенд-В");
  await expect(slotB).toContainText("—");
  await expect(gamma).toHaveAttribute("data-in-pair", "a");
  // Нажатая кнопка «А» получает цвет роли из переменной --lnt-role-a (каталог
  // стилей жив после переноса переменных из v6.css в catalogAssign.css).
  expect(
    await gamma.locator('[data-assign="a"]').evaluate((el) => getComputedStyle(el).color),
  ).toBe("rgb(157, 180, 255)");

  // (4) «Б» на строке в A → move: строка в B, A освобождён.
  await gamma.locator('[data-assign="b"]').click();
  await expect(slotA).toContainText("—");
  await expect(slotB).toContainText("стенд-В");
  await expect(gamma).toHaveAttribute("data-in-pair", "b");

  // (5) клик тела строки уже в B → no-op, пара не меняется.
  await gamma.click();
  await expect(slotA).toContainText("—");
  await expect(slotB).toContainText("стенд-В");
  await expect(gamma).toHaveAttribute("data-in-pair", "b");

  // (6) слот-клик: фокус первого ряда рейла, токен [data-pulse] появляется и
  // снимается по animationend; пара не меняется, арм не включается.
  await installPulseObserver(page);
  await slotA.click();
  await expect(page.locator(".tbl-cat tbody tr[data-session]").first()).toBeFocused();
  await expect.poll(() => pulseCount(page)).toBe(8);
  expect(
    await page.evaluate(() =>
      (window as unknown as { __m1Pulse?: string[] }).__m1Pulse?.every((slot) => slot === "a"),
    ),
  ).toBe(true);
  await expect(page.locator("[data-pulse]")).toHaveCount(0);
  await expect(slotA).toContainText("—");
  await expect(slotB).toContainText("стенд-В");
  await expect(slotA).toHaveAttribute("aria-pressed", "false");

  // (7) KeyA/KeyB на сфокусированном ряду: event.code — физические клавиши,
  // RU-раскладка не мешает (key = «и», код KeyB).
  await page.locator('tr[data-rowkey="sess-beta"]').focus();
  await page.keyboard.press("KeyA");
  await expect(slotA).toContainText("стенд-Б");
  await expect(slotB).toContainText("стенд-В");
  const alpha = page.locator('tr[data-rowkey="sess-alpha"]');
  await alpha.focus();
  await alpha.evaluate((el) =>
    el.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyB", key: "и", bubbles: true })),
  );
  await expect(slotA).toContainText("стенд-Б");
  await expect(slotB).toContainText("стенд-А");
});

test("M1 reduced-motion: слот-клик фокусирует рейл, токен пульса не ставится вовсе", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  installMockBackend(page, { corpus: WORLD });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();
  await expect(page.locator(".pairbar [data-pair='b']")).toContainText("стенд-Б");

  await installPulseObserver(page);
  await page.locator(".pairbar [data-pair='b']").click();
  await expect(page.locator(".tbl-cat tbody tr[data-session]").first()).toBeFocused();
  // focusRail под reduced-motion возвращается ДО установки токена —
  // после фокуса токенов нет и не будет (код установки уже отработал).
  expect(await pulseCount(page)).toBe(0);
  await expect(page.locator("[data-pulse]")).toHaveCount(0);
  await expect(page.locator(".pairbar [data-pair='b']")).toContainText("стенд-Б");
});

test("M1 job-busy: pairbar залочен, строки и кнопки рейла живы", async ({ page }) => {
  const backend = installMockBackend(page, { corpus: WORLD });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();
  const slotA = page.locator(".pairbar [data-pair='a']");
  const slotB = page.locator(".pairbar [data-pair='b']");
  await expect(slotA).toContainText("стенд-А");

  // Задача анализа v2 в полёте: слоты и swap парбара заблокированы.
  await page.locator(".v6-extras .av2-cta").click();
  await expect(page.locator(".pair-slot[data-pair='a']")).toBeDisabled();
  await expect(page.locator(".pair-slot[data-pair='b']")).toBeDisabled();
  await expect(page.locator(".pairbar [data-pair-swap]")).toBeDisabled();

  // Рейл жив: кнопка «А» незапаренной строки назначает, клик тела — тоже.
  await page.locator('tr[data-rowkey="sess-gamma"]').locator('[data-assign="a"]').click();
  await expect(slotA).toContainText("стенд-В");
  await page.locator('tr[data-rowkey="sess-alpha"]').click();
  await expect(slotB).toContainText("стенд-А");

  // Терминал задачи снимает блокировку.
  backend.pumpAll();
  await expect(page.locator(".pair-slot[data-pair='a']")).not.toBeDisabled();
  await expect(page.locator(".pairbar [data-pair-swap]")).not.toBeDisabled();
});

test("M1 честный отказ: «А» отказной ch2-строки — сессия в слоте, лента ошибки с причиной, Δ сброшен", async ({
  page,
}) => {
  installMockBackend(page, { corpus: WORLD });
  // Отказ анализатора на ch2-захвате: сервер отвечает 409 с причиной
  // (паттерн серверного detail — V6-P10).
  const refusal = "отклонено анализатором: ch2 under_range";
  await page.route(`**/api/sessions/${REFUSED_ID}*`, (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: refusal }),
    }),
  );
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  // До отказа Δ посчитан по спектрам пары (не прочерк).
  await expect(page.locator('[data-pair-delta="mean"]')).toContainText("дБ");

  const refused = page.locator(`tr[data-rowkey="${REFUSED_ID}"]`);
  await refused.locator('[data-assign="a"]').click();

  // Сессия осела в слоте и держится там после честного провала загрузки.
  const slotA = page.locator(".pairbar [data-pair='a']");
  await expect(slotA).toContainText("отказ-ch2");
  const band = page.locator("[data-inspect-error]");
  await expect(band).toBeVisible({ timeout: 15_000 });
  await expect(band).toContainText(refusal);
  await expect(slotA).toContainText("отказ-ch2");
  await expect(refused).toHaveAttribute("data-in-pair", "a");

  // Δ-бейджи сброшены в прочерк — провал не оставляет старую сводку.
  await expect(page.locator('[data-pair-delta="mean"]')).toHaveText("Δср —");
  await expect(page.locator('[data-pair-delta="max"]')).toHaveText("Δmax —");
});

test("M1 дубль-триплет: кнопки несут dir-name loadKey, копия и архив — разные цели", async ({
  page,
}) => {
  installMockBackend(page, { corpus: WORLD });
  await page.goto(BASE);
  await expect(page.locator(".app-v6")).toBeVisible();

  const copy = page.locator(`tr[data-rowkey="${DIR_COPY}"]`);
  const archive = page.locator(`tr[data-rowkey="${DIR_ARCHIVE}"]`);
  // title кнопки дубля = имя каталога (loadKey), не общий session_id.
  await expect(copy.locator('[data-assign="a"]')).toHaveAttribute("title", DIR_COPY);
  await expect(archive.locator('[data-assign="a"]')).toHaveAttribute("title", DIR_ARCHIVE);

  // «А» копии: пара берёт dir-ключ, эхо — на строке копии, не на сиблингах.
  await copy.locator('[data-assign="a"]').click();
  await expect(page.locator(".pairbar [data-pair='a']")).toContainText("копия");
  await expect(copy).toHaveAttribute("data-in-pair", "a");
  await expect(page.locator(`tr[data-rowkey="${DIR_DUP_BASE}"]`)).not.toHaveAttribute(
    "data-in-pair",
    "a",
  );

  // «А» архива — другая цель: выбор переносится, копия освобождена.
  await archive.locator('[data-assign="a"]').click();
  await expect(page.locator(".pairbar [data-pair='a']")).toContainText("архив");
  await expect(archive).toHaveAttribute("data-in-pair", "a");
  await expect(copy).not.toHaveAttribute("data-in-pair", "a");
});
