/** V6 — следующая ступень после V5: единицей работы становится ПАРА сессий.
 *  Протокол продукта сравнивает дельты, а не абсолюты, поэтому интерфейс называет
 *  обе трассы графика, показывает разницу между ними числом и уводит запись в
 *  докированную командную полосу — освободившаяся высота уходит графику. */
import "./variantV6.css";
import { ERROR_STATE, JOB, SESSIONS } from "../showcase-redesign/data";
import { buildCatalogV6 } from "./catalogV6";
import { buildCommandbar } from "./commandbar";
import { buildSpectrumPanel, buildTabbar, h } from "./kit";
import { METERS } from "./metrics";
import { buildPairbar } from "./pairbar";
import { mountPeakMarkers } from "./peakMarkers";
import { buildPeaksCompare } from "./peaksCompare";
import { buildSpectrogramV6 } from "./spectrogramV6";

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");

const SESSION_ROOT = "C:\\lnt-sessions";
const base = SESSIONS[0];
const compare = SESSIONS[6];
if (base === undefined || compare === undefined) throw new Error("нет пары сессий");

function buildStationHeader(): HTMLElement {
  return h("header", "hdr", {}, [
    h("span", "hdr-brand", {}, ["LNT"]),
    buildTabbar("Инспекция"),
    h("span", "hdr-status", {}, [
      h("span", "dot", { "aria-hidden": "true" }),
      "Hantek 6022BE · готов",
    ]),
  ]);
}

/** Приборный ритм: микро-лейбл 11px uppercase над крупным табличным значением. */
function buildReadout(): HTMLElement {
  const grid = h("div", "readout-grid");
  // Широкие значения идут последними: иначе полнострочная ячейка рвёт сетку и добавляет ряд.
  const ordered = [...METERS].sort(
    (left, right) => Number(left.value.length > 11) - Number(right.value.length > 11),
  );
  for (const meter of ordered) {
    const value = h("span", "readout-value", {}, [meter.value]);
    if (meter.unit) value.append(h("span", "t-unit", {}, [meter.unit]));
    // Длинные значения («3 000–45 000 Гц») берут всю ширину, а не обрезаются (§9.2).
    const wide = meter.value.length > 11 ? " is-wide" : "";
    grid.append(
      h("div", `readout-cell${wide}`, {}, [h("span", "readout-label", {}, [meter.label]), value]),
    );
  }
  return h("section", "panel readout", {}, [
    h("div", "panel-hd", {}, [h("h2", "panel-title", {}, ["Показания базы"])]),
    h("div", "panel-bd", {}, [grid]),
  ]);
}

function buildStationStatusbar(): HTMLElement {
  return h("footer", "statusbar", {}, [
    h("span", "statusbar-item", {}, [
      h("span", "dot", { "aria-hidden": "true" }),
      `${JOB.status} — ${JOB.stage} · ${JOB.series}`,
    ]),
    h("button", "btn-quiet", { type: "button" }, ["Отмена серии"]),
    h("span", "statusbar-spacer", {}),
    h("span", "statusbar-item num", {}, [`Корень: ${SESSION_ROOT}`]),
    h("button", "btn-quiet", { type: "button" }, ["Открыть корень"]),
  ]);
}

function buildInlineError(): HTMLElement {
  return h("aside", "banner banner-inline", { "data-showcase": "error", role: "alert" }, [
    h("span", "banner-glyph", { "aria-hidden": "true" }, ["✕"]),
    h("p", "banner-msg", {}, [ERROR_STATE.message]),
    h("button", "btn-quiet", { type: "button" }, [ERROR_STATE.action]),
  ]);
}

const peaksPanel = h("section", "panel", { "data-showcase": "metrics" }, [
  h("div", "panel-hd", {}, [h("h2", "panel-title", {}, ["Пики спектра · дельта к базе"])]),
  h("div", "panel-bd is-bare", {}, [buildPeaksCompare()]),
]);
const peakRows = Array.from(peaksPanel.querySelectorAll<HTMLElement>("[data-peak-row]"));

let redrawMarkers: (() => void) | undefined;
// Спектрограмма берёт высоту у самого спектра: сигнальная зона остаётся прежней,
// но вместо одной картины даёт две, стоящие на одной шкале частот.
const gram = buildSpectrogramV6();
const spectrum = buildSpectrumPanel(264, {
  labels: { a: base.label, b: compare.label },
  // Заголовок оси X ушёл в шапку панели: под графиком оставалась мёртвая тёмная
  // полоса с одинокой подписью «Частота, Гц», читавшаяся пустым местом.
  title: "Спектр мощности · Гц",
  xLabel: "",
  onDraw: () => {
    redrawMarkers?.();
  },
  onPlot: (plot) => {
    redrawMarkers = mountPeakMarkers(plot, peakRows);
    // Грам захватывает домен шкалы спектра: оба вида говорят на одной шкале.
    gram.attach(plot);
  },
});
spectrum.querySelector(".panel-bd")?.append(gram.host);

// Сигнальное окно одно, вида два: спектр и спектрограмма переключаются, а не
// стоят стопкой — стопка читалась пользователем как артефакт.
const viewToggle = h("div", "view-toggle", { role: "group", "aria-label": "Вид сигнального окна" });
const viewButtons = new Map<"spectrum" | "gram", HTMLElement>();
for (const [key, title] of [
  ["spectrum", "Спектр"],
  ["gram", "Спектрограмма"],
] as const) {
  const button = h(
    "button",
    "btn-quiet view-toggle-btn",
    { type: "button", "data-spectrum-view": key, "aria-pressed": String(key === "spectrum") },
    [title],
  );
  button.addEventListener("click", () => {
    spectrum.classList.toggle("is-gram", key === "gram");
    for (const [name, node] of viewButtons) node.setAttribute("aria-pressed", String(name === key));
  });
  viewButtons.set(key, button);
  viewToggle.append(button);
}
// Органы управления грамом живут в шапке панели: отдельная полоса съела бы высоту.
spectrum.querySelector(".panel-hd")?.append(viewToggle, gram.bar);

app.append(
  h("div", "app-v6", { "data-showcase": "shell" }, [
    buildStationHeader(),
    buildPairbar(base, compare),
    h("div", "app-body", {}, [
      h("div", "col-cat", {}, [buildCatalogV6({ base, compare })]),
      h("div", "col-main", {}, [
        spectrum,
        h("div", "analysis-band", {}, [buildReadout(), peaksPanel]),
      ]),
    ]),
    buildCommandbar(),
    buildInlineError(),
    buildStationStatusbar(),
  ]),
);

// Первая отрисовка возможна только когда полотно уже в DOM и имеет высоту.
gram.redraw();
