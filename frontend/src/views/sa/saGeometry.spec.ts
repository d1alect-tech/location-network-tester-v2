/** E2E задача 17 (план scope-sa-round4): продуктовая геометрия-спека
 * вкладки «Спектроанализатор» — 3 вьюпорта {1280×720, 1920×1080,
 * 1280×625}. Зеркало scopeGeometry.spec.ts по карте зон SA-манифеста
 * (SA_STRIP_ZONES: span/rbw/run/traces/markers/peaks, набор ≠ scope):
 * (a) docScroll == docClient (+1, паттерн замороженного
 * round2-v6.spec.ts:118-121 — документ И окно вида); (b) per-zone
 * box-intersection полосы liveStrip + зоны в видимом окне вида;
 * (c) цели ≥ 44×44 (чекбоксы трасс — по label[for]); (d) [data-readonly]
 * → pointer-events:none; (e) высоты: полоса ≤ 150 (цель)/238 (аварийный
 * потолок) в idle и running, экран-доминанта (AC3: stage ≥ 60 % полезной
 * высоты при 1280×625). Settle — наблюдаемые сигналы (счётчик свипов
 * растёт), ноль фиксированных пауз. Высоты инкрементально пишутся в
 * квитанцию задачи 17 (heights.json). */

import { expect, test } from "@playwright/test";
import {
  LIVE_VIEWPORTS,
  SA_LIVE_TAB,
  openLiveTab,
  recordLiveGeometryRow,
  runLiveGeometryGate,
} from "../../testkit/liveGeometry";
import { installMockBackend } from "../../testkit/mockBackend";

test.beforeEach(async ({ page }) => {
  installMockBackend(page);
});

for (const vp of LIVE_VIEWPORTS) {
  test(`геометрия вкладки «Спектроанализатор» @ ${vp.width}×${vp.height}`, async ({ page }) => {
    await runLiveGeometryGate(page, SA_LIVE_TAB, vp, recordLiveGeometryRow);
  });
}

/** Задача r5-10 (W2/W4): r4-пропорции главной зоны SA — стекло спектра
 * (фигура) заполняет воркспейс на всю ширину окна вида (как стекло scope
 * после r5-9: воркспейс 1232, стекло колонки 920, высота ≥ 400 px на
 * 1280×720), полоса ≤ 140 px, и цензус листьев с текстом: ни одна видимая
 * клетка воркспейса/полосы не обрезана (scrollWidth ≤ clientWidth, паттерн
 * round2-review S12). Пустые состояния маркеров/пиков — инструкции
 * оператора — рендерятся полностью (W4: 359/398 px контента в клетке
 * 278 px). Цензус снимается в idle — тексты детерминированы, живые
 * значения свипов не участвуют. */

test("r5-10 W2/W4: главная зона r4-пропорций + пустые состояния без обрезки @1280×720", async ({
  page,
}) => {
  await openLiveTab(page, SA_LIVE_TAB, { width: 1280, height: 720 });

  const audit = await page.evaluate(() => {
    const round = (n: number): number => Math.round(n * 10) / 10;
    const view = document.querySelector("#view-container");
    const workspace = document.querySelector(".lnt-sa-workspace");
    const glass = document.querySelector(".lnt-sa-figure");
    const band = document.querySelector("[data-band]");
    if (
      !(view instanceof HTMLElement) ||
      !(workspace instanceof HTMLElement) ||
      !(glass instanceof HTMLElement) ||
      !(band instanceof HTMLElement)
    ) {
      throw new Error("нет вью/воркспейса/стекла/полосы");
    }
    /** Цензус: каждый видимый лист с собственным текстом не обрезан. */
    const clipped: string[] = [];
    for (const node of document.querySelectorAll(".lnt-sa-workspace *, [data-band] *")) {
      if (!(node instanceof HTMLElement)) continue;
      if (node.getClientRects().length === 0) continue; /* скрытые не в счёт */
      if (node.children.length > 0) continue; /* лист = без элементов-детей */
      const ownText = Array.from(node.childNodes)
        .filter((child) => child.nodeType === Node.TEXT_NODE)
        .map((child) => child.textContent ?? "")
        .join("")
        .trim();
      if (ownText === "") continue;
      if (node.scrollWidth > node.clientWidth + 1) {
        clipped.push(
          `${node.tagName}.${node.className}: ${node.scrollWidth}>${node.clientWidth} «${node.textContent?.slice(0, 50)}»`,
        );
      }
    }
    const emptyOf = (selector: string) => {
      const node = document.querySelector<HTMLElement>(selector);
      if (node === null) return null;
      return {
        text: node.textContent ?? "",
        scrollW: node.scrollWidth,
        clientW: node.clientWidth,
        whiteSpace: getComputedStyle(node).whiteSpace,
        textOverflow: getComputedStyle(node).textOverflow,
      };
    };
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
      markersEmpty: emptyOf("[data-sa-markers-empty]"),
      peaksEmpty: emptyOf("[data-sa-peaks-empty]"),
    };
  });

  // W2: воркспейс заполняет окно вида (как scope после r5-9), стекло
  // главной колонки — крупное (высота ≥ 400, r4-планка на 1280×720).
  expect(
    audit.workspaceW,
    `воркспейс ${audit.workspaceW}px не заполняет окно ${audit.viewInner}px`,
  ).toBeGreaterThanOrEqual(audit.viewInner - 1);
  expect(audit.glassBox.h, `стекло SA ${audit.glassBox.h}px < 400`).toBeGreaterThanOrEqual(400);
  expect(audit.glassBox.w, `стекло SA ${audit.glassBox.w}px — колонка уже рельса`).toBeGreaterThan(
    600,
  );
  // Полоса — константа r4-гейта (≤ 140).
  expect(audit.bandH, `полоса ${audit.bandH}px > 140`).toBeLessThanOrEqual(140);
  // W4: ни один видимый текстовый лист не обрезан.
  expect(audit.clipped, `обрезанные клетки: ${audit.clipped.join("; ")}`).toEqual([]);
  // W4: пустые состояния — полные инструкции оператора, переносом, без
  // эллипсиса (контент в клетке, не за её пределами).
  expect(audit.markersEmpty?.text).toBe(
    "Маркеры не поставлены: клик по спектру ставит маркер (до 4).",
  );
  expect(audit.peaksEmpty?.text).toBe(
    "Пики не искались: «Найти пики» отметит максимумы текущей трассы.",
  );
  for (const [name, cell] of [
    ["маркеры", audit.markersEmpty],
    ["пики", audit.peaksEmpty],
  ] as const) {
    expect(cell, `нет пустого состояния ${name}`).not.toBeNull();
    expect(
      cell?.scrollW,
      `${name}: контент ${cell?.scrollW}px > клетки ${cell?.clientW}px`,
    ).toBeLessThanOrEqual((cell?.clientW ?? 0) + 1);
    expect(cell?.whiteSpace, `${name}: white-space ${cell?.whiteSpace}`).not.toBe("nowrap");
    expect(cell?.textOverflow, `${name}: text-overflow ${cell?.textOverflow}`).not.toBe("ellipsis");
  }
});
