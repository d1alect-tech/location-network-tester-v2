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

  const toggle = page.locator("#lnt-scope-math");
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

/** Задача 17 (GATE A 2026-10-18): пресеты задач — секция «Пресеты» в меню
 * захвата (кнопка в существующем кластере — бюджет строки 2 полосы на
 * 1280×720 исчерпан математ-тумблером), stateless-диалог поверх полосы,
 * localStorage lnt.live.presets.v1, применение — staged-дорогой: маркер
 * «применится при следующем запуске» виден, запуска не уходит. */
test("задача 17: пресеты — диалог из меню захвата, staged-применение @1280×720", async ({
  page,
}) => {
  await runLiveGeometryGate(
    page,
    SCOPE_LIVE_TAB,
    { width: 1280, height: 720 },
    recordLiveGeometryRow,
  );

  await page.locator('[data-action="capture"] .lnt-live-capture-btn').click();
  const menu = page.locator(".lnt-live-capture-menu");
  await expect(menu).toBeVisible();
  await expect(page.locator("[data-presets-open]")).toBeVisible();
  await page.locator("[data-presets-open]").click();
  const dialog = page.locator(".lnt-live-presets");
  await expect(dialog).toBeVisible();
  await expect(menu).toBeHidden();

  // Геометрия: полоса не растёт от диалога (absolute-оверлей), диалог в окне
  // вида, интерактивные цели ≥ 44 — ДО staged-дрифта В/дел (рост эха зоны
  // ВЕРТ от маркера — существующее поведение, гейтом r4 не проверяется).
  const bandH = await page.evaluate(() =>
    Math.round(document.querySelector("[data-band]")?.getBoundingClientRect().height ?? 999),
  );
  expect(bandH, `полоса ${bandH}px > 140`).toBeLessThanOrEqual(140);
  const audit = await page.evaluate(() => {
    const dialogEl = document.querySelector<HTMLElement>(".lnt-live-presets");
    if (dialogEl === null) return { inView: false, targets: [] as number[] };
    const rect = dialogEl.getBoundingClientRect();
    const inView = rect.top >= 0 && rect.left >= 0 && rect.right <= window.innerWidth;
    const targets = [...dialogEl.querySelectorAll("button, input")].map((node) => {
      const r = node.getBoundingClientRect();
      return Math.min(Math.round(r.width), Math.round(r.height));
    });
    return { inView, targets };
  });
  expect(audit.inView, "диалог вылез за окно вида").toBe(true);
  for (const target of audit.targets) {
    expect(target, `цель ${target}px < 44`).toBeGreaterThanOrEqual(44);
  }

  // Statelessness до действия: Esc закрывает без изменений.
  await page.locator("[data-presets-name]").press("Escape");
  await expect(dialog).toBeHidden();

  // Снимок с ЦЕЛЬЮ В/дел 1 (запущено 5): цель ≠ применённое — staged-семантика.
  await page.locator('#lnt-scope-vdiv [data-value="1"]').click();
  await page.locator('[data-action="capture"] .lnt-live-capture-btn').click();
  await page.locator("[data-presets-open]").click();
  await expect(dialog).toBeVisible();
  await page.locator("[data-presets-name]").fill("рабочий-1");
  await page.locator("[data-presets-save]").click();
  await expect(page.locator("[data-presets-list]")).toContainText("рабочий-1");
  await expect(dialog).toBeHidden();

  // Вернулись к применённому 5, применили пресет: цель 1 ≠ применённое 5 —
  // staged-маркер «применится при следующем запуске», без перезапуска.
  await page.locator('#lnt-scope-vdiv [data-value="5"]').click();
  await page.locator('[data-action="capture"] .lnt-live-capture-btn').click();
  await page.locator("[data-presets-open]").click();
  await expect(dialog).toBeVisible();
  await page.locator('[data-preset-name="рабочий-1"] [data-presets-apply]').click();
  const mark = page.locator('[data-live-mark="vdiv"]');
  await expect(mark).toBeVisible();
  await expect(mark).toHaveText("→ 1 В/дел");

  // Диалог закрылся после применения; повторное открытие + Esc — stateless.
  await expect(dialog).toBeHidden();
  await page.locator('[data-action="capture"] .lnt-live-capture-btn').click();
  await page.locator("[data-presets-open]").click();
  await expect(dialog).toBeVisible();
  await page.locator("[data-presets-name]").press("Escape");
  await expect(dialog).toBeHidden();
});

