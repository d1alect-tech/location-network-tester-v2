/** Точка монтирования uPlot-workbench (todo 41): изолирует создание
 * API-клиента и жизненный цикл графиков от маршрутизатора. */

import { LntApiClient } from "../../api/client";
import { createChartsWorkbench } from "./workbench";
import type { WorkbenchHandle } from "./workbench";

export function mountInspectWorkbench(host: HTMLElement): WorkbenchHandle {
  const client = new LntApiClient();
  const workbench = createChartsWorkbench({ client });
  host.append(workbench.root);
  return workbench;
}
