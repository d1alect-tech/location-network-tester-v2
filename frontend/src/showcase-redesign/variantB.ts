import "./fonts/fonts.css";
import "./variantB.css";
import {
  CAPTURE_FORM,
  CAPTURE_MODES,
  CAPTURE_SOURCES,
  ERROR_STATE,
  JOB,
  METRICS,
  PEAKS,
  SESSIONS,
  type ShowcaseSession,
  formatHz,
} from "./data";
import { type SpectrumStyle, renderSpectrum } from "./spectrum";

const ru = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 7 });
const SPECTRUM_STYLE = {
  traceA: "#0F4C81",
  traceB: "#C84B31",
  grid: "#E9E8E1",
  axisText: "#5C5F66",
  lineWidth: 2,
  dash: [6, 4],
  axisFont: '11px "Source Serif 4 Variable", serif',
  height: 280,
} satisfies SpectrumStyle;

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
  attrs?: Record<string, string>,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  }
  return node;
}

function field(labelText: string, control: HTMLElement): HTMLElement {
  const label = el("label", "field-label", labelText);
  if (control.id) label.htmlFor = control.id;
  const wrap = el("div", "field");
  wrap.append(label, control);
  return wrap;
}

function fillSelect(
  select: HTMLSelectElement,
  items: readonly { id: string; title: string }[],
): void {
  for (const item of items) select.append(el("option", undefined, item.title, { value: item.id }));
}

function makeTable(
  captionText: string,
  headers: string[],
  rows: HTMLTableRowElement[],
): HTMLTableElement {
  const table = el("table", "booktabs");
  table.append(el("caption", "table-caption", captionText));
  const headRow = el("tr");
  for (const header of headers) headRow.append(el("th", undefined, header));
  const thead = el("thead");
  thead.append(headRow);
  const tbody = el("tbody");
  for (const row of rows) tbody.append(row);
  table.append(thead, tbody);
  return table;
}

function section(showcase: string, kicker: string, note: string, ...body: Node[]): HTMLElement {
  const root = el("section", "section", undefined, { "data-showcase": showcase });
  const head = el("header", "section-head");
  head.append(el("p", "kicker", kicker));
  const aside = el("aside", "sidenote", note);
  const content = el("div", "section-body");
  content.append(...body);
  root.append(head, aside, content);
  return root;
}

function catalogRow(session: ShowcaseSession): HTMLTableRowElement {
  const edge = session.storagePath !== undefined;
  const row = el("tr", "catalog-row", undefined, { "data-row": edge ? "edge" : session.id });
  const cells: [string, string][] = [
    ["", session.label],
    ["mono", session.id],
    ["", session.typeLabel],
    ["mono", session.date],
    [`health health-${session.health}`, `${session.glyph} ${session.healthLabel}`],
    ["path-cell", session.storagePath ?? ""],
  ];
  for (const [cls, text] of cells) row.append(el("td", cls || undefined, text));
  return row;
}

function catalogSection(): HTMLElement {
  return section(
    "catalog",
    "1. Каталог сессий",
    `В каталоге ${ru.format(SESSIONS.length)} записей. Состояние манифеста — в последнем столбце.`,
    makeTable(
      "Таблица 1. Каталог сессий измерения",
      ["Метка", "Каталог", "Тип", "Дата", "Состояние", "Путь"],
      SESSIONS.map(catalogRow),
    ),
  );
}

function spectrumSection(): { root: HTMLElement; host: HTMLElement } {
  const host = el("div", "spectrum-host");
  const plate = el("div", "figure-plate");
  plate.append(host);
  const figure = el("figure", "figure");
  figure.append(
    plate,
    el(
      "figcaption",
      "caption",
      `Рис. 1. Спектральная плотность мощности записи в полосе ${formatHz(METRICS.bandLowHz)}–${formatHz(METRICS.bandHighHz)}.`,
    ),
  );
  return {
    root: section(
      "spectrum",
      "2. Спектральный анализ",
      "Сплошная линия и кружок — сессия А; штрих и квадрат — сессия Б. Различие читается без цвета.",
      figure,
    ),
    host,
  };
}

