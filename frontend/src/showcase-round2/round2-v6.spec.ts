import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";

/** V6 — следующая ступень после V5: единицей работы становится ПАРА сессий.
 *  Протокол продукта сравнивает дельты, а не абсолюты, поэтому интерфейс называет
 *  обе сессии графика и показывает разницу между трассами числом. */
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const EVIDENCE_DIR = resolve(__dirname, "../../../.omo/start-work/evidence/task-redesign-round2");
const BASE = "http://127.0.0.1:4101/static/v2";
const PAGE = `${BASE}/showcase-v6.html`;

function watchConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(String(error)));
  return errors;
}

test("V6-S1: пара А/Б названа, трассы графика привязаны к сессиям", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const consoleErrors = watchConsoleErrors(page);
  await page.goto(PAGE);

  for (const section of ["shell", "catalog", "spectrum", "metrics", "capture-form", "error"]) {
    await expect(page.locator(`[data-showcase="${section}"]`)).toBeVisible();
  }

  const slotA = page.locator('.app-v6 .pairbar [data-pair="a"]');
  const slotB = page.locator('.app-v6 .pairbar [data-pair="b"]');
  await expect(slotA).toBeVisible();
  await expect(slotB).toBeVisible();
  const textA = (await slotA.textContent()) ?? "";
  const textB = (await slotB.textContent()) ?? "";
  expect(textA).toContain("стенд-А");
  expect(textB).toContain("bad-damped");
  // Слоты подписаны ролью, а не только порядком.
  expect(textA).toContain("База");
  expect(textB).toContain("Сравнение");
  await expect(page.locator(".app-v6 .pairbar [data-pair-swap]")).toBeVisible();

  // Легенда графика называет те же сессии, а не абстрактные «Сессия А/Б».
  const chips = await page
    .locator('[data-showcase="spectrum"] .chip')
    .evaluateAll((els) => els.map((el) => (el.textContent ?? "").trim()));
  expect(chips.join(" ")).toContain("стенд-А");
  expect(chips.join(" ")).toContain("bad-damped");

  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
  expect(consoleErrors).toEqual([]);
});

test("V6-S2: таблица пиков несёт дельту между трассами, читаемую без цвета", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);
  const deltas = page.locator('[data-showcase="metrics"] [data-delta]');
  await expect(deltas).toHaveCount(5);

  const rows = await deltas.evaluateAll((els) =>
    els.map((el) => ({
      value: Number(el.getAttribute("data-delta")),
      text: (el.textContent ?? "").trim(),
    })),
  );
  // Направление кодируется глифом, а не только цветом (§6).
  for (const row of rows) {
    expect(row.text).toMatch(/[▲▼—]/);
    expect(row.text).toMatch(/\d/);
  }
  // Дельта посчитана из самих трасс: демпфированный пик 22.4 кГц ниже базы.
  const damped = rows[0];
  expect(damped?.value ?? 0).toBeLessThanOrEqual(-4);
  expect(damped?.text).toContain("▼");
  // Пики, где трассы совпадают, не выдаются за изменение.
  const flat = rows[3];
  expect(Math.abs(flat?.value ?? 9)).toBeLessThanOrEqual(1);
});

test("V6-S3: слот шрифтов данных заменён на Source Code Pro", async ({ page }) => {
  await page.goto(PAGE);
  await page.waitForTimeout(300);
  const fonts = await page.evaluate(async () => {
    await document.fonts.ready;
    const cell = document.querySelector('[data-showcase="metrics"] td.num');
    return {
      mono: cell ? getComputedStyle(cell).fontFamily : "",
      ui: getComputedStyle(document.body).fontFamily,
      loaded: document.fonts.check('12px "Source Code Pro Variable"'),
    };
  });
  expect(fonts.mono).toContain("Source Code Pro Variable");
  expect(fonts.loaded).toBe(true);
  expect(fonts.ui).toContain("Golos Text Variable");
});

test("V6-S4: приборный ритм показаний, весь срез без прокрутки", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);
  const readout = await page.evaluate(() => {
    const label = document.querySelector(".app-v6 .readout-label");
    const value = document.querySelector(".app-v6 .readout-value");
    const main = document.querySelector(".app-v6 .col-main");
    const plot = document.querySelector('[data-showcase="spectrum"] .spectrum-plot');
    const cs = (el: Element | null) => (el ? getComputedStyle(el) : null);
    return {
      labelSize: Number.parseFloat(cs(label)?.fontSize ?? "0"),
      labelTransform: cs(label)?.textTransform ?? "",
      valueSize: Number.parseFloat(cs(value)?.fontSize ?? "0"),
      valueNumeric: cs(value)?.fontVariantNumeric ?? "",
      count: document.querySelectorAll(".app-v6 .readout-value").length,
      mainScroll: main?.scrollHeight ?? 0,
      mainClient: main?.clientHeight ?? 0,
      docScroll: document.documentElement.scrollHeight,
      docClient: document.documentElement.clientHeight,
      plotHeight: plot?.getBoundingClientRect().height ?? 0,
    };
  });
  expect(readout.count).toBe(7);
  expect(readout.labelSize).toBe(11);
  expect(readout.labelTransform).toBe("uppercase");
  expect(readout.valueSize).toBeGreaterThanOrEqual(16);
  expect(readout.valueNumeric).toContain("tabular-nums");
  expect(readout.docScroll).toBeLessThanOrEqual(readout.docClient + 1);
  expect(readout.mainScroll).toBeLessThanOrEqual(readout.mainClient + 1);
  // График остаётся героем: больше, чем в V5 (303.5px).
  expect(readout.plotHeight, `высота графика V6: ${readout.plotHeight}`).toBeGreaterThanOrEqual(
    320,
  );
});

