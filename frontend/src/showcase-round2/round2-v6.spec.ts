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
      spectrumPanel:
        document.querySelector('[data-showcase="spectrum"]')?.getBoundingClientRect().height ?? 0,
      band: document.querySelector(".app-v6 .analysis-band")?.getBoundingClientRect().height ?? 0,
      readoutPanel: document.querySelector(".app-v6 .readout")?.getBoundingClientRect().height ?? 0,
      peaksPanel:
        document.querySelector('[data-showcase="metrics"]')?.getBoundingClientRect().height ?? 0,
      mainBox: main?.getBoundingClientRect().height ?? 0,
      gramHeight:
        document.querySelector("[data-spectrogram-canvas]")?.getBoundingClientRect().height ?? 0,
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
  // Сигнальная зона — спектр вместе со спектрограммой: вторая дорожка берёт высоту
  // у первой, поэтому сумма остаётся на уровне прежнего графика, а сам спектр не вырождается.
  const signalZone = readout.plotHeight + readout.gramHeight;
  expect(
    signalZone,
    `спектр ${readout.plotHeight} + спектрограмма ${readout.gramHeight}`,
  ).toBeGreaterThanOrEqual(320);
  expect(readout.plotHeight).toBeGreaterThanOrEqual(210);
  expect(readout.gramHeight).toBeGreaterThanOrEqual(88);
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

test("V6-S17: каталог держит высоту колонки и не режет дату", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);

  const fills = async (): Promise<number> =>
    page.evaluate((sel) => {
      const panel = document.querySelector(sel);
      const column = document.querySelector(".app-v6 .col-cat");
      if (!(panel instanceof HTMLElement) || !(column instanceof HTMLElement)) return 0;
      return panel.getBoundingClientRect().height / column.getBoundingClientRect().height;
    }, CATALOG);

  // Панель занимает всю колонку, иначе под коротким списком зияет дыра.
  expect(await fills(), "полный список").toBeGreaterThan(0.98);
  await page.locator(`${CATALOG} [data-cat-search]`).fill("такого-нет");
  await expect(page.locator(`${CATALOG} [data-cat-empty]`)).toBeVisible();
  expect(await fills(), "пустой результат").toBeGreaterThan(0.98);
  await page.locator(`${CATALOG} [data-cat-clear]`).click();

  // При распущенных группах колонка показывает ПОЛНУЮ дату, а ширина была под «14:30».
  await page.locator(`${CATALOG} [data-cat-sort="label"]`).click();
  const clippedDate = await page.evaluate((sel) => {
    const bad: string[] = [];
    for (const row of document.querySelectorAll(`${sel} [data-session]`)) {
      const cell = row.children[3];
      if (!(cell instanceof HTMLElement)) continue;
      if (cell.scrollWidth > cell.clientWidth + 1) {
        bad.push(`${cell.textContent ?? ""} ${cell.scrollWidth}>${cell.clientWidth}`);
      }
    }
    return bad;
  }, CATALOG);
  expect(clippedDate, "дата обрезана").toEqual([]);

  // Короткие метки обязаны читаться целиком: широкая дата сжала «самошум» до «са…».
  const clippedLabel = await page.evaluate((sel) => {
    const bad: string[] = [];
    for (const node of document.querySelectorAll(`${sel} [data-cat-label]`)) {
      if (!(node instanceof HTMLElement)) continue;
      const text = (node.textContent ?? "").trim();
      if (text.length > 10) continue;
      if (node.scrollWidth > node.clientWidth + 1) {
        bad.push(`${text} ${node.scrollWidth}>${node.clientWidth}`);
      }
    }
    return bad;
  }, CATALOG);
  expect(clippedLabel, "короткая метка обрезана").toEqual([]);
});

