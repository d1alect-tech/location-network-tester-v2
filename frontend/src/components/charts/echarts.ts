/** Модульная регистрация ECharts (todo 42): ТОЛЬКО бенч-отобранные модули
 * (Heatmap, Canvas, Grid/DataZoom, Tooltip, VisualMap) попадают в продукт.
 * Полный barrel `echarts` в продуктовом коде запрещён — точка входа одна. */

import { HeatmapChart } from "echarts/charts";
import type { HeatmapSeriesOption } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import type {
  DataZoomComponentOption,
  GridComponentOption,
  TooltipComponentOption,
  VisualMapComponentOption,
} from "echarts/components";
import * as echarts from "echarts/core";
import type { ComposeOption } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  HeatmapChart,
  CanvasRenderer,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
]);

/** Строго типизированный набор опций только из зарегистрированных компонентов. */
export type SpectrogramChartOption = ComposeOption<
  | HeatmapSeriesOption
  | DataZoomComponentOption
  | GridComponentOption
  | TooltipComponentOption
  | VisualMapComponentOption
>;

export const initSpectrogramChart = echarts.init;
export type SpectrogramChart = ReturnType<typeof echarts.init>;