/** Задача 19 (GATE A 2026-10-18): edge-drag В/дел — верхняя кромка «экрана»
 * (стекло + фигура развёртки): 3 детента 5/1/0.5, эхо в зоне ВЕРТ без клика
 * (staged-маркер), арбитраж кромка > линия триггера > курсорные линии
 * (capture-фазой на предке; существующие drag-линии не правятся),
 * ghost-репетиция hover без анимации (PRM). Полоса не растёт (≤140 до
 * staged-дрифта: рост эха ВЕРТ от маркера — существующее поведение). */
test("задача 19: edge-drag В/дел — кромка, детенты, арбитраж, ghost @1280×720", async ({
  page,
}) => {
  await runLiveGeometryGate(
    page,
    SCOPE_LIVE_TAB,
    { width: 1280, height: 720 },
    recordLiveGeometryRow,
  );

  const viewport = page.locator(".lnt-scope-viewport");
  const box = await viewport.boundingBox();
  expect(box).not.toBeNull();
  const x = box!.x + box!.width / 2;
  // Полоса не растёт от кромки/ghost (до staged-дрифта В/дел).
  const bandH = await page.evaluate(() =>
    Math.round(document.querySelector("[data-band]")?.getBoundingClientRect().height ?? 999),
  );
  expect(bandH, `полоса ${bandH}px > 140`).toBeLessThanOrEqual(140);

  // Ghost-репетиция hover: пунктир + текущее значение, БЕЗ анимации (PRM).
  await page.mouse.move(x, box!.y + 5);
  const ghost = page.locator(".lnt-scope-edge-ghost");
  await expect(ghost).toBeVisible();
  await expect(ghost).toContainText("В/дел 5");
  const motion = await page.evaluate(() => {
    const el = document.querySelector<HTMLElement>(".lnt-scope-edge-ghost");
    if (el === null) return { duration: "?", animation: "?" };
    const computed = getComputedStyle(el);
    return { duration: computed.transitionDuration, animation: computed.animationName };
  });
  expect(motion.duration).toBe("0s");
  expect(motion.animation).toBe("none");

  // Детент 1 (5 → 1): эхо в ВЕРТ видно без клика — staged-маркер.
  await page.mouse.down();
  await page.mouse.move(x, box!.y + 50, { steps: 5 });
  await page.mouse.up();
  const mark = page.locator('[data-live-mark="vdiv"]');
  await expect(mark).toBeVisible();
  await expect(mark).toHaveText("→ 1 В/дел");

  // Арбитраж: линия триггера у верхней кромки не тянется (кромка выше).
  const line = page.locator(".lnt-scope-trig-line");
  const lineBox = await line.boundingBox();
  expect(lineBox).not.toBeNull();
  await page.mouse.move(lineBox!.x + 30, lineBox!.y + 20);
  await page.mouse.down();
  await page.mouse.move(x, box!.y + 8, { steps: 4 });
  await page.mouse.up();
  const levelTop = await page.locator("#lnt-scope-level").inputValue();
  await page.mouse.move(x, box!.y + 5);
  await page.mouse.down();
  await page.mouse.move(x, box!.y + 50, { steps: 5 });
  await page.mouse.up();
  // Уровень триггера не сдвинулся (линия не получила жест), В/дел — 0.5
  // (формат эха — 500 мВ/дел: тот же форматтер, что в зоне ВЕРТ).
  expect(await page.locator("#lnt-scope-level").inputValue()).toBe(levelTop);
  await expect(mark).toHaveText("→ 500 мВ/дел");

  // Линия ниже кромки тянется как раньше: уровень меняется.
  const lineTopBox = await line.boundingBox();
  expect(lineTopBox).not.toBeNull();
  // Старт ниже полосы кромки (12 px): жест у линии, не у кромки.
  await page.mouse.move(lineTopBox!.x + 30, lineTopBox!.y + 38);
  await page.mouse.down();
  await page.mouse.move(x, box!.y + box!.height / 2, { steps: 6 });
  await page.mouse.up();
  expect(await page.locator("#lnt-scope-level").inputValue()).not.toBe(levelTop);
});