test("V6-S18: дельта спокойна там, где трассы не расходятся", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);
  // Дефолт — уровень сравнения; спокойствие дельты проверяем в её собственном режиме.
  await page.locator('[data-spectrogram-mode="delta"]').click();

  const canvas = await page.locator("[data-spectrogram-canvas]").boundingBox();
  const marker = await page.locator('[data-peak="0"]').boundingBox();
  expect(canvas).not.toBeNull();
  expect(marker).not.toBeNull();
  if (canvas === null || marker === null) return;

  const readout = page.locator("[data-spectrogram-readout]");
  const swingAt = async (x: number): Promise<number> => {
    const values: number[] = [];
    for (let step = 0; step < 12; step += 1) {
      await page.mouse.move(x, canvas.y + ((step + 0.5) / 12) * canvas.height);
      const match = /(-|−|\+)?\d+[.,]\d+\s*дБ/.exec((await readout.textContent()) ?? "");
      if (match === null) continue;
      values.push(Number(match[0].replace(/\s*дБ/, "").replace("−", "-").replace(",", ".")));
    }
    return Math.max(...values) - Math.min(...values);
  };

  // Вдали от демпфированного пика трассы совпадают: собственная рябь дельты там —
  // декоративный муар, маскирующий единственное настоящее различие.
  const quiet = await swingAt(canvas.x + canvas.width * 0.9);
  const atPeak = await swingAt(marker.x + marker.width / 2);
  expect(quiet, `размах вдали от пика ${quiet.toFixed(2)} дБ`).toBeLessThan(1);
  expect(atPeak, `размах на пике ${atPeak.toFixed(2)} дБ`).toBeGreaterThan(quiet);
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

  // Самошум своего чипа не получает: колонка типа и так его называет, а дубль сжимал метку.
  await expect(page.locator(`${CATALOG} [data-cat-role]`)).toHaveCount(2);
  const noiseRow = page.locator(`${CATALOG} [data-session]`).filter({ hasText: "Самошум" });
  await expect(noiseRow.locator("[data-cat-label]")).toHaveText("самошум");
});

/** Спектрограмма V6: вторая дорожка под спектром, делящая с ним ось частот.
 *  Главный дефицит продукта — спектрограмма и линейный спектр живут порознь и
 *  не синхронизированы; здесь они по построению стоят на одной шкале. */
const GRAM = "[data-spectrogram]";

test("V6-S11: спектрограмма делит ось частот с линейным спектром", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const consoleErrors = watchConsoleErrors(page);
  await page.goto(PAGE);

  await expect(page.locator(GRAM)).toBeVisible();

  const geometry = await page.evaluate(() => {
    const canvas = document.querySelector("[data-spectrogram-canvas]");
    const over = document.querySelector('[data-showcase="spectrum"] .u-over');
    if (!(canvas instanceof HTMLElement) || !(over instanceof HTMLElement)) return null;
    const left = canvas.getBoundingClientRect();
    const right = over.getBoundingClientRect();
    return {
      gramLeft: left.left,
      gramRight: left.right,
      plotLeft: right.left,
      plotRight: right.right,
    };
  });
  expect(geometry).not.toBeNull();
  // Полотно спектрограммы стоит ровно под областью данных графика: одна шкала частот.
  const where = `полотно ${geometry?.gramLeft}..${geometry?.gramRight} | график ${geometry?.plotLeft}..${geometry?.plotRight}`;
  expect(
    Math.abs((geometry?.gramLeft ?? 0) - (geometry?.plotLeft ?? 0)),
    where,
  ).toBeLessThanOrEqual(1);
  expect(
    Math.abs((geometry?.gramRight ?? 0) - (geometry?.plotRight ?? 0)),
    where,
  ).toBeLessThanOrEqual(1);

  // Полотно действительно закрашено, а не осталось пустым.
  const painted = await page.evaluate(() => {
    const canvas = document.querySelector("[data-spectrogram-canvas]");
    if (!(canvas instanceof HTMLCanvasElement)) return 0;
    const ctx = canvas.getContext("2d");
    if (ctx === null) return 0;
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
    let opaque = 0;
    for (let index = 3; index < data.length; index += 4) {
      if ((data[index] ?? 0) > 0) opaque += 1;
    }
    return opaque / (data.length / 4);
  });
  expect(painted).toBeGreaterThan(0.9);
  expect(consoleErrors).toEqual([]);
});

test("V6-S12: спектрограмма переключается между А, Б и дельтой", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);

  const modes = page.locator("[data-spectrogram-mode]");
  await expect(modes).toHaveCount(3);

  // По умолчанию открыт уровень сравнения: спокойная дельта вдали от пиков почти
  // чёрная и читается пустым полем; дельта — в один клик и числом в таблице пиков.
  const active = page.locator('[data-spectrogram-mode][aria-pressed="true"]');
  await expect(active).toHaveCount(1);
  await expect(active).toHaveAttribute("data-spectrogram-mode", "b");

  const snapshot = async (): Promise<string> =>
    page.evaluate(() => {
      const canvas = document.querySelector("[data-spectrogram-canvas]");
      return canvas instanceof HTMLCanvasElement ? canvas.toDataURL().slice(-96) : "";
    });

  const levelImage = await snapshot();
  await page.locator('[data-spectrogram-mode="delta"]').click();
  await expect(page.locator('[data-spectrogram-mode="delta"]')).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const deltaImage = await snapshot();
  // Переключение действительно перерисовывает полотно, а не только подсветку кнопки.
  expect(deltaImage).not.toBe(levelImage);

  // Шкала цвета названа и снабжена числами в дБ.
  const scale = page.locator("[data-spectrogram-scale]");
  await expect(scale).toBeVisible();
  await expect(scale).toContainText("дБ");
});

