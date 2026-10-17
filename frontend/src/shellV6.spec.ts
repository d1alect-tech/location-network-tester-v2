import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { type MockLntBackend, installMockBackend } from "./testkit/mockBackend";

/** Контракт общей V6-оболочки (раскатка дизайна витрины на всё приложение):
 *  единые шапка (.hdr с таббаром .snav-item) и статус-бар (.statusbar) на ВСЕХ
 *  маршрутах; старой .app-header больше нет; инспект не дублирует шелл.
 *  Доказываем отрисованный DOM, а не логи. */

const BASE = "http://127.0.0.1:4101/static/v2/";

const TABS = 8; // Каталог, Захват, Осциллограф, Спектроанализатор, Инспекция, Эксперименты, Отчёты, Настройки

const ROUTES = ["catalog", "capture", "inspect", "experiments", "reports", "settings"] as const;

const TITLES: Record<(typeof ROUTES)[number], string> = {
  catalog: "Каталог",
  capture: "Захват",
  inspect: "Инспекция",
  experiments: "Эксперименты",
  reports: "Отчёты",
  settings: "Настройки",
};

function mockInspectApi(backend: MockLntBackend): void {
  backend.seedCatalog([
    {
      id: "capture-001",
      health: "ok",
      created_utc: "2026-08-02T10:00:00Z",
      source: "capture",
      session_type: "capture",
      profile: "bad",
      label: "стенд-А",
    },
  ]);
  backend.seedSessionDetail("capture-001", {
    name: "capture-001",
    manifest: {},
    analysis: null,
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  });
  backend.seedSpectrum("capture-001", {
    frequency_hz: [10, 100, 1000],
    psd_v2_per_hz: [1e-6, 1e-4, 1e-2],
    point_count: 3,
  });
}

async function noHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
}

test("S1: общая V6-шапка и статус-бар на всех маршрутах, старой шапки нет", async ({ page }) => {
  mockInspectApi(installMockBackend(page));
  for (const route of ROUTES) {
    await page.goto(`${BASE}#/${route}`);
    // Единая шапка витрины: бренд, таббар из 8 вкладок, статус устройства.
    const header = page.locator("header.hdr");
    await expect(header, `маршрут #/${route}: шапка .hdr`).toBeVisible();
    await expect(header.locator(".hdr-brand")).toHaveText("LNT");
    await expect(header.locator(".tabbar a.snav-item")).toHaveCount(TABS);
    // Supersession: пункт теперь «Иконки-ярлыки» — глиф .ico обязателен у каждого.
    await expect(header.locator(".tabbar a.snav-item svg.ico[aria-hidden='true']")).toHaveCount(
      TABS,
    );
    // Статус-бар внизу.
    await expect(page.locator("footer.statusbar"), `маршрут #/${route}: статус-бар`).toBeVisible();
    // Старой шапки больше нет нигде.
    await expect(page.locator(".app-header")).toHaveCount(0);
    // Активная вкладка помечена единым паттерном: is-active + aria-current=page.
    const active = header.locator(".tabbar a.snav-item[aria-current='page']");
    await expect(active).toHaveCount(1);
    await expect(active).toHaveAttribute("href", `#/${route}`);
    await expect(active).toHaveClass(/is-active/);
    await noHorizontalOverflow(page);
  }
});

