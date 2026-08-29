/** Витрина A: приборная панель — стойка, ЭЛТ-спектр, фосфорные индикаторы. */
import "./fonts/fonts.css";
import "./variantA.css";
import {
  CAPTURE_FORM,
  CAPTURE_MODES,
  CAPTURE_SOURCES,
  ERROR_STATE,
  JOB,
  METRICS,
  PEAKS,
  SESSIONS,
  formatHz,
} from "./data";
import { renderSpectrum } from "./spectrum";

function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  cls = "",
  attrs: Readonly<Record<string, string>> = {},
  kids: readonly (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  for (const [key, val] of Object.entries(attrs)) node.setAttribute(key, val);
  for (const kid of kids) node.append(kid);
  return node;
}

function field(label: string, control: HTMLElement): HTMLLabelElement {
  return h("label", "field", {}, [h("span", "kicker", {}, [label]), control]);
}

function sel(name: string, items: readonly { id: string; title: string }[]): HTMLSelectElement {
  const node = h("select", "ctl", { name, id: name });
  for (const item of items) node.append(h("option", "", { value: item.id }, [item.title]));
  return node;
}

function inp(name: string, value: string, type = "text"): HTMLInputElement {
  return h("input", "ctl", { name, id: name, type, value });
}

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");

const strip = h("header", "strip", {}, [
  h("div", "strip-dev", {}, [
    h("span", "led led-run", { "aria-hidden": "true" }),
    h("span", "kicker", {}, ["Устройство"]),
    h("strong", "strip-name", {}, ["LNT · Hantek 6022BE"]),
  ]),
  h("p", "strip-job", {}, [`${JOB.status} — ${JOB.stage} · ${JOB.series}`]),
  h("nav", "ch-nav", { "aria-label": "Каналы" }, [
    h("button", "ch-btn is-on", { type: "button" }, ["КАНАЛ A"]),
    h("button", "ch-btn ch-b", { type: "button" }, ["ОПОРНЫЙ СИГНАЛ"]),
  ]),
]);

const tbody = h("tbody");
SESSIONS.forEach((session, index) => {
  const edge = Boolean(session.storagePath);
  const row = h(
    "tr",
    `row health-${session.health} zebra-${index % 2}${index === 0 ? " is-sel" : ""}`,
    { "data-row": edge ? "edge" : session.id },
  );
  row.append(
    h("td", "", {}, [
      h("span", `glyph glyph-${session.health}`, {}, [`${session.glyph} ${session.healthLabel}`]),
    ]),
    h("td", "cell-label", {}, [session.label]),
    h("td", "", {}, [session.typeLabel]),
    h("td", "num", {}, [session.date]),
  );
  const sub = h("tr", `row-sub zebra-${index % 2}`);
  sub.append(h("td", "cell-path", { colspan: "4" }, [session.storagePath ?? session.id]));
  tbody.append(row, sub);
});

const catalog = h("section", "bay catalog", { "data-showcase": "catalog" }, [
  h("h2", "kicker", {}, ["Каталог сессий"]),
  h("div", "table-wrap", {}, [
    h("table", "cat-table", {}, [
      h("thead", "", {}, [
        h("tr", "", {}, [
          h("th", "", {}, ["Состояние"]),
          h("th", "", {}, ["Метка"]),
          h("th", "", {}, ["Тип"]),
          h("th", "", {}, ["Дата"]),
        ]),
      ]),
      tbody,
    ]),
  ]),
]);

const plotHost = h("div", "crt-glass");
const spectrum = h("section", "bay crt", { "data-showcase": "spectrum" }, [
  h("h2", "kicker", {}, ["Спектр мощности"]),
  h("div", "crt-bezel", {}, [plotHost]),
]);

const meters = [
  ["Частота сети", `${METRICS.lineFrequencyHz.toFixed(4)} Гц`],
  ["μ иглы", `${METRICS.needleMeanV.toFixed(4)} В`],
  ["σ/μ", METRICS.sigmaRatio.toFixed(3)],
  ["P_async/P_sync", METRICS.asyncSyncRatio.toFixed(2)],
  ["Циклов", String(METRICS.cyclesAnalyzed)],
  ["Частота дискретизации", formatHz(METRICS.sampleRateHz)],
  ["Длительность", `${METRICS.durationS} с`],
  ["Полоса", `${formatHz(METRICS.bandLowHz)} – ${formatHz(METRICS.bandHighHz)}`],
  ["Разрешение", `${METRICS.resolutionHz} Гц`],
] as const;

