/** V1 — «Классический воркбенч»: трёхпанельный docked-воркспейс как в Audition.
 *  Каталог слева 280px, спектр в центре на канве, инспектор справа 300px (§8 V1). */
import "./variantV1.css";
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
  h("div", "app-v1", { "data-showcase": "shell" }, [
    buildHeader(false),
    h("div", "navrow", {}, [buildTabbar("Инспекция")]),
    h("div", "app-body", {}, [
      h("div", "col-cat", {}, [buildCatalog()]),
      h("div", "col-center", {}, [buildSpectrumPanel(300), buildCaptureForm(), buildError()]),
      h("div", "col-inspect", {}, [buildMetrics()]),
    ]),
    buildStatusbar(),
  ]),
);