function metricsSection(): HTMLElement {
  const grid = el("div", "metrics-grid");
  const items: [string, string][] = [
    ["Частота сети", `${ru.format(METRICS.lineFrequencyHz)} Гц`],
    ["Среднее иглы", `${ru.format(METRICS.needleMeanV)} В`],
    ["σ/μ", ru.format(METRICS.sigmaRatio)],
    ["P_async/P_sync", ru.format(METRICS.asyncSyncRatio)],
    ["Циклы", ru.format(METRICS.cyclesAnalyzed)],
    ["Частота дискретизации", formatHz(METRICS.sampleRateHz)],
    ["Длительность", `${ru.format(METRICS.durationS)} с`],
    ["Полоса анализа", `${formatHz(METRICS.bandLowHz)}–${formatHz(METRICS.bandHighHz)}`],
    ["Разрешение", `${ru.format(METRICS.resolutionHz)} Гц`],
  ];
  for (const [label, value] of items) {
    const item = el("div", "metric");
    item.append(el("p", "metric-label", label), el("p", "metric-readout", value));
    grid.append(item);
  }
  const peakRows = PEAKS.map((peak) => {
    const row = el("tr");
    row.append(
      el("td", "mono", formatHz(peak.frequencyHz)),
      el("td", "mono", ru.format(peak.levelDb)),
      el("td", "mono", ru.format(peak.prominenceDb)),
      el("td", "mono", ru.format(peak.q)),
    );
    return row;
  });
  return section(
    "metrics",
    "3. Метрики",
    `Проанализировано ${ru.format(METRICS.cyclesAnalyzed)} циклов сети при длительности ${ru.format(METRICS.durationS)} с.`,
    grid,
    makeTable(
      "Таблица 2. Пики спектральной плотности",
      ["Частота", "Уровень, дБ", "Выделенность, дБ", "Q"],
      peakRows,
    ),
  );
}

function textInput(id: string, value: string): HTMLInputElement {
  return el("input", "underline", undefined, { id, name: id, type: "text", value });
}

function captureSection(): HTMLElement {
  const form = el("form", "capture-form");
  form.addEventListener("submit", (event) => event.preventDefault());
  const mode = el("select", "underline", undefined, { id: "mode", name: "mode" });
  fillSelect(mode, CAPTURE_MODES);
  const source = el("select", "underline", undefined, { id: "source", name: "source" });
  fillSelect(source, CAPTURE_SOURCES);
  const range = el("select", "underline", undefined, { id: "range", name: "range" });
  for (const item of CAPTURE_FORM.ranges)
    range.append(el("option", undefined, item, { value: item }));
  const grid = el("div", "form-grid");
  grid.append(
    field("Режим", mode),
    field("Источник", source),
    field("Длительность, с", textInput("duration", CAPTURE_FORM.durationS)),
    field("Частота дискретизации, Гц", textInput("rate", CAPTURE_FORM.sampleRateHz)),
    field("Диапазон CH1", range),
    field("Метка", textInput("label", CAPTURE_FORM.label)),
  );
  const profile = el("select", "underline", undefined, { id: "profile", name: "profile" });
  for (const item of CAPTURE_FORM.profiles)
    profile.append(el("option", undefined, item, { value: item }));
  const extra = el("div", "form-grid");
  extra.append(
    field("Повторы", textInput("repeat", CAPTURE_FORM.repeat)),
    field("Интервал, с", textInput("interval", CAPTURE_FORM.intervalS)),
    field("Профиль", profile),
  );
  const details = el("details", "disclosure");
  details.append(el("summary", "disclosure-summary", "Серия и протокол"), extra);
  form.append(grid, details, el("button", "btn", "Записать", { type: "submit" }));
  const hint = CAPTURE_SOURCES.find((item) => item.id === "device")?.hint ?? "";
  return section("capture-form", "4. Форма захвата", hint, form);
}

function errorSection(): HTMLElement {
  const root = el("section", "error-banner", undefined, {
    "data-showcase": "error",
    role: "alert",
  });
  root.append(
    el("p", "kicker", "Сообщение об ошибке"),
    el("h2", "error-title", ERROR_STATE.title),
    el("p", "error-message", ERROR_STATE.message),
    el("button", "btn btn-quiet", ERROR_STATE.action, { type: "button" }),
  );
  return root;
}

function mount(): void {
  const app = document.getElementById("app");
  if (!app) return;
  const shell = el("div", "shell", undefined, { "data-showcase": "shell" });
  const header = el("header", "masthead");
  const running = el("div", "running-head");
  running.append(
    el("p", "running-title", "LNT · Отчёт об измерении"),
    el("p", "running-job", `${JOB.status} · ${JOB.stage} · ${JOB.series}`),
  );
  header.append(
    running,
    el("h1", "paper-title", "Спектральная плотность мощности записи"),
    el("p", "paper-deck", SESSIONS[0]?.date ?? ""),
  );
  const main = el("main", "main");
  const spectrum = spectrumSection();
  main.append(catalogSection(), spectrum.root, metricsSection(), captureSection(), errorSection());
  shell.append(header, main);
  app.append(shell);
  renderSpectrum(spectrum.host, SPECTRUM_STYLE, { a: "Сессия А", b: "Сессия Б" });
}

mount();
