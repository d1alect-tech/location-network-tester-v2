/** V2 — «Компактная студия»: скелет V1 с профессиональной высокой плотностью (§8 V2).
 *  Данные компактнее (12px, строки 28px, инспектор 260px), формы и заголовки — 14px. */
import "./variantV1.css";
import "./variantV2.css";
import { buildCaptureForm, buildError } from "./form";
import {
  buildCatalog,
  buildHeader,
  buildSpectrumPanel,
  buildStatusbar,
  buildTabbar,
  h,
} from "./kit";
import { buildMetrics } from "./metrics";

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");

app.append(
  h("div", "app-v1 app-v2 is-dense", { "data-showcase": "shell" }, [
    buildHeader(false),
    h("div", "navrow", {}, [buildTabbar("Инспекция")]),
    h("div", "app-body", {}, [
      h("div", "col-cat", {}, [buildCatalog()]),
      h("div", "col-center", {}, [buildSpectrumPanel(240), buildCaptureForm(), buildError()]),
      h("div", "col-inspect", {}, [buildMetrics()]),
    ]),
    buildStatusbar(),
  ]),
);
