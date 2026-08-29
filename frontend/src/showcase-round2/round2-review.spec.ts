import { expect, test } from "@playwright/test";

/** Ревью-гейт раунда 2 (Oracle): сценарии S5–S9 из .scratch/ulw-notepad.md.
 *  S5 — минимальный кегль ≥11px и данные 12px (§2.2/§2.5); S6 — строки каталога 28–32px (§2.3);
 *  S7 — текст на акценте ≥4.5:1 в покое и hover (§4/§6); S8 — disclosure закрыт по [hidden] (§1.5);
 *  S9 — V4 несёт левый рейл каталога как V1 (§8 V4). */
const BASE = "http://127.0.0.1:4101/static/v2";
const ALL = [
  "showcase-v1.html",
  "showcase-v2.html",
  "showcase-v3.html",
  "showcase-v4.html",
] as const;

/** Собирает все отрисованные носители текста мельче 11px, включая ::before/::after. */
async function tinyText(page: import("@playwright/test").Page): Promise<string[]> {
  return page.evaluate(() => {
    const bad: string[] = [];
    const name = (el: Element): string =>
      `${el.tagName.toLowerCase()}.${el.getAttribute("class") ?? ""}`;
    for (const el of Array.from(document.querySelectorAll("*"))) {
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      const ownText = Array.from(el.childNodes).some(
        (node) => node.nodeType === Node.TEXT_NODE && (node.textContent ?? "").trim().length > 0,
      );
      if (ownText && Number.parseFloat(cs.fontSize) < 11) {
        bad.push(`${name(el)} = ${cs.fontSize}`);
      }
      for (const pseudo of ["::before", "::after"]) {
        const ps = getComputedStyle(el, pseudo);
        const content = ps.content;
        if (content === "none" || content === "normal" || content === '""') continue;
        if (Number.parseFloat(ps.fontSize) < 11) {
          bad.push(`${name(el)}${pseudo} = ${ps.fontSize}`);
        }
      }
    }
    return bad;
  });
}

test.describe("S5: минимальный кегль (§2.5) и кегль данных (§2.2)", () => {
  for (const pageName of ALL) {
    test(`${pageName}: нет текста <11px, числовые ячейки 12px`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(`${BASE}/${pageName}`);
      expect(await tinyText(page), `мельчение <11px на ${pageName}`).toEqual([]);
      const numFonts = await page
        .locator('[data-showcase="catalog"] td.num')
        .evaluateAll((els) => els.map((el) => getComputedStyle(el).fontSize));
      expect(numFonts.length).toBeGreaterThanOrEqual(8);
      expect(new Set(numFonts)).toEqual(new Set(["12px"]));
    });
  }
});

test.describe("S6: строки каталога 28–32px (§2.3)", () => {
  for (const pageName of ALL) {
    test(`${pageName}: высота строки данных в диапазоне ТЗ`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(`${BASE}/${pageName}`);
      const heights = await page
        .locator('[data-showcase="catalog"] tr[data-row]')
        .evaluateAll((els) => els.map((el) => el.getBoundingClientRect().height));
      expect(heights.length).toBeGreaterThanOrEqual(8);
      for (const height of heights) {
        expect(height).toBeGreaterThanOrEqual(27.5);
        expect(height).toBeLessThanOrEqual(32.5);
      }
    });
  }
});

test.describe("S7: текст на акценте ≥4.5:1 (§4, §6)", () => {
  for (const pageName of ALL) {
    test(`${pageName}: основная кнопка контрастна в покое и при наведении`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(`${BASE}/${pageName}`);
      const button = page.locator('[data-showcase="capture-form"] .form-actions .btn');
      await expect(button).toBeVisible();
      const ratio = () =>
        button.evaluate((el) => {
          const lum = (color: string): number => {
            const parts = (color.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
            const channel = (raw: number): number => {
              const c = raw / 255;
              return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
            };
            const [r = 0, g = 0, b = 0] = parts.map(channel);
            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
          };
          const cs = getComputedStyle(el);
          const a = lum(cs.color);
          const b = lum(cs.backgroundColor);
          return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        });
      expect(await ratio()).toBeGreaterThanOrEqual(4.5);
      await button.hover();
      expect(await ratio()).toBeGreaterThanOrEqual(4.5);
    });
  }
});

test.describe("S8: disclosure «Серия и протокол» закрыт на загрузке (§1.5)", () => {
  for (const pageName of ALL) {
    test(`${pageName}: [hidden] скрывает тело, тумблер раскрывает`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(`${BASE}/${pageName}`);
      const body = page.locator('[data-showcase="capture-form"] .disc-body');
      const toggle = page.locator('[data-showcase="capture-form"] .disc-toggle');
      await expect(body).toBeHidden();
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await toggle.click();
      await expect(body).toBeVisible();
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      await toggle.click();
      await expect(body).toBeHidden();
    });
  }
});

test.describe("S9: V4 несёт левый рейл каталога как V1 (§8)", () => {
  test("showcase-v4.html: каталог — сайдбар 280px, а не карточка в сетке", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE}/showcase-v4.html`);
    const rail = page.locator(".app-v4 .app-body > .col-cat");
    const catalog = rail.locator('[data-showcase="catalog"]');
    await expect(catalog).toBeVisible();
    expect(await page.locator('.app-v4 .cards [data-showcase="catalog"]').count()).toBe(0);

    const railBox = await rail.boundingBox();
    const cardsBox = await page.locator(".app-v4 .cards").boundingBox();
    const catalogBox = await catalog.boundingBox();
    expect(railBox).not.toBeNull();
    expect(cardsBox).not.toBeNull();
    expect(catalogBox).not.toBeNull();
    if (!railBox || !cardsBox || !catalogBox) return;
    expect(Math.round(railBox.width)).toBe(280);
    expect(railBox.x + railBox.width).toBeLessThanOrEqual(cardsBox.x + 1);
    // Рейл во всю высоту рабочей области, как колонка V1, а не карточка по контенту.
    expect(catalogBox.height).toBeGreaterThanOrEqual(railBox.height - 1);
    expect(railBox.height).toBeGreaterThanOrEqual(600);
  });
});
