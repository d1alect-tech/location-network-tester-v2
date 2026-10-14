import { expect, test } from "@playwright/test";
import type { CorpusRow } from "../../testkit/catalogFixture";
import { installMockBackend } from "../../testkit/mockBackend";

/** Строка 13 (план ui-refactor-3, F3-remedy): инвариант владельца на живом
 * рендере — «когда обрезаются какие-либо данные или не лезут друг на друга»
 * недопустимо. Геометрия (headless Chrome, реальная раскладка 336px):
 * полный текст метки в DOM, без text-overflow:ellipsis/nowrap/overflow:hidden,
 * scrollWidth внутри clientWidth, попарные прямоугольники линии метки не
 * пересекаются, мета-строка не залезает под кнопки А/Б. Плюс локализация
 * типов реального перечня (measurement/self_noise) и год в заголовке дня.
 * Даты сверяются строками из UTC-литералов — без Date/Intl (сдвиг зоны). */

const BASE = "http://127.0.0.1:4101/static/v2/#/inspect";

const LONG_LABEL =
  "Замер подъезда №2 — повторный прогон после замены кабеля на стенде-А (длинная метка), вторая часть для полного переноса";

function row(seed: Partial<CorpusRow> & { readonly dir: string }): CorpusRow {
  return {
    sessionId: null,
    health: "ok",
    createdUtc: null,
    sessionType: "measurement",
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

const WORLD: readonly CorpusRow[] = [
  row({
    dir: "sess-long",
    sessionId: "sess-long",
    createdUtc: "2026-10-05T15:10:00Z",
    metrics: true,
    spectrum: true,
    label: LONG_LABEL,
  }),
  row({
    dir: "sess-noise",
    sessionId: "sess-noise",
    createdUtc: "2026-10-05T15:09:00Z",
    sessionType: "self_noise",
    label: "Самошум, демпфирование пика №2",
  }),
  row({
    dir: "sess-quality",
    sessionId: "sess-quality",
    createdUtc: "2026-08-06T09:43:00Z",
    sessionType: "line_quality",
    label: "12:39, 06.08 бпф",
  }),
  row({
    dir: "sess-refused",
    sessionId: "sess-refused",
    createdUtc: "2026-08-06T08:12:00Z",
    ch2: true,
    label: "отказ-ch2",
  }),
];

test("полная метка видима без эллипсиса: DOM-текст равен полному, клиппинга нет", async ({
  page,
}) => {
  installMockBackend(page, { corpus: WORLD });
  await page.goto(BASE);
  const rail = page.locator(".col-cat > .panel");
  await expect(rail.locator('[data-session="sess-long"] [data-cat-label]')).toBeVisible();

  const label = rail.locator('[data-session="sess-long"] [data-cat-label]');
  await expect(label).toHaveText(LONG_LABEL);

  const style = await label.evaluate((node) => {
    const s = getComputedStyle(node);
    return {
      textOverflow: s.textOverflow,
      overflow: s.overflow,
      whiteSpace: s.whiteSpace,
      overflowWrap: s.overflowWrap,
      scrollWidth: node.scrollWidth,
      clientWidth: node.clientWidth,
    };
  });
  expect(style.textOverflow).not.toBe("ellipsis");
  expect(style.whiteSpace).not.toBe("nowrap");
  expect(style.overflowWrap).toMatch(/anywhere|break-word/);
  expect(style.scrollWidth).toBeLessThanOrEqual(style.clientWidth + 1);
});

test("рейл без горизонтального скролла; элементы строки не наезжают друг на друга", async ({
  page,
}) => {
  installMockBackend(page, { corpus: WORLD });
  await page.goto(BASE);
  const rail = page.locator(".col-cat > .panel");
  await expect(rail.locator("[data-session]").first()).toBeVisible();

  const panelBox = await rail.evaluate((node) => ({
    scrollWidth: node.scrollWidth,
    clientWidth: node.clientWidth,
  }));
  expect(panelBox.scrollWidth).toBeLessThanOrEqual(panelBox.clientWidth + 1);

  const overlaps = await rail.evaluate((node) => {
    const clashes: string[] = [];
    for (const tr of node.querySelectorAll<HTMLElement>("tr[data-session]")) {
      const line1 = tr.querySelector(".cat-line1");
      if (line1 === null) {
        clashes.push(`${tr.getAttribute("data-session")}: нет .cat-line1`);
        continue;
      }
      const parts = [
        ...line1.querySelectorAll<HTMLElement>("[data-assign], [data-cat-role], [data-cat-label]"),
      ];
      for (let i = 0; i < parts.length; i += 1) {
        for (let j = i + 1; j < parts.length; j += 1) {
          const left = parts[i];
          const right = parts[j];
          if (left === undefined || right === undefined) continue;
          const a = left.getBoundingClientRect();
          const b = right.getBoundingClientRect();
          const sepX = a.right <= b.left + 1 || b.right <= a.left + 1;
          const sepY = a.bottom <= b.top + 1 || b.bottom <= a.top + 1;
          if (!sepX && !sepY) {
            clashes.push(
              `${tr.getAttribute("data-session")}: пересечение ${left.tagName}/${right.tagName}`,
            );
          }
        }
      }
      const meta = tr.querySelector(".cat-meta");
      if (meta !== null) {
        const m = meta.getBoundingClientRect();
        for (const part of parts) {
          const p = part.getBoundingClientRect();
          const sepY = p.bottom <= m.top + 1 || m.bottom <= p.top + 1;
          if (!sepY) {
            clashes.push(`${tr.getAttribute("data-session")}: мета наезжает на линию метки`);
          }
        }
      }
    }
    return clashes;
  });
  expect(overlaps).toEqual([]);
});

test("мета-строка: локализованный тип, время, analyzed- и health-пилюли", async ({ page }) => {
  installMockBackend(page, { corpus: WORLD });
  await page.goto(BASE);
  const rail = page.locator(".col-cat > .panel");

  await expect(rail.locator('[data-session="sess-long"] .cat-meta-type')).toHaveText("Измерение");
  await expect(rail.locator('[data-session="sess-noise"] .cat-meta-type')).toHaveText("Самошум");
  await expect(rail.locator('[data-session="sess-quality"] .cat-meta-type')).toHaveText(
    "Качество сети",
  );
  await expect(rail.locator('[data-session="sess-long"] .cat-meta-time')).toHaveText("15:10");
  await expect(
    rail.locator('[data-session="sess-long"] .cat-meta [data-cat-analyzed="yes"]'),
  ).toBeVisible();
  await expect(
    rail.locator('[data-session="sess-long"] .cat-meta [data-cat-health="ok"]'),
  ).toBeVisible();
  await expect(
    rail.locator('[data-session="sess-refused"] .cat-meta [data-cat-analyzed="no"]'),
  ).toBeVisible();
});

test("заголовки дней с годом; сортировка по метке держит дату в мета-строке", async ({ page }) => {
  installMockBackend(page, { corpus: WORLD });
  await page.goto(BASE);
  const cat = page.locator(".col-cat");

  await expect(cat.locator("[data-cat-group]").first()).toContainText("5 октября 2026");

  await cat.locator("[data-cat-sort='label']").click();
  await expect(cat.locator("[data-cat-group]")).toHaveCount(0);
  await expect(cat.locator('[data-session="sess-long"] .cat-meta-time')).toContainText(
    "05.10.2026",
  );
  await expect(cat.locator('[data-session="sess-long"] .cat-meta-time')).toContainText("15:10");
});

test("высота строки растёт с длиной метки (длинная выше короткой)", async ({ page }) => {
  installMockBackend(page, { corpus: WORLD });
  await page.goto(BASE);
  const rail = page.locator(".col-cat > .panel");
  await expect(rail.locator("[data-session]").first()).toBeVisible();

  const heights = await rail.evaluate((node) => ({
    long: node.querySelector('tr[data-session="sess-long"]')?.getBoundingClientRect().height ?? 0,
    short: node.querySelector('tr[data-session="sess-noise"]')?.getBoundingClientRect().height ?? 0,
  }));
  expect(heights.long).toBeGreaterThan(heights.short);
});
