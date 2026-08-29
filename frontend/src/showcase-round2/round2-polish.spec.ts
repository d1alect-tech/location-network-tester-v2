import { expect, test } from "@playwright/test";

/** Полировка раунда 2 (ultrawork): сценарии S1–S4 из .scratch/ulw-notepad.md.
 *  S1 — дифференциация поверхностей (V1/V2); S2 — эллипсис в каталоге;
 *  S3 — легенда-свотчи и hover-ридаут графика; S4 — замена слота шрифтов (§3). */
const BASE = "http://127.0.0.1:4101/static/v2";
const DOCKED = ["showcase-v1.html", "showcase-v2.html"] as const;
const ALL = [
  "showcase-v1.html",
  "showcase-v2.html",
  "showcase-v3.html",
  "showcase-v4.html",
] as const;

test.describe("S1: панели различимы по поверхностям (docked-варианты)", () => {
  for (const pageName of DOCKED) {
    test(`${pageName}: header-полосы и колонки не сливаются`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(`${BASE}/${pageName}`);
      const tones = await page.evaluate(() => {
        const bg = (sel: string) => {
          const el = document.querySelector(sel);
          return el ? getComputedStyle(el).backgroundColor : "";
        };
        return {
          catalog: bg('[data-showcase="catalog"]'),
          catalogHead: bg('[data-showcase="catalog"] .panel-hd'),
          spectrum: bg('[data-showcase="spectrum"]'),
          spectrumHead: bg('[data-showcase="spectrum"] .panel-hd'),
          metrics: bg('[data-showcase="metrics"]'),
          frame: bg('[data-showcase="spectrum"] .frame'),
        };
      });
      // Заголовок панели отличается от её тела — панель читается как приборный блок.
      expect(tones.catalogHead).not.toBe(tones.catalog);
      expect(tones.spectrumHead).not.toBe(tones.spectrum);
      // Вьюпорт измерения темнее хрома панелей (сигнал отделён, §5.1).
      expect(tones.frame).not.toBe(tones.catalog);
      // Левая и правая колонки не совпадают с центром хотя бы тоном или границей.
      expect(tones.catalog === tones.spectrum && tones.metrics === tones.spectrum).toBe(false);
    });
  }
});

test.describe("S2: каталог — эллипсис вместо переносов", () => {
  for (const pageName of ALL) {
    test(`${pageName}: метка и тип в один ряд с троеточием`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(`${BASE}/${pageName}`);
      const cells = page.locator('[data-showcase="catalog"] td.cell-ellipsis');
      expect(await cells.count()).toBeGreaterThanOrEqual(10);
      const sample = cells.first();
      const style = await sample.evaluate((el) => {
        const cs = getComputedStyle(el);
        // Однорядность читается по базовым линиям текста, а не по высоте ячейки: высота
        // задана ТЗ §2.3 (28-32px), а обрезанный текст браузер вправе вернуть
        // несколькими фрагментами одной и той же строки.
        const range = document.createRange();
        range.selectNodeContents(el);
        const tops = new Set(
          Array.from(range.getClientRects()).map((rect) => Math.round(rect.top)),
        );
        return {
          textOverflow: cs.textOverflow,
          whiteSpace: cs.whiteSpace,
          height: el.getBoundingClientRect().height,
          lines: tops.size,
          title: el.getAttribute("title") ?? "",
        };
      });
      expect(style.textOverflow).toBe("ellipsis");
      expect(style.whiteSpace).toBe("nowrap");
      expect(style.lines).toBe(1);
      expect(style.height).toBeLessThanOrEqual(32);
      expect(style.title.length).toBeGreaterThan(0);
    });
  }
});

test.describe("S3: график — свотчи легенды и hover-ридаут", () => {
  for (const pageName of ALL) {
    test(`${pageName}: легенда с образцами линий, ридеут при наведении`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(`${BASE}/${pageName}`);
      const swatches = page.locator('[data-showcase="spectrum"] [data-series] .swatch');
      await expect(swatches).toHaveCount(2);
      const kinds = await swatches.evaluateAll((els) =>
        els.map((el) => el.getAttribute("data-swatch")),
      );
      expect(new Set(kinds).size).toBe(2); // сплошная и штриховая различимы без цвета
      const plot = page.locator('[data-showcase="spectrum"] .spectrum-plot').first();
      await plot.hover({ position: { x: 300, y: 120 } });
      const readout = page.locator('[data-showcase="spectrum"] [data-readout]');
      await expect(readout).toBeVisible();
      const text = (await readout.textContent()) ?? "";
      expect(text).toMatch(/\d/);
      expect(text).toMatch(/Гц/);
    });
  }
});

test.describe("S4: слот шрифтов заменён (§3)", () => {
  test("UI-шрифт с нативной кириллицей загружен и применён", async ({ page }) => {
    await page.goto(`${BASE}/showcase-v1.html`);
    await page.waitForTimeout(300);
    const fonts = await page.evaluate(async () => {
      await document.fonts.ready;
      return {
        body: getComputedStyle(document.body).fontFamily,
        golos: document.fonts.check('14px "Golos Text Variable"'),
        jbMono: document.fonts.check('12px "JetBrains Mono Variable"'),
      };
    });
    expect(fonts.body).toContain("Golos Text Variable");
    expect(fonts.golos).toBe(true);
    expect(fonts.jbMono).toBe(true);
  });
});
