import "./fonts/fonts.css";
import "./variantC.css";
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
  attrs: Record<string, string> = {},
  kids: Array<Node | string> = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const kid of kids) node.append(kid);
  return node;
}

function field(label: string, control: HTMLElement): HTMLLabelElement {
  return h("label", { class: "tui-field" }, [h("span", { class: "tui-k", text: label }), control]);
}

function sel(
  name: string,
  items: readonly { readonly id: string; readonly title: string }[],
): HTMLSelectElement {
  const node = h("select", { class: "tui-ctl", name });
  for (const item of items) node.append(h("option", { value: item.id, text: item.title }));
  return node;
}

function inp(name: string, value: string): HTMLInputElement {
  return h("input", { class: "tui-ctl", name, value, spellcheck: "false", autocomplete: "off" });
}

function metric(key: string, value: string, live = false): HTMLElement {
  return h("div", { class: live ? "tui-metric is-live" : "tui-metric" }, [
    h("div", { class: "tui-val", text: value }),
    h("div", { class: "tui-key", text: key }),
  ]);
}

function catalog(): HTMLElement {
  const pane = h("section", { class: "tui-pane", "data-showcase": "catalog" });
  pane.append(h("h2", { class: "tui-hd", text: "[ 01_КАТАЛОГ_СЕССИЙ ]" }));
  const list = h("div", { class: "tui-list" });
  for (const [index, session] of SESSIONS.entries()) {
    const edge = Boolean(session.storagePath);
    const row = h("button", {
      class: `tui-row${index === 0 ? " is-on" : ""}${edge ? " is-edge" : ""}`,
      type: "button",
      "data-row": edge ? "edge" : session.id,
    });
    row.append(
      h("span", { class: "tui-idx", text: `${String(index + 1).padStart(3, "0")}>` }),
      h("span", { class: "tui-glyph", text: session.glyph }),
      h("span", { class: "tui-name", text: session.label }),
      h("span", { class: "tui-type", text: session.typeLabel }),
      h("span", { class: "tui-date", text: session.date }),
      h("span", {
        class: `tui-chip is-${session.health}`,
        text: `[${session.healthLabel.toUpperCase()}]`,
      }),
    );
    if (session.storagePath) {
      row.append(h("span", { class: "tui-path", text: session.storagePath }));
    }
    row.addEventListener("click", () => {
      list.querySelector(".is-on")?.classList.remove("is-on");
      row.classList.add("is-on");
    });
    list.append(row);
  }
  pane.append(list);
  return pane;
}

function spectrum(): HTMLElement {
  const pane = h("section", { class: "tui-pane", "data-showcase": "spectrum" });
  const peak = PEAKS[0];
  const chip = peak
    ? `[▲ ПИК: −${Math.abs(peak.levelDb).toFixed(1)} дБ @ ${formatHz(peak.frequencyHz)}]`
    : "";
  pane.append(h("h2", { class: "tui-hd", text: `[ 02_СПЕКТР ] ${chip}` }));
  const host = h("div", { class: "tui-plot" });
  pane.append(host);
  const sessionA = SESSIONS[0];
  const sessionB = SESSIONS[1];
  renderSpectrum(
    host,
    {
      traceA: "#00FF88",
      traceB: "#00E5FF",
      grid: "#1E2C3A",
      axisText: "#4A6B82",
      lineWidth: 1.5,
      dash: [3, 3],
      axisFont: '11px "JetBrains Mono Variable"',
      height: 220,
    },
    { a: `▮ ${sessionA?.label ?? "А"}`, b: `▯ ${sessionB?.label ?? "Б"}` },
  );
  return pane;
}

