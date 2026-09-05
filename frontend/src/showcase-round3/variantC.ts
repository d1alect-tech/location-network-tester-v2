/** R3-C «Пара»: сигнатура-максимум — паирбар A/B/Δ как герой экрана,
 *  холодный графит, Plex Sans + JetBrains Mono. Бриф #13: пара первокласснее трейса. */
import "../showcase-redesign/fonts/fonts.css";
import "./tokens.css";
import "./kit.css";
import "./variantC.css";
import {
  buildChannelBar,
  buildDeltaBadges,
  buildPairChips,
  buildPeakTable,
  buildStatusBar,
  buildVerdicts,
  h,
} from "./kit";
import { buildSpectrumPanel } from "./spectrumPanel";

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");
document.body.classList.add("r3", "r3--c");

const hero = h("div", "hero", { "data-r3": "hero" }, [
  buildPairChips(),
  buildDeltaBadges("hero"),
  h("span", "bar-spacer", {}),
  buildVerdicts(),
]);

app.append(
  h("div", "app", { "data-showcase": "shell" }, [
    hero,
    buildChannelBar(false),
    h("div", "body", {}, [
      buildSpectrumPanel({ traceA: "#3ec9e6", traceB: "#e6a13c" }),
      buildPeakTable(),
    ]),
    buildStatusBar(),
  ]),
);
