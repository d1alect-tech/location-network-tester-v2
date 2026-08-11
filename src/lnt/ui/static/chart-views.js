import { loadPlotly } from "./plotly-loader.js";
import { element } from "./view-dom.js";

const LOADING_MESSAGE = "Загрузка графика…";
const ERROR_MESSAGE = "Не удалось загрузить график. Повторите открытие сессии.";

export function createChartShell({ name, caption, plotClass, hidden = false }) {
  const block = element("div", "chart-block");
  block.id = `${name}-chart`;
  block.setAttribute("role", "region");
  block.setAttribute("aria-labelledby", `${name}-caption`);

  const figure = element("figure", "chart-figure");
  figure.id = `${name}-figure`;
  figure.setAttribute("aria-labelledby", `${name}-caption`);
  const figcaption = element("figcaption", "visually-hidden", caption);
  figcaption.id = `${name}-caption`;

  const target = element("div", `plot ${plotClass}`);
  target.id = `${name}-plot`;
  target.dataset.chartState = "idle";
  target.setAttribute("aria-busy", "false");
  target.setAttribute("aria-describedby", `${name}-status`);

  const status = element("p", "chart-status");
  status.id = `${name}-status`;
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  status.setAttribute("aria-atomic", "true");

  if (hidden) {
    block.hidden = true;
    figure.hidden = true;
    target.hidden = true;
  }
  figure.append(figcaption, target);
  block.append(figure, status);
  return block;
}

function readBrowserPlotTokens() {
  const styles = getComputedStyle(document.documentElement);
  return {
    lineA: styles.getPropertyValue("--plot-line-a").trim(),
    lineB: styles.getPropertyValue("--plot-line-b").trim(),
    grid: styles.getPropertyValue("--plot-grid").trim(),
    plot: styles.getPropertyValue("--plot-bg").trim(),
    paper: styles.getPropertyValue("--surface-panel").trim(),
    text: styles.getPropertyValue("--text-secondary").trim(),
    lineWidth: Number.parseFloat(styles.getPropertyValue("--plot-line-width")),
  };
}

function spectrumDefinition(spectrum, colors) {
  const levelDb = spectrum.psd_v2_per_hz.map((value) => 10 * Math.log10(value));
  return {
    traces: [{
      type: "scattergl",
      mode: "lines",
      name: "A",
      x: spectrum.frequency_hz,
      y: spectrum.psd_v2_per_hz,
      customdata: levelDb,
      hovertemplate: "%{x:.0f} Гц<br>%{y:.3e} В²/Гц<br>%{customdata:.1f} дБ<extra>A</extra>",
      line: { color: colors.lineA, width: colors.lineWidth },
    }],
    layout: {
      autosize: true,
      paper_bgcolor: colors.paper,
      plot_bgcolor: colors.plot,
      font: { color: colors.text },
      xaxis: { type: "log", title: "Частота, Гц", gridcolor: colors.grid },
      yaxis: { type: "log", title: "PSD, В²/Гц", gridcolor: colors.grid },
    },
  };
}

function waveformDefinition(waveform, colors) {
  const isSecondChannel = waveform.channel === "ch2";
  return {
    traces: [{
      type: "scattergl",
      mode: "lines",
      name: waveform.channel.toUpperCase(),
      x: waveform.time_s,
      y: waveform.voltage_v,
      line: {
        color: isSecondChannel ? colors.lineB : colors.lineA,
        dash: isSecondChannel ? "dash" : "solid",
        width: colors.lineWidth,
      },
    }],
    layout: {
      autosize: true,
      paper_bgcolor: colors.paper,
      plot_bgcolor: colors.plot,
      font: { color: colors.text },
      xaxis: { title: "Время, с", gridcolor: colors.grid },
      yaxis: { title: "Напряжение, В", gridcolor: colors.grid },
    },
  };
}

function revealChart(target) {
  target.hidden = false;
  target.parentElement.hidden = false;
  target.parentElement.parentElement.hidden = false;
}

