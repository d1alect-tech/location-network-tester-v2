/** E2E задача 17 (план scope-sa-round4): продуктовая геометрия-спека
 * вкладки «Осциллограф» — 3 вьюпорта {1280×720, 1920×1080, 1280×625}.
 * Ассерты — перенос прототипной геометрия-машины (задача 9) на продукт
 * (:4101, installMockBackend): (a) docScroll == docClient (+1, паттерн
 * замороженного round2-v6.spec.ts:118-121 — документ И окно вида);
 * (b) per-zone box-intersection полосы liveStrip по карте зон манифеста
 * SCOPE_STRIP_ZONES + зоны в видимом окне вида; (c) цели ≥ 44×44;
 * (d) [data-readonly] → pointer-events:none; (e) высоты: полоса ≤ 150
 * (цель)/238 (аварийный потолок) в idle и running, экран-доминанта
 * (AC3: stage ≥ 60 % полезной высоты при 1280×625). Settle — наблюдаемые
 * сигналы (счётчик кадров растёт), ноль фиксированных пауз. Высоты
 * инкрементально пишутся в квитанцию задачи 17 (heights.json). */

import { expect, test } from "@playwright/test";
import {
  LIVE_VIEWPORTS,
  SCOPE_LIVE_TAB,
  recordLiveGeometryRow,
  runLiveGeometryGate,
} from "../../testkit/liveGeometry";
import { installMockBackend } from "../../testkit/mockBackend";

test.beforeEach(async ({ page }) => {
  installMockBackend(page);
});

for (const vp of LIVE_VIEWPORTS) {
  test(`геометрия вкладки «Осциллограф» @ ${vp.width}×${vp.height}`, async ({ page }) => {
    await runLiveGeometryGate(page, SCOPE_LIVE_TAB, vp, recordLiveGeometryRow);
  });
}

/** Задача r5-9 (W1/W3): r4-пропорции главного экрана — стекло заполняет
 * главную колонку (высота ≥ 400 px на 1280×720, воркспейс на всю ширину
 * окна вида — r4 v1: стекло 454 из 498 стейджа), полоса ≤ 140 px, и цензус
 * ридаут-ячеек: ни одна видимая клетка не обрезана (scrollWidth ≤ clientWidth,
 * паттерн round2-review S12). Инлайн Δt·ΔV — одна строка без обрезки. */