test("S1b: убитый legacy-маршрут prepare редиректит на capture (A3)", async ({ page }) => {
  mockInspectApi(installMockBackend(page));
  await page.goto(`${BASE}#/prepare`);
  await expect(page).toHaveURL(/#\/capture/);
  const header = page.locator("header.hdr");
  await expect(header).toBeVisible();
  const active = header.locator(".tabbar a.snav-item[aria-current='page']");
  await expect(active).toHaveCount(1);
  await expect(active).toHaveAttribute("href", "#/capture");
  await expect(page.locator(".capture-view")).toBeVisible();
  await expect(page.locator(".error-panel")).toHaveCount(0);
  await noHorizontalOverflow(page);
});

test("S2: инспект под общей оболочкой — окно сравнения без дублирования шелла", async ({
  page,
}) => {
  mockInspectApi(installMockBackend(page));
  await page.goto(`${BASE}#/inspect`);
  // Окно сравнения на месте: полоса пары, каталог, сигнальное окно, лента анализа.
  await expect(page.locator(".pairbar")).toBeVisible();
  await expect(page.locator(".app-body .col-cat")).toBeVisible();
  await expect(page.locator("[data-showcase='spectrum']")).toBeVisible();
  await expect(page.locator(".analysis-band")).toBeVisible();
  // Шелл не дублируется внутри view-контейнера: ровно одна .hdr на странице.
  await expect(page.locator("header.hdr")).toHaveCount(1);
  await expect(page.locator("#view-container header.hdr")).toHaveCount(0);
  await expect(page.locator("#view-container footer.statusbar")).toHaveCount(0);
  // Таббар общий и рабочий: клик по «Каталог» уводит на #/catalog, шапка остаётся.
  await page.locator("header.hdr .tabbar a[href='#/catalog']").click();
  await expect(page).toHaveURL(/#\/catalog/);
  await expect(page.locator("header.hdr")).toBeVisible();
  await expect(page.locator(".app-header")).toHaveCount(0);
});

test("S2b: персона 375px — общая оболочка без горизонтальной прокрутки", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  mockInspectApi(installMockBackend(page));
  for (const route of ["catalog", "inspect", "settings"] as const) {
    await page.goto(`${BASE}#/${route}`);
    await expect(page.locator("header.hdr")).toBeVisible();
    await expect(page.locator(".error-panel")).toHaveCount(0);
    await noHorizontalOverflow(page);
  }
});

test("S3: пункт = глиф + ярлык; активный тонирован, font-weight не прыгает", async ({ page }) => {
  mockInspectApi(installMockBackend(page));
  await page.goto(`${BASE}#/catalog`);
  const header = page.locator("header.hdr");
  for (const route of ROUTES) {
    const item = header.locator(`#nav-${route}`);
    await expect(item.locator(".lbl"), `ярлык ${route}`).toHaveText(TITLES[route]);
    await expect(item, `имя пункта ${route}`).toHaveAttribute("aria-label", TITLES[route]);
  }
  const active = header.locator(".tabbar a.snav-item.is-active");
  await expect(active).toHaveCSS("background-color", "rgba(86, 129, 255, 0.16)");
  await expect(active).toHaveCSS("border-top-color", "rgba(86, 129, 255, 0.38)");
  await expect(active.locator(".ico")).toHaveCSS("color", "rgb(86, 129, 255)");
  const inactive = header.locator("#nav-capture");
  await expect(inactive.locator(".ico")).toHaveCSS("color", "rgb(122, 130, 140)");
  // Индикация тоном: полосы ::before у активного пункта шапки больше нет.
  await expect(active).toHaveCSS("background-image", "none");
  const weight = (locator: typeof active) =>
    locator.evaluate((n) => getComputedStyle(n).fontWeight);
  expect(await weight(active), "fw активного равен fw неактивного").toBe(await weight(inactive));
});

test("S4: смена вкладки — вход не повторяется, геометрия соседей не двинута", async ({ page }) => {
  mockInspectApi(installMockBackend(page));
  await page.goto(`${BASE}#/catalog`);
  // Вход играет ровно один раз на монтаже оболочки.
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .some((a) => a instanceof CSSAnimation && a.animationName === "lnt-nav-in"),
  );
  await page.waitForFunction(() => {
    const entrance = document
      .getAnimations()
      .find((a) => a instanceof CSSAnimation && a.animationName === "lnt-nav-in");
    return entrance === undefined || entrance.playState === "finished";
  });
  const rects = () =>
    [...document.querySelectorAll("header.hdr .tabbar a.snav-item")].map((node) => {
      const box = node.getBoundingClientRect();
      return [box.x, box.y, box.width, box.height];
    });
  const before = await page.evaluate(rects);

  await page.click("#nav-reports");
  await expect(page.locator("#nav-reports")).toHaveAttribute("aria-current", "page");

  const replay = await page.evaluate(
    () =>
      document
        .getAnimations()
        .filter(
          (a) =>
            a instanceof CSSAnimation &&
            a.animationName === "lnt-nav-in" &&
            a.playState === "running",
        ).length,
  );
  expect(replay, "вход не повторяется на смене вкладки").toBe(0);
  expect(await page.evaluate(rects), "геометрия пунктов не двинулась").toEqual(before);
});

test("S5: 390px — ярлык уходит, глиф и тач-таргет 44px остаются", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  mockInspectApi(installMockBackend(page));
  await page.goto(`${BASE}#/catalog`);
  await expect(page.locator("header.hdr .tabbar a.snav-item")).toHaveCount(TABS);
  await expect(page.locator("#nav-catalog .lbl")).toBeHidden();
  const box = await page.locator("#nav-catalog").boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
  await expect(page.locator("#nav-catalog")).toHaveAttribute("aria-label", TITLES.catalog);
  await noHorizontalOverflow(page);
});

