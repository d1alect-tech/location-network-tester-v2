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

import { test } from "@playwright/test";
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