test("V6-S13: курсор спектрограммы называет частоту, время и значение", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);

  const readout = page.locator("[data-spectrogram-readout]");
  const canvas = page.locator("[data-spectrogram-canvas]");
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  if (box === null) return;

  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  const text = (await readout.textContent()) ?? "";
  expect(text).toMatch(/Гц/);
  // \b не работает на кириллице: \w — только ASCII, границы у «с» нет.
  expect(text).toMatch(/\d\s?мс|\d\s?с/);
  expect(text).toMatch(/дБ/);
  expect(text).toMatch(/\d/);
});

test("V6-S14: органы каталога и спектрограммы держат геометрию и фокус ТЗ", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);

  // §2.3: инпут 32px, шапка таблицы 30-32px; §6: цели ≥28px.
  const small = await page.evaluate(() => {
    const bad: string[] = [];
    const probes: readonly [string, number][] = [
      ["[data-cat-search]", 32],
      ["[data-cat-sort] .cat-sort", 30],
      ["[data-cat-clear]", 28],
      ["[data-spectrogram-mode]", 28],
    ];
    for (const [selector, min] of probes) {
      for (const node of document.querySelectorAll(selector)) {
        const height = node.getBoundingClientRect().height;
        if (height < min - 0.5) bad.push(`${selector} ${height} < ${min}`);
      }
    }
    return bad;
  });
  expect(small, "геометрия контролов").toEqual([]);

  // §2.3: фокус-рамка видима, а не снята outline:none.
  const focusable: readonly string[] = [
    "[data-cat-search]",
    "[data-cat-clear]",
    '[data-cat-sort="label"] .cat-sort',
    '[data-spectrogram-mode="a"]',
  ];
  for (const selector of focusable) {
    await page.locator(selector).focus();
    const ring = await page.evaluate((sel) => {
      const node = document.querySelector(sel);
      if (node === null) return { width: "", style: "" };
      const cs = getComputedStyle(node);
      return { width: cs.outlineWidth, style: cs.outlineStyle };
    }, selector);
    expect(ring.style, `${selector}: стиль рамки фокуса`).not.toBe("none");
    expect(
      Number.parseFloat(ring.width),
      `${selector}: толщина рамки фокуса`,
    ).toBeGreaterThanOrEqual(2);
  }
});

test("V6-S15: средняя по времени дельта полотна совпадает с колонкой дельты", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);
  // Дефолт — уровень сравнения; согласованность с таблицей — свойство дельта-режима.
  await page.locator('[data-spectrogram-mode="delta"]').click();

  // Колонка Δ первой строки таблицы пиков — демпфированный пик 22.4 кГц.
  const column = Number(
    await page.locator('[data-showcase="metrics"] [data-delta]').first().getAttribute("data-delta"),
  );
  expect(Number.isFinite(column)).toBe(true);

  // Тот же пик на графике: маркер даёт координату частоты.
  const marker = await page.locator('[data-peak="0"]').boundingBox();
  const canvas = await page.locator("[data-spectrogram-canvas]").boundingBox();
  expect(marker).not.toBeNull();
  expect(canvas).not.toBeNull();
  if (marker === null || canvas === null) return;

  const readout = page.locator("[data-spectrogram-readout]");
  const x = marker.x + marker.width / 2;
  // 24 пробы при 48 бинах и 4 периодах попадают в целое число циклов: сумма модуляции точно ноль.
  const samples: number[] = [];
  for (let step = 0; step < 24; step += 1) {
    const y = canvas.y + ((step + 0.5) / 24) * canvas.height;
    await page.mouse.move(x, y);
    const text = (await readout.textContent()) ?? "";
    const match = /(-|−|\+)?\d+[.,]\d+\s*дБ/.exec(text);
    if (match === null) continue;
    samples.push(Number(match[0].replace(/\s*дБ/, "").replace("−", "-").replace(",", ".")));
  }
  expect(samples.length).toBeGreaterThanOrEqual(22);

  // Модуляция обязана иметь нулевое среднее ИМЕННО В ДЕЦИБЕЛАХ: единичное среднее
  // в линейных величинах смещает среднее по Йенсену, и полотно разошлось бы с таблицей.
  const mean = samples.reduce((sum, value) => sum + value, 0) / samples.length;
  expect(mean, `среднее полотна ${mean.toFixed(2)} против колонки ${column}`).toBeCloseTo(
    column,
    0,
  );
});