test("S6: prefers-reduced-motion — вход гасится, тон живёт, движения нет", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  mockInspectApi(installMockBackend(page));
  await page.goto(`${BASE}#/catalog`);
  const active = page.locator("header.hdr .tabbar a.snav-item.is-active");
  await expect(active).toHaveCount(1);
  await expect(active).toHaveCSS("animation-name", "none");
  // Политика r5-7/r5-11 (emil: reduced = меньше/мягче, не ноль): цвет/opacity
  // живут, transform выпадает из списка свойств, длительность конечная —
  // старый пин «0s» (transition: none) репинен на машинные значения политики.
  await expect(active).toHaveCSS("transition-property", "background, border-color, color, opacity");
  await expect(active).not.toHaveCSS("transition-duration", "0s");
});

test("S7: worst-case длинный ярлык эллипсуется, хром не ломается", async ({ page }) => {
  mockInspectApi(installMockBackend(page));
  await page.goto(`${BASE}#/catalog`);
  const header = page.locator("header.hdr");
  await expect(header.locator(".tabbar a.snav-item")).toHaveCount(TABS);
  const heightBefore = (await header.boundingBox())?.height;

  await page.evaluate(() => {
    const lbl = document.querySelector("#nav-experiments .lbl") as HTMLElement;
    lbl.textContent = "Прослеживаемость измерений и калибровочные коэффициенты стенда";
  });
  const lbl = page.locator("#nav-experiments .lbl");
  await expect(lbl).toBeVisible();
  expect(await lbl.evaluate((n) => n.scrollWidth > n.clientWidth), "ярлык эллипсован").toBe(true);
  expect((await header.boundingBox())?.height, "высота шапки не изменилась").toBe(heightBefore);
  await noHorizontalOverflow(page);
});

test("S8: холодный диплинк — вход играет на реальном маршруте", async ({ page }) => {
  // Подписка на animationstart ДО кода приложения: событие не теряется.
  await page.addInitScript(() => {
    const log: { name: string; id: string }[] = [];
    (window as unknown as { __navAnimStarts: typeof log }).__navAnimStarts = log;
    document.addEventListener(
      "animationstart",
      (event) => {
        log.push({ name: event.animationName, id: (event.target as HTMLElement).id });
      },
      true,
    );
  });
  mockInspectApi(installMockBackend(page));
  await page.goto(`${BASE}#/reports`);
  await page.waitForFunction(
    () => (window as unknown as { __navAnimStarts?: { name: string }[] }).__navAnimStarts?.length,
  );
  const starts = await page.evaluate(
    () =>
      (window as unknown as { __navAnimStarts: { name: string; id: string }[] }).__navAnimStarts,
  );
  const entrance = starts.filter((item) => item.name === "lnt-nav-in");
  // Вход сыграл ровно один раз и на пункте реального маршрута, не дефолтного.
  expect(entrance).toEqual([{ name: "lnt-nav-in", id: "nav-reports" }]);
});

test("S9: клик во время входа — затухание доигрывает до конца, повтора нет", async ({ page }) => {
  await page.addInitScript(() => {
    const log = { starts: [] as string[], ends: [] as string[], cancels: [] as string[] };
    (window as unknown as { __navAnim: typeof log }).__navAnim = log;
    const push = (kind: "starts" | "ends" | "cancels") => (event: AnimationEvent) => {
      if (event.animationName === "lnt-nav-in") log[kind].push((event.target as HTMLElement).id);
    };
    document.addEventListener("animationstart", push("starts"), true);
    document.addEventListener("animationend", push("ends"), true);
    document.addEventListener("animationcancel", push("cancels"), true);
  });
  mockInspectApi(installMockBackend(page));
  await page.goto(`${BASE}#/catalog`);
  // Клик по вкладке в окне входа (180ms): затухание обязано доиграть.
  await page.click("#nav-reports", { noWaitAfter: true });
  await page.waitForFunction(() => {
    const log = (window as unknown as { __navAnim?: { ends: string[]; cancels: string[] } })
      .__navAnim;
    return log !== undefined && log.ends.length + log.cancels.length > 0;
  });
  const log = await page.evaluate(
    () =>
      (window as unknown as { __navAnim: { starts: string[]; ends: string[]; cancels: string[] } })
        .__navAnim,
  );
  expect(log.starts, "вход стартовал один раз на пункте монтажа").toEqual(["nav-catalog"]);
  expect(log.ends, "затухание доиграло до конца (без скачка)").toEqual(["nav-catalog"]);
  expect(log.cancels, "вход не оборван кликом").toEqual([]);
});
