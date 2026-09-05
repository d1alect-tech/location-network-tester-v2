/** R3-B «Верстак»: Spike-гибрид — график-центр, докируемые панели справа,
 *  тёплый графит, Golos Text + JetBrains Mono. Бриф #13, оси: док + Golos. */
import "../showcase-redesign/fonts/fonts.css";
import "./tokens.css";
import "./kit.css";
import "./variantB.css";
import {
  buildChannelBar,
  buildDeltaBadges,
  buildDockPanel,
  buildPeakTable,
  buildStatusBar,
  buildVerdicts,
  h,
} from "./kit";
import { buildSpectrumPanel } from "./spectrumPanel";

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");
document.body.classList.add("r3", "r3--b");

const dock = h("aside", "dock", { "aria-label": "Панели" }, [
  buildDockPanel("Дельта пары", [buildDeltaBadges("line")]),
  buildDockPanel("Пики спектра", [buildPeakTable()]),
  buildDockPanel("Маска", [buildVerdicts()]),
]);

app.append(
  h("div", "app", { "data-showcase": "shell" }, [
    buildChannelBar(),
    h("div", "body", {}, [
      h("div", "center", {}, [buildSpectrumPanel({ traceA: "#41cfe0", traceB: "#eaa63f" })]),
      dock,
    ]),
    buildStatusBar(),
  ]),
);