function setChartLoading(target, status) {
  target.setAttribute("aria-busy", "true");
  target.dataset.chartState = "loading";
  status.textContent = LOADING_MESSAGE;
}

function setChartReady(target, status) {
  target.setAttribute("aria-busy", "false");
  target.dataset.chartState = "ready";
  status.textContent = "";
}

function setChartError(target, status) {
  target.setAttribute("aria-busy", "false");
  target.dataset.chartState = "error";
  target.replaceChildren();
  status.textContent = ERROR_MESSAGE;
}

export function createChartRenderer({ loadPlotly: load, getElementById, readPlotTokens }) {
  const chains = new Map();
  const owners = new Map();
  const plots = new Map();
  let plotlyRef = null;

  async function renderChart({ targetId, payload, definition, reveal, isCurrent, token }) {
    if (!isCurrent()) return undefined;
    const target = getElementById(targetId);
    const status = getElementById(target.getAttribute("aria-describedby"));
    const isOwner = () => owners.get(targetId) === token;
    if (reveal) revealChart(target);
    setChartLoading(target, status);
    const config = { responsive: true, displaylogo: false };
    try {
      const plotly = await load();
      plotlyRef = plotly;
      if (!isCurrent()) return undefined;
      const chart = definition(payload, readPlotTokens());
      const result = await plotly.newPlot(target, chart.traces, chart.layout, config);
      if (isCurrent() && isOwner()) {
        setChartReady(target, status);
        plots.set(targetId, { payload, definition, config });
      }
      return result;
    } catch (error) {
      if (isCurrent() && isOwner()) {
        setChartError(target, status);
        plots.delete(targetId);
      }
      throw error;
    }
  }

  function scheduleChart(options) {
    const token = Symbol("chart-request");
    owners.set(options.targetId, token);
    const pending = chains.get(options.targetId);
    const run = () => renderChart({ ...options, token });
    const next = pending === undefined ? run() : pending.catch(() => undefined).then(run);
    chains.set(options.targetId, next);
    next.catch(() => undefined).finally(() => {
      if (chains.get(options.targetId) === next) chains.delete(options.targetId);
    });
    return next;
  }

  function failChart(targetId) {
    const target = getElementById(targetId);
    if (target.dataset.chartState !== "loading") return;
    setChartError(target, getElementById(target.getAttribute("aria-describedby")));
  }

  function applyTheme() {
    if (plotlyRef === null) return;
    for (const [targetId, entry] of plots) {
      const target = getElementById(targetId);
      if (!target || target.dataset.chartState !== "ready") continue;
      const chart = entry.definition(entry.payload, readPlotTokens());
      plotlyRef.react(target, chart.traces, chart.layout, entry.config);
    }
  }

  return {
    failChart,
    applyTheme,
    plotSpectrum: (targetId, spectrum, { isCurrent = () => true } = {}) => scheduleChart({
      targetId,
      payload: spectrum,
      definition: spectrumDefinition,
      reveal: false,
      isCurrent,
    }),
    plotWaveform: (targetId, waveform, { isCurrent = () => true } = {}) => scheduleChart({
      targetId,
      payload: waveform,
      definition: waveformDefinition,
      reveal: true,
      isCurrent,
    }),
  };
}

const browserRenderer = typeof document === "undefined"
  ? null
  : createChartRenderer({
    loadPlotly,
    getElementById: (id) => document.getElementById(id),
    readPlotTokens: readBrowserPlotTokens,
  });

export async function plotSpectrum(divId, spectrum, options = {}) {
  return await browserRenderer.plotSpectrum(divId, spectrum, options);
}

export async function plotWaveform(divId, waveform, options = {}) {
  return await browserRenderer.plotWaveform(divId, waveform, options);
}

export function failChart(divId) {
  browserRenderer.failChart(divId);
}

export function applyChartTheme() {
  browserRenderer?.applyTheme();
}