/** Измеряет фактическую ширину одной и той же числовой строки в таблице пиков. */
async function peakDigitsWidth(page: Page, url: string): Promise<number> {
  await page.goto(url);
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  return page.evaluate(() => {
    const cell = document.querySelector('[data-showcase="metrics"] tbody td.num');
    if (cell === null) return 0;
    const range = document.createRange();
    range.selectNodeContents(cell);
    return range.getBoundingClientRect().width;
  });
}

test("V6-S6: смена шрифта данных не расширяет числовые колонки", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const jetbrains = await peakDigitsWidth(page, `${BASE}/showcase-v5.html`);
  const sourceCodePro = await peakDigitsWidth(page, PAGE);
  expect(jetbrains).toBeGreaterThan(0);
  // Измерено: у обоих моноширинных одинаковый шаг знака (43.2px на «22 418» в 12px),
  // поэтому контракт — «не шире»: смена слота §3 не должна распирать числовые колонки.
  expect(
    sourceCodePro,
    `Source Code Pro ${sourceCodePro.toFixed(1)}px против JetBrains Mono ${jetbrains.toFixed(1)}px`,
  ).toBeLessThanOrEqual(jetbrains);
});

test("V6-S5: индекс ведёт на V6, витрина снимается артефактом", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${BASE}/showcase-round2.html`);
  await expect(page.locator('a[href="showcase-v6.html"]')).toBeVisible();
  await page.goto(PAGE);
  await page.screenshot({ path: resolve(EVIDENCE_DIR, "v6-compare-1280.png"), fullPage: true });
});

/** Каталог V6: структура вместо плоского списка (жалоба «нет структуры»). */
const CATALOG = '[data-showcase="catalog"]';

test("V6-S7: каталог сгруппирован по дням, каждая группа названа и посчитана", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);

  const groups = page.locator(`${CATALOG} [data-cat-group]`);
  await expect(groups).toHaveCount(5);

  const shape = await groups.evaluateAll((els) =>
    els.map((el) => ({
      date: el.getAttribute("data-cat-group") ?? "",
      count: Number(el.querySelector("[data-cat-count]")?.textContent ?? "0"),
      text: (el.textContent ?? "").trim(),
    })),
  );
  // Дни идут от свежего к старому, как и весь каталог.
  const dates = shape.map((group) => group.date);
  expect([...dates].sort((left, right) => right.localeCompare(left))).toEqual(dates);
  // Счётчики групп в сумме дают весь список.
  expect(shape.reduce((sum, group) => sum + group.count, 0)).toBe(10);
  // Заголовок называет день словами, а не только машинной датой.
  expect(shape[0]?.text).toContain("август");

  // Заголовок дня тянется на всю таблицу: display:flex на th отменяет colspan
  // и схлопывает его до первой колонки — тогда от «29 августа» видно только «29».
  const spans = await page.evaluate((sel) => {
    const root = document.querySelector(sel);
    const group = root?.querySelector("[data-cat-group] th");
    const row = root?.querySelector("[data-session]");
    if (!(group instanceof HTMLElement) || !(row instanceof HTMLElement)) return null;
    return { group: group.getBoundingClientRect().width, row: row.getBoundingClientRect().width };
  }, CATALOG);
  expect(spans).not.toBeNull();
  expect(spans?.group ?? 0).toBeGreaterThanOrEqual((spans?.row ?? 0) - 1);

  // Каждая строка лежит в группе своего дня.
  const misplaced = await page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (root === null) return ["нет каталога"];
    const bad: string[] = [];
    let current = "";
    for (const row of root.querySelectorAll("tbody tr")) {
      const group = row.getAttribute("data-cat-group");
      if (group !== null) {
        current = group;
        continue;
      }
      const date = row.getAttribute("data-cat-date");
      if (date !== current) bad.push(`${row.getAttribute("data-session")}: ${date} в ${current}`);
    }
    return bad;
  }, CATALOG);
  expect(misplaced).toEqual([]);
});

test("V6-S8: одна плотная строка на сессию вместо двух", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);

  await expect(page.locator(`${CATALOG} [data-session]`)).toHaveCount(10);
  // 10 сессий + 5 заголовков дней: подстроки-дубля с тем же id больше нет.
  await expect(page.locator(`${CATALOG} tbody tr`)).toHaveCount(15);

  const rows = await page
    .locator(`${CATALOG} [data-session]`)
    .evaluateAll((els) => els.map((el) => el.getBoundingClientRect().height));
  for (const height of rows) {
    expect(height).toBeGreaterThanOrEqual(24);
    expect(height).toBeLessThanOrEqual(30);
  }

  // Тип — закрытый словарь из четырёх значений: обрезанные «Симул…» и «Самошум»
  // перестают различаться, поэтому эта колонка обязана вмещать самое длинное слово.
  const clipped = await page.evaluate((sel) => {
    const bad: string[] = [];
    for (const row of document.querySelectorAll(`${sel} [data-session]`)) {
      const cell = row.children[2];
      if (!(cell instanceof HTMLElement)) continue;
      if (cell.scrollWidth > cell.clientWidth + 1) {
        bad.push(`${cell.textContent ?? ""} ${cell.scrollWidth}>${cell.clientWidth}`);
      }
    }
    return bad;
  }, CATALOG);
  expect(clipped, "тип сессии обрезан").toEqual([]);
});

test("V6-S9: каталог сортируется кликом по колонке и ищет по метке", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);

  const labels = async (): Promise<string[]> =>
    page
      .locator(`${CATALOG} [data-session]:visible [data-cat-label]`)
      .evaluateAll((els) => els.map((el) => (el.textContent ?? "").trim()));

  const sortLabel = page.locator(`${CATALOG} [data-cat-sort="label"]`);
  await sortLabel.click();
  const ascending = await labels();
  // Порядок сверяем той же коллацией, что и страница: у Node и браузера она разная.
  const monotone = await page.evaluate(
    (items) =>
      items.every((item, index) => index === 0 || items[index - 1]!.localeCompare(item, "ru") <= 0),
    ascending,
  );
  expect(monotone, ascending.join(" | ")).toBe(true);
  expect(ascending).toHaveLength(10);
  await expect(sortLabel).toHaveAttribute("aria-sort", "ascending");

  await sortLabel.click();
  const descending = await labels();
  expect(descending).toEqual([...ascending].reverse());
  await expect(sortLabel).toHaveAttribute("aria-sort", "descending");

  // Сортировка по метке распускает группировку по дням: одно или другое, без вранья.
  await expect(page.locator(`${CATALOG} [data-cat-group]`)).toHaveCount(0);

  const search = page.locator(`${CATALOG} [data-cat-search]`);
  await search.fill("стенд");
  // Состав найденного, а не порядок: поиск не отменяет выбранную сортировку.
  expect([...(await labels())].sort()).toEqual(["стенд-А", "стенд-Б"]);
  await expect(page.locator(`${CATALOG} [data-cat-found]`)).toContainText("2");

  await search.fill("такого-нет");
  expect(await labels()).toEqual([]);
  await expect(page.locator(`${CATALOG} [data-cat-empty]`)).toBeVisible();

  await page.locator(`${CATALOG} [data-cat-clear]`).click();
  expect(await labels()).toHaveLength(10);
  // Очистка возвращает и группы по дням.
  await expect(page.locator(`${CATALOG} [data-cat-group]`)).toHaveCount(5);
});

test("V6-S10: каталог показывает роли сессий и совпадает с полосой пары", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);

  const roleA = page.locator(`${CATALOG} [data-cat-role="a"]`);
  const roleB = page.locator(`${CATALOG} [data-cat-role="b"]`);
  await expect(roleA).toHaveCount(1);
  await expect(roleB).toHaveCount(1);

  // Роль читается текстом, а не только цветом (§6).
  await expect(roleA).toContainText("А");
  await expect(roleB).toContainText("Б");

  // Каталог и полоса пары говорят об одних и тех же сессиях.
  const rowA = page
    .locator(`${CATALOG} [data-session]`)
    .filter({ has: page.locator('[data-cat-role="a"]') });
  const rowB = page
    .locator(`${CATALOG} [data-session]`)
    .filter({ has: page.locator('[data-cat-role="b"]') });
  await expect(rowA.locator("[data-cat-label]")).toHaveText("стенд-А");
  await expect(rowB.locator("[data-cat-label]")).toHaveText("bad-damped");

  // Самошум назван инструментальным базисом своего дня, а не просто ещё одной записью.
  const noise = page.locator(`${CATALOG} [data-cat-role="noise"]`);
  await expect(noise).toHaveCount(1);
  const noiseRow = page
    .locator(`${CATALOG} [data-session]`)
    .filter({ has: page.locator('[data-cat-role="noise"]') });
  await expect(noiseRow.locator("[data-cat-label]")).toHaveText("самошум");
});
