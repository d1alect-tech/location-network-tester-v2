/** Точка монтирования uPlot-workbench (todo 41) и спектрограммы (todo 42):
 * изолирует создание API-клиента и жизненный цикл графиков от маршрутизатора. */

import { LntApiClient } from "../../api/client";
import { createSpectrogramPanel } from "./spectrogramPanel";
import type { SpectrogramPanelHandle } from "./spectrogramPanel";
import { createChartsWorkbench } from "./workbench";
import type { WorkbenchHandle } from "./workbench";

export function mountInspectWorkbench(host: HTMLElement): WorkbenchHandle {
  const client = new LntApiClient();
  const workbench = createChartsWorkbench({ client });
  host.append(workbench.root);
  return workbench;
}

// --- todo 42: аддитивный монтаж спектрограммы под uPlot-workbench ---
export function mountInspectSpectrogram(host: HTMLElement): SpectrogramPanelHandle {
  const client = new LntApiClient();
  const panel = createSpectrogramPanel({ client });
  host.append(panel.root);
  return panel;
}
