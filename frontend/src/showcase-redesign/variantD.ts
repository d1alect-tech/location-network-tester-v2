import "./fonts/fonts.css";
import "./variantD.css";
import {
  CAPTURE_FORM,
  CAPTURE_MODES,
  CAPTURE_SOURCES,
  ERROR_STATE,
  JOB,
  METRICS,
  SESSIONS,
} from "./data";
import { renderSpectrum } from "./spectrum";

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function field(label: string, control: HTMLElement): HTMLLabelElement {
  const wrap = el("label", "d-field");
  wrap.append(el("span", "d-field-label", label), control);
  return wrap;
}

function fillSelect(
  node: HTMLSelectElement,
  items: readonly string[] | readonly { readonly id: string; readonly title: string }[],
): void {
  for (const item of items) {
    const opt = document.createElement("option");
    if (typeof item === "string") {
      opt.value = item;
      opt.textContent = item;
    } else {
      opt.value = item.id;
      opt.textContent = item.title;
    }
    node.append(opt);
  }
}

function namedSelect(
  name: string,
  items: readonly string[] | readonly { readonly id: string; readonly title: string }[],
): HTMLSelectElement {
  const node = el("select", "d-input");
  node.name = name;
  fillSelect(node, items);
  return node;
}

function namedInput(name: string, value: string): HTMLInputElement {
  const node = el("input", "d-input");
  node.name = name;
  node.value = value;
  return node;
}

function kpi(label: string, value: string, unit: string): HTMLElement {
  const card = el("article", "d-kpi");
  card.append(el("p", "d-kpi-label", label), el("p", "d-kpi-value", value));
  if (unit) card.append(el("p", "d-kpi-unit", unit));
  return card;
}

function mount(): void {
  const app = document.getElementById("app");
  if (!app) return;

  const brand = el("div", "d-brand");
  brand.append(el("span", "d-brand-mark", "LNT"), el("span", "d-brand-sub", "Сети"));

  const nav = el("nav", "d-nav");
  nav.setAttribute("aria-label", "Разделы");
  const navItems = [
    ["Подготовка", ""],
    ["Захват", ""],
    ["Инспекция", "is-active"],
    ["Эксперименты", ""],
    ["Отчёты", ""],
    ["Настройки", ""],
  ] as const;
  for (const [label, extra] of navItems) {
    const item = el("button", extra ? `d-nav-item ${extra}` : "d-nav-item", label);
    item.type = "button";
    nav.append(item);
  }

  const aside = el("aside", "d-aside");
  aside.append(brand, nav);

  const header = el("header", "d-header");
  header.append(
    el("p", "d-kicker", "Сеанс измерения · 2026-08-29"),
    el("h1", "d-title", "стенд-А"),
  );

  const job = el("div", "d-job");
  job.append(
    el("p", "d-job-text", `${JOB.status} — ${JOB.stage} · ${JOB.series}`),
    el("div", "d-job-track"),
  );

  const metrics = el("section", "d-kpis");
  metrics.setAttribute("data-showcase", "metrics");
  metrics.append(
    kpi("Частота сети", String(METRICS.lineFrequencyHz), "Гц"),
    kpi("σ/μ", METRICS.sigmaRatio.toFixed(2), ""),
    kpi("P_async/P_sync", METRICS.asyncSyncRatio.toFixed(1), ""),
    kpi("Циклов", String(METRICS.cyclesAnalyzed), ""),
  );

  const spectrum = el("section", "d-card d-card-primary");
  spectrum.setAttribute("data-showcase", "spectrum");
  const spectrumHead = el("header", "d-card-head");
  spectrumHead.append(el("h2", "d-card-title", "Спектр мощности"), el("p", "d-card-meta", "А / Б"));
  const spectrumHost = el("div", "d-spectrum");
  spectrum.append(spectrumHead, spectrumHost);

  const catalog = el("section", "d-card");
  catalog.setAttribute("data-showcase", "catalog");
  const catHead = el("header", "d-cat-head");
  catHead.append(
    el("h2", "d-card-title", "Каталог"),
    el("span", "d-card-meta", `${SESSIONS.length}`),
  );
  const list = el("div", "d-cat-list");
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", "Сессии");
  for (const [index, session] of SESSIONS.entries()) {
    const row = el("div", index === 0 ? "d-cat-row is-selected" : "d-cat-row");
    row.setAttribute("data-row", session.storagePath ? "edge" : session.id);
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", index === 0 ? "true" : "false");
    const main = el("div", "d-cat-main");
    main.append(el("span", "d-cat-label", session.label), el("span", "d-cat-id", session.id));
    if (session.storagePath) main.append(el("p", "d-path", session.storagePath));
    const meta = el("div", "d-cat-meta");
    meta.append(
      el("span", "d-cat-type", session.typeLabel),
      el("time", "d-cat-date", session.date),
      el("span", `d-pill d-pill-${session.health}`, `${session.glyph} ${session.healthLabel}`),
    );
    row.append(main, meta);
    list.append(row);
  }
  catalog.append(catHead, list);

  const form = el("form", "d-form");
  form.setAttribute("data-showcase", "capture-form");
  const mode = namedSelect("mode", CAPTURE_MODES);
  const source = namedSelect("source", CAPTURE_SOURCES);
  const range = namedSelect("range", CAPTURE_FORM.ranges);
  const profile = namedSelect("profile", CAPTURE_FORM.profiles);
  const series = el("details", "d-disclosure");
  series.append(
    el("summary", "d-summary", "Серия и протокол"),
    field("Повторы", namedInput("repeat", CAPTURE_FORM.repeat)),
    field("Интервал, с", namedInput("interval", CAPTURE_FORM.intervalS)),
    field("Профиль", profile),
  );
  const submit = el("button", "d-btn d-btn-primary", "Запустить захват");
  submit.type = "submit";
  form.append(
    el("h2", "d-card-title", "Захват"),
    field("Режим", mode),
    field("Источник", source),
    field("Длительность, с", namedInput("duration", CAPTURE_FORM.durationS)),
    field("Частота, Гц", namedInput("rate", CAPTURE_FORM.sampleRateHz)),
    field("Диапазон", range),
    field("Метка", namedInput("label", CAPTURE_FORM.label)),
    series,
    submit,
  );
  form.addEventListener("submit", (event) => event.preventDefault());

  const capture = el("section", "d-card");
  capture.append(form);

  const error = el("div", "d-error");
  error.setAttribute("data-showcase", "error");
  error.setAttribute("role", "alert");
  const retry = el("button", "d-btn", ERROR_STATE.action);
  retry.type = "button";
  error.append(
    el("p", "d-error-title", ERROR_STATE.title),
    el("p", "d-error-msg", ERROR_STATE.message),
    retry,
  );

  const stack = el("div", "d-stack");
  stack.append(catalog, capture, error);

  const main = el("main", "d-main");
  main.append(header, job, metrics, spectrum, stack);

  const shell = el("div", "d-shell");
  shell.setAttribute("data-showcase", "shell");
  shell.append(aside, main);
  app.append(shell);

  renderSpectrum(
    spectrumHost,
    {
      traceA: "#5E6AD2",
      traceB: "#27B6B0",
      grid: "rgba(255,255,255,0.05)",
      axisText: "#8A8F98",
      lineWidth: 2,
      dash: [6, 4],
      axisFont: '11px "JetBrains Mono Variable"',
      height: 240,
    },
    { a: "Сессия А", b: "Сессия Б" },
  );
}

mount();
