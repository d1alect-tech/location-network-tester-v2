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

import { test } from "@playwright/test";
import {
  LIVE_VIEWPORTS,
  SA_LIVE_TAB,
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