test("V6-S16: витрина снимается артефактом в каждом рабочем состоянии", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(PAGE);
  const shot = async (name: string): Promise<void> => {
    await page.screenshot({ path: resolve(EVIDENCE_DIR, `v6-${name}-1280.png`), fullPage: true });
  };

  // Сортировка по метке: группы распущены, колонка отдаёт полную дату.
  await page.locator(`${CATALOG} [data-cat-sort="label"]`).click();
  await shot("catalog-sorted");

  // Пустой результат поиска.
  await page.locator(`${CATALOG} [data-cat-search]`).fill("такого-нет");
  await shot("catalog-empty");
  await page.locator(`${CATALOG} [data-cat-clear]`).click();

  // Спектрограмма в режиме уровня, а не дельты.
  await page.locator('[data-spectrogram-mode="a"]').click();
  await page.mouse.move(640, 300);
  await shot("gram-level");
  await page.locator('[data-spectrogram-mode="delta"]').click();

  // Фокус-рамки на органах управления.
  await page.locator(`${CATALOG} [data-cat-search]`).focus();
  await shot("focus-search");
  await page.locator('[data-cat-sort="label"] .cat-sort').focus();
  await shot("focus-sort");

  // Стык под полотном крупным планом: туда ни разу не смотрели вблизи.
  const box = await page.locator("[data-spectrogram-canvas]").boundingBox();
  if (box !== null) {
    await page.screenshot({
      path: resolve(EVIDENCE_DIR, "v6-gram-seam-1280.png"),
      clip: { x: box.x - 80, y: box.y + box.height - 40, width: box.width + 80, height: 90 },
    });
  }
});

test.describe("V6-S19: полотно чёткое на экране с масштабированием", () => {
  test.use({ deviceScaleFactor: 2 });

  test("буфер холста считается в физических пикселях", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(PAGE);

    const canvas = await page.evaluate(() => {
      const node = document.querySelector("[data-spectrogram-canvas]");
      if (!(node instanceof HTMLCanvasElement)) return null;
      const box = node.getBoundingClientRect();
      return {
        bufferWidth: node.width,
        bufferHeight: node.height,
        cssWidth: box.width,
        cssHeight: box.height,
        ratio: devicePixelRatio,
      };
    });
    expect(canvas).not.toBeNull();
    if (canvas === null) return;

    // Буфер меньше физического размера — браузер растянет его интерполяцией, и полотно
    // поплывёт мылом на любом экране с масштабированием, отличным от 100%.
    expect(canvas.ratio).toBeGreaterThan(1);
    expect(
      canvas.bufferWidth,
      `буфер ${canvas.bufferWidth}x${canvas.bufferHeight} против css ${canvas.cssWidth}x${canvas.cssHeight} при dpr ${canvas.ratio}`,
    ).toBe(Math.round(canvas.cssWidth * canvas.ratio));
    expect(canvas.bufferHeight).toBe(Math.round(canvas.cssHeight * canvas.ratio));

    const box = await page.locator("[data-spectrogram]").boundingBox();
    if (box !== null) {
      await page.screenshot({
        path: resolve(EVIDENCE_DIR, "v6-gram-dpr2-1280.png"),
        clip: {
          x: Math.max(0, box.x - 40),
          y: Math.max(0, box.y - 40),
          width: box.width + 80,
          height: box.height + 80,
        },
      });
    }

    // Битмап не должен становиться flex min-content: иначе обёртка и ось
    // вырастают до физических пикселей, а CSS-высота полотна остаётся 104px —
    // под спектрограммой дыра, в которой висят «0 с / 1.2 с / 2.4 с».
    const layout = await page.evaluate(() => {
      const node = document.querySelector("[data-spectrogram-canvas]");
      const axis = document.querySelector(".app-v6 .gram-axis");
      const wrap = document.querySelector(".app-v6 .gram-canvas-wrap");
      if (
        !(node instanceof HTMLCanvasElement) ||
        !(axis instanceof HTMLElement) ||
        !(wrap instanceof HTMLElement)
      ) {
        return null;
      }
      node.width = 2000;
      node.height = 800;
      void wrap.offsetHeight;
      return {
        canvas: node.getBoundingClientRect().height,
        axis: axis.getBoundingClientRect().height,
        wrap: wrap.getBoundingClientRect().height,
      };
    });
    expect(layout).not.toBeNull();
    expect(layout?.canvas, "CSS-высота полотна").toBeCloseTo(104, 0);
    expect(
      Math.abs((layout?.axis ?? 0) - (layout?.canvas ?? 0)),
      `ось ${layout?.axis} против полотна ${layout?.canvas}`,
    ).toBeLessThanOrEqual(1);
    expect(
      Math.abs((layout?.wrap ?? 0) - (layout?.canvas ?? 0)),
      `обёртка ${layout?.wrap} против полотна ${layout?.canvas}`,
    ).toBeLessThanOrEqual(1);
  });
});