const peakBody = h("tbody");
for (const peak of PEAKS) {
  peakBody.append(
    h("tr", "", {}, [
      h("td", "num", {}, [formatHz(peak.frequencyHz)]),
      h("td", "num", {}, [`${peak.levelDb.toFixed(2)} дБ`]),
      h("td", "num", {}, [`${peak.prominenceDb.toFixed(2)} дБ`]),
      h("td", "num", {}, [peak.q.toFixed(2)]),
    ]),
  );
}

const metrics = h("section", "bay meters", { "data-showcase": "metrics" }, [
  h("h2", "kicker", {}, ["Показания"]),
  h(
    "div",
    "meter-grid",
    {},
    meters.map(([label, value]) =>
      h("article", "meter", {}, [
        h("span", "kicker", {}, [label]),
        h("strong", "meter-val", {}, [value]),
      ]),
    ),
  ),
  h("h3", "kicker peak-kicker", {}, ["Пики спектра"]),
  h("table", "peak-table", {}, [
    h("thead", "", {}, [
      h("tr", "", {}, [
        h("th", "", {}, ["f0"]),
        h("th", "", {}, ["Уровень"]),
        h("th", "", {}, ["Выделенность"]),
        h("th", "", {}, ["Q"]),
      ]),
    ]),
    peakBody,
  ]),
]);

const rangeSel = h("select", "ctl", { name: "range", id: "range" });
for (const range of CAPTURE_FORM.ranges)
  rangeSel.append(h("option", "", { value: range }, [range]));
const profileSel = h("select", "ctl", { name: "profile", id: "profile" });
for (const profile of CAPTURE_FORM.profiles) {
  profileSel.append(h("option", "", { value: profile }, [profile]));
}

const discBtn = h(
  "button",
  "disc-btn",
  { type: "button", "aria-expanded": "false", "aria-controls": "series-bay" },
  ["Серия и протокол"],
);
const discBody = h("div", "disc-body", { id: "series-bay", hidden: "" }, [
  field("Повторов, шт.", inp("repeat", CAPTURE_FORM.repeat, "number")),
  field("Интервал стартов, с", inp("interval", CAPTURE_FORM.intervalS, "number")),
  field("Профиль симуляции", profileSel),
]);
discBtn.addEventListener("click", () => {
  const open = discBtn.getAttribute("aria-expanded") === "true";
  discBtn.setAttribute("aria-expanded", String(!open));
  discBody.hidden = open;
});

const form = h("form", "bay bay-form", { "data-showcase": "capture-form" }, [
  h("h2", "kicker", {}, ["Захват"]),
  field(
    "Режим измерения",
    sel(
      "mode",
      CAPTURE_MODES.map((mode) => ({ id: mode.id, title: `${mode.title} · ${mode.channels}` })),
    ),
  ),
  field("Источник записи", sel("source", CAPTURE_SOURCES)),
  field("Длительность, с", inp("duration", CAPTURE_FORM.durationS, "number")),
  field("Частота дискретизации, Гц", inp("rate", CAPTURE_FORM.sampleRateHz, "number")),
  field("Диапазон CH1", rangeSel),
  field("Метка", inp("label", CAPTURE_FORM.label)),
  h("div", "disc", {}, [discBtn, discBody]),
  h("button", "btn-go", { type: "submit" }, ["Запустить запись"]),
]);
form.addEventListener("submit", (event) => event.preventDefault());

const error = h("aside", "banner", { "data-showcase": "error", role: "alert" }, [
  h("h2", "banner-title", {}, [ERROR_STATE.title]),
  h("p", "banner-msg", {}, [ERROR_STATE.message]),
  h("button", "btn-go btn-ghost", { type: "button" }, [ERROR_STATE.action]),
]);

app.append(
  h("div", "rack", { "data-showcase": "shell" }, [
    strip,
    h("main", "rack-body", {}, [
      catalog,
      h("div", "workspace", {}, [spectrum, metrics]),
      h("div", "control-col", {}, [form, error]),
    ]),
  ]),
);

renderSpectrum(
  plotHost,
  {
    traceA: "#00FFA3",
    traceB: "#FF5500",
    grid: "rgba(139,148,158,0.25)",
    axisText: "#8B949E",
    lineWidth: 1.4,
    dash: [6, 4],
    axisFont: '500 10px "JetBrains Mono Variable", monospace',
    height: 280,
  },
  { a: "● Сессия А", b: "■ Сессия Б" },
);