test("r5-9 W1/W3: экран r4-пропорций + ридауты без обрезки @1280×720", async ({ page }) => {
  await runLiveGeometryGate(
    page,
    SCOPE_LIVE_TAB,
    { width: 1280, height: 720 },
    recordLiveGeometryRow,
  );

  const audit = await page.evaluate(() => {
    const round = (n: number): number => Math.round(n * 10) / 10;
    const view = document.querySelector("#view-container");
    const workspace = document.querySelector(".lnt-scope-workspace");
    const glass = document.querySelector(".lnt-scope-viewport");
    const band = document.querySelector("[data-band]");
    if (
      !(view instanceof HTMLElement) ||
      !(workspace instanceof HTMLElement) ||
      !(glass instanceof HTMLElement) ||
      !(band instanceof HTMLElement)
    ) {
      throw new Error("нет вью/воркспейса/стекла/полосы");
    }
    const clipped: string[] = [];
    const cells = [
      ...document.querySelectorAll<HTMLElement>(
        "[data-band] .readout-grid dt, [data-band] .readout-grid dd, .lnt-scope-workspace .readout-grid dt, .lnt-scope-workspace .readout-grid dd, [data-band] .lnt-scope-cursor-inline",
      ),
    ];
    for (const cell of cells) {
      if (cell.getClientRects().length === 0) continue; /* скрытые не в счёт */
      if (cell.scrollWidth > cell.clientWidth + 1) {
        clipped.push(
          `${cell.className}: ${cell.scrollWidth}>${cell.clientWidth} «${cell.textContent}»`,
        );
      }
    }
    const inline = document.querySelector<HTMLElement>("[data-band] .lnt-scope-cursor-inline");
    const styles = getComputedStyle(view);
    const viewInner = round(
      view.clientWidth -
        Number.parseFloat(styles.paddingLeft) -
        Number.parseFloat(styles.paddingRight),
    );
    return {
      viewInner,
      workspaceW: round(workspace.getBoundingClientRect().width),
      glassBox: (() => {
        const r = glass.getBoundingClientRect();
        return { w: round(r.width), h: round(r.height) };
      })(),
      bandH: round(band.getBoundingClientRect().height),
      clipped,
      inlineText: inline?.textContent ?? "",
    };
  });

  // W1: стекло — крупный экран r4 (высота ≥ 400), воркспейс заполняет окно вида.
  expect(audit.glassBox.h, `стекло ${audit.glassBox.h}px < 400`).toBeGreaterThanOrEqual(400);
  expect(
    audit.workspaceW,
    `воркспейс ${audit.workspaceW}px не заполняет окно ${audit.viewInner}px`,
  ).toBeGreaterThanOrEqual(audit.viewInner - 1);
  // Полоса — константа r4-гейта (≤ 140).
  expect(audit.bandH, `полоса ${audit.bandH}px > 140`).toBeLessThanOrEqual(140);
  // W3: ни одна видимая ридаут-клетка не обрезана; инлайн — одна строка.
  expect(audit.clipped, `обрезанные клетки: ${audit.clipped.join("; ")}`).toEqual([]);
  expect(audit.inlineText).toContain("Δt");
  expect(audit.inlineText).toContain("ΔV");
});

/** Задача 21 (GATE A 2026-10-18): расширенное меню захвата — disclosure-
 * оверлей по r4-прецеденту. Открытие НЕ растит полосу (панель absolute,
 * открывается вверх), окно вида не переполняется, цели меню ≥ 44×44, меню
 * целиком в окне вида. Пункт меню пишет то же поле, что и полоса: staged-
 * маркер зажигается, слот чипа частоты НЕ врёт; Esc закрывает stateless. */