function metrics(): HTMLElement {
  const pane = h("section", { class: "tui-pane", "data-showcase": "metrics" });
  pane.append(h("h2", { class: "tui-hd", text: "[ 03_ТЕЛЕМЕТРИЯ ]" }));
  const ru = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 7 });
  pane.append(
    h("div", { class: "tui-metrics" }, [
      metric("Частота сети", `${METRICS.lineFrequencyHz} Гц`, true),
      metric("μ_pk", `${ru.format(METRICS.needleMeanV)} В`),
      metric("σ/μ", ru.format(METRICS.sigmaRatio)),
      metric("P_async/P_sync", ru.format(METRICS.asyncSyncRatio)),
      metric("Циклы", ru.format(METRICS.cyclesAnalyzed)),
      metric("Частота дискр.", formatHz(METRICS.sampleRateHz)),
      metric("Длительность", `${METRICS.durationS} с`),
      metric("Полоса", `${formatHz(METRICS.bandLowHz)} – ${formatHz(METRICS.bandHighHz)}`),
      metric("Разрешение", formatHz(METRICS.resolutionHz)),
    ]),
  );
  return pane;
}

function capture(): HTMLFormElement {
  const form = h("form", { class: "tui-pane tui-form", "data-showcase": "capture-form" });
  form.append(h("h2", { class: "tui-hd", text: "[ 04_ЗАХВАТ ]" }));
  const ranges = CAPTURE_FORM.ranges.map((title) => ({ id: title, title }));
  const profiles = CAPTURE_FORM.profiles.map((title) => ({ id: title, title }));
  form.append(
    h("div", { class: "tui-fields" }, [
      field("Режим", sel("mode", CAPTURE_MODES)),
      field("Источник", sel("source", CAPTURE_SOURCES)),
      field("Длительность, с", inp("duration", CAPTURE_FORM.durationS)),
      field("Частота, Гц", inp("rate", CAPTURE_FORM.sampleRateHz)),
      field("Диапазон CH1", sel("range", ranges)),
      field("Метка", inp("label", CAPTURE_FORM.label)),
    ]),
  );
  const extra = h("details", { class: "tui-more", open: "" });
  extra.append(
    h("summary", { text: "Серия и протокол" }),
    h("div", { class: "tui-fields" }, [
      field("Повторы", inp("repeat", CAPTURE_FORM.repeat)),
      field("Интервал, с", inp("interval", CAPTURE_FORM.intervalS)),
      field("Профиль", sel("profile", profiles)),
    ]),
  );
  form.append(extra, h("button", { class: "tui-btn", type: "submit", text: "Запустить захват" }));
  form.addEventListener("submit", (event) => event.preventDefault());
  return form;
}

function errorPane(): HTMLElement {
  const pane = h("section", {
    class: "tui-pane tui-fatal",
    "data-showcase": "error",
    role: "alert",
  });
  pane.append(
    h("h2", { class: "tui-hd tui-hd-fatal", text: "[ FATAL ]" }),
    h("p", { class: "tui-err-title", text: ERROR_STATE.title }),
    h("p", { class: "tui-err-msg", text: ERROR_STATE.message }),
    h("button", { class: "tui-btn tui-btn-fatal", type: "button", text: ERROR_STATE.action }),
  );
  return pane;
}

function mount(): void {
  const app = document.getElementById("app");
  if (!app) throw new Error("нет #app");
  app.className = "tui";
  app.setAttribute("data-showcase", "shell");
  const bar = h("header", { class: "tui-bar" }, [
    h("span", { class: "tui-brand", text: "[ LNT v2 ]" }),
    h("span", { class: "tui-live", text: `${METRICS.lineFrequencyHz} ГЦ` }),
    h("span", { class: "tui-pipe", text: "|" }),
    h("span", { text: JOB.stage.toUpperCase() }),
    h("span", { class: "tui-pipe", text: "|" }),
    h("span", { text: JOB.series.toUpperCase() }),
    h("span", { class: "tui-pipe", text: "|" }),
    h("span", { class: "is-ok", text: "УСТРОЙСТВО: ГОТОВО" }),
    h("span", { class: "tui-bar-end", text: JOB.status.toUpperCase() }),
  ]);
  const left = h("div", { class: "tui-col" }, [catalog(), capture()]);
  const right = h("div", { class: "tui-col" }, [spectrum(), metrics(), errorPane()]);
  app.append(bar, h("div", { class: "tui-body" }, [left, right]));
}

mount();
