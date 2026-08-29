/** V4 — «Карточный дашборд»: слева рейл каталога как в V1, центр — сетка карточек
 *  (r8, hairline-рамки, без теней), отступы 16px, больше воздуха (§8 V4). */
import "./variantV4.css";
import { buildCaptureForm, buildError } from "./form";
import {
  buildCatalog,
  buildHeader,
  buildKpiRow,
  buildSpectrumPanel,
  buildStatusbar,
  buildTabbar,
  h,
} from "./kit";
import { METERS, buildMetrics } from "./metrics";

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");

const kpiCard = h("section", "panel span2", {}, [
  h("div", "panel-hd", {}, [h("h2", "panel-title", {}, ["Показания"])]),
  h("div", "panel-bd", {}, [buildKpiRow(METERS, "tiles")]),
]);
const spectrum = buildSpectrumPanel(300);
spectrum.classList.add("span2");
const capture = buildCaptureForm();
const metrics = buildMetrics();

app.append(
  h("div", "app-v4", { "data-showcase": "shell" }, [
    buildHeader(false),
    h("div", "navrow", {}, [buildTabbar("Инспекция")]),
    h("div", "app-body", {}, [
      h("div", "col-cat", {}, [buildCatalog()]),
      h("div", "col-main", {}, [
        h("div", "cards", {}, [
          kpiCard,
          spectrum,
          metrics,
          h("div", "col-stack", {}, [capture, buildError()]),
        ]),
      ]),
    ]),
    buildStatusbar(),
  ]),
);