test("задача 21: меню захвата — overlay, полоса не растёт, staged-запись @1280×720", async ({
  page,
}) => {
  await runLiveGeometryGate(
    page,
    SCOPE_LIVE_TAB,
    { width: 1280, height: 720 },
    recordLiveGeometryRow,
  );

  const panel = page.locator(".lnt-live-capture-menu");
  await expect(panel).toBeHidden();
  const menuButton = page.locator('[data-action="capture"] .lnt-live-capture-btn');
  await expect(menuButton).toBeVisible();
  await menuButton.click();
  await expect(panel).toBeVisible();

  const audit = await page.evaluate(() => {
    const round = (n: number): number => Math.round(n * 10) / 10;
    const doc = document.documentElement;
    const band = document.querySelector("[data-band]");
    const panelNode = document.querySelector(".lnt-live-capture-menu");
    if (!(band instanceof HTMLElement) || !(panelNode instanceof HTMLElement)) {
      throw new Error("нет полосы/панели меню");
    }
    const small: string[] = [];
    for (const node of panelNode.querySelectorAll<HTMLElement>("button, input")) {
      if (node.getClientRects().length === 0) continue;
      const r = node.getBoundingClientRect();
      if (r.width < 43.5 || r.height < 43.5) {
        small.push(
          `${node.getAttribute("data-menu-value") ?? node.tagName}: ${r.width}×${r.height}`,
        );
      }
    }
    const box = panelNode.getBoundingClientRect();
    const button = document.querySelector('[data-action="capture"] button');
    const buttonBox = button instanceof HTMLElement ? button.getBoundingClientRect() : null;
    return {
      bandH: round(band.getBoundingClientRect().height),
      docScrollH: doc.scrollHeight,
      docClientH: doc.clientHeight,
      docScrollW: doc.scrollWidth,
      docClientW: doc.clientWidth,
      menuTop: round(box.top),
      menuLeft: round(box.left),
      menuRight: round(box.right),
      menuBottom: round(box.bottom),
      small,
      buttonH: buttonBox === null ? 0 : round(buttonBox.height),
    };
  });

  // Полоса-гейт держится при открытом меню: высота и отсутствие прокрутки.
  expect(audit.bandH, `полоса ${audit.bandH}px > 140 при открытом меню`).toBeLessThanOrEqual(140);
  expect(audit.docScrollH).toBeLessThanOrEqual(audit.docClientH + 1);
  expect(audit.docScrollW).toBeLessThanOrEqual(audit.docClientW + 1);
  // Меню целиком в окне вида, кнопка ≥ 44, цели меню ≥ 44×44.
  expect(audit.menuTop).toBeGreaterThanOrEqual(0);
  expect(audit.menuLeft).toBeGreaterThanOrEqual(0);
  expect(audit.menuRight).toBeLessThanOrEqual(1280);
  expect(audit.menuBottom).toBeLessThanOrEqual(720);
  expect(audit.buttonH).toBeGreaterThanOrEqual(44);
  expect(audit.small, `мелкие цели меню: ${audit.small.join("; ")}`).toEqual([]);

  // Пункт меню пишет то же поле, что и полоса: staged-маркер + честный слот.
  await page.locator('.lnt-live-capture-menu [data-menu-row="vdiv"] [data-menu-value="1"]').click();
  const mark = page.locator('[data-live-mark="vdiv"]');
  await expect(mark).toBeVisible();
  await expect(mark).toHaveText("→ 1 В/дел");
  await expect(page.locator("[data-slot='rate']")).toHaveText("8 МГц");

  // Esc закрывает stateless: маркер остаётся staged-целью, панель скрыта.
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(mark).toBeVisible();

  // Клик мимо закрывает без изменений: повторное открытие показывает цель.
  await menuButton.click();
  await expect(panel).toBeVisible();
  await expect(
    page.locator('.lnt-live-capture-menu [data-menu-row="vdiv"] button[aria-pressed="true"]'),
  ).toHaveAttribute("data-menu-value", "1");
});

/** Задача 16 (GATE A 2026-10-18): математ-трасса CH1−CH2 — тумблер в ИЗМЕР
 * линии 2 (манифест local math), третья серия существующего стека развёртки,
 * ярлык честности [data-wave-math]. Полоса не растёт (≤140, линия 2 не
 * переносится), staged-грамматика не затрагивается. */
test("задача 16: математ-трасса — тумблер ИЗМЕР, полоса не растёт, ярлык виден @1280×720", async ({
  page,
}) => {
  await runLiveGeometryGate(
    page,
    SCOPE_LIVE_TAB,
    { width: 1280, height: 720 },
    recordLiveGeometryRow,
  );

  const toggle = page.locator('#lnt-scope-math');
  await expect(toggle).toBeVisible();
  await expect(toggle.locator("button")).toHaveCount(2);
  const tag = page.locator("[data-wave-math]");
  await expect(tag).toBeHidden();

  await toggle.locator('[data-value="on"]').click();
  await expect(tag).toBeVisible();
  await expect(tag).toContainText("CH1−CH2");

  // Живой захват идёт (гейт выше нажал Run): кадры пишут размах ряда разности.
  await expect(tag).toContainText("размах", { timeout: 15000 });

  // Полоса держит бюджет с новым тумблером; staged-маркеры не зажглись.
  const bandH = await page.evaluate(() =>
    Math.round(document.querySelector("[data-band]")?.getBoundingClientRect().height ?? 999),
  );
  expect(bandH, `полоса ${bandH}px > 140`).toBeLessThanOrEqual(140);
  const stagedVisible = await page.locator("[data-live-mark]:not([hidden])").count();
  expect(stagedVisible).toBe(0);
});
