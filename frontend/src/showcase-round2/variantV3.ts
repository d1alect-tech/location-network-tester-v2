/** V3 — «Верхние вкладки»: навигация таб-баром в шапке, каталог слева 320px,
 *  анализ справа: спектр во всю ширину, ряд KPI, форма захвата в две колонки (§8 V3). */
import "./variantV3.css";
import { buildCaptureForm, buildError } from "./form";
import { buildCatalog, buildHeader, buildKpiRow, buildSpectrumPanel, h } from "./kit";
import { METERS, buildMetrics } from "./metrics";

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");

app.append(
  h("div", "app-v3", { "data-showcase": "shell" }, [
    buildHeader(true),
    h("div", "app-body", {}, [
      h("div", "col-cat", {}, [buildCatalog()]),
      h("div", "col-main", {}, [
        buildSpectrumPanel(280),
        h("div", "kpi-panel", {}, [buildKpiRow(METERS, "row")]),
        h("div", "bottom-row", {}, [
          buildCaptureForm(),
          h("div", "panel side-panel", {}, [
            h("div", "panel-hd", {}, [h("h2", "panel-title", {}, ["Состояние"])]),
            h("div", "panel-bd", {}, [buildError()]),
          ]),
        ]),
        buildMetrics(),
      ]),
    ]),
  ]),
);
