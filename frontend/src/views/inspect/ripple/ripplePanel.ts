/** Жизненный цикл панели «Риппл / шум»: один GET сохранённого артефакта на
 * выбранную сессию, отмена прошлой загрузки, переключение PSD/ASD и полосы
 * БЕЗ нового запроса. Ошибки маршрута рендерятся честной причиной. */

import { RippleApiError } from "../../../api/client-ripple";
import type { RippleApi } from "../../../api/client-ripple";
import { isAbortError } from "../../../api/errors";
import type { RippleArtifactPayload, RippleConflictReason } from "../../../api/types-ripple";
import { readChartTheme } from "../../../components/charts/theme";
import type { ChartHandle } from "../../../components/charts/types";
import { createUplotView } from "../../../components/charts/uplotView";
import type { UplotViewOptions } from "../../../components/charts/uplotView";
import { chartRequest } from "./rippleChart";
import type { RippleSpectrumMode } from "./rippleChart";
import { buildRippleView } from "./rippleModel";
import { createRipplePanelView } from "./ripplePanelView";
import "./ripple.css";

export type RipplePanelHandle = {
  readonly root: HTMLElement;
  setPair(session: string | null): Promise<void>;
  destroy(): void;
};

export type RipplePanelOptions = {
  readonly api: RippleApi | null;
  readonly createView?: (options: UplotViewOptions) => ChartHandle;
};

const CONFLICT_RU: Readonly<Record<RippleConflictReason, string>> = {
  corrupt: "файл повреждён",
  schema_incompatible: "схема не совместима с v1",
  stale_input: "входные файлы изменились",
  unsafe_sidecar: "файл сайдкара небезопасен",
};

type Failure = { readonly kind: string; readonly reason: string; readonly text: string };

function failureOf(error: unknown): Failure {
  if (!(error instanceof RippleApiError)) {
    const text = error instanceof Error ? error.message : String(error);
    return {
      kind: "unexpected",
      reason: "",
      text: `Не удалось загрузить ripple-артефакт: ${text}`,
    };
  }
  if (error.kind !== "conflict") {
    return { kind: error.kind, reason: "", text: error.message };
  }
  const reason = error.reason ?? "";
  const ru = error.reason === undefined ? "причина не указана сервером" : CONFLICT_RU[error.reason];
  const code = reason === "" ? "409" : `409, ${reason}`;
  return {
    kind: "conflict",
    reason,
    text: `Артефакт не согласован с сессией: ${ru} (${code}). Запустите анализ ripple заново.`,
  };
}

export function createRipplePanel(opts: RipplePanelOptions): RipplePanelHandle {
  const view = createRipplePanelView();
  const chart = (opts.createView ?? createUplotView)({
    container: view.chartHost,
    syncKey: "lnt-inspect-ripple",
  });
  view.chartHost.append(chart.root);
  const theme = readChartTheme();

  let mode: RippleSpectrumMode = "psd";
  let generation = 0;
  let controller = new AbortController();
  let artifact: RippleArtifactPayload | null = null;
  let bandIndex = 0;

  function renderChart(): void {
    if (artifact === null) {
      view.chartEmpty("спектр не загружен");
      return;
    }
    const request = chartRequest(artifact, mode, theme.accentA);
    if (request === null) {
      const model = buildRippleView(artifact, bandIndex);
      view.chartEmpty(model.spectrumText === "" ? "спектр недоступен" : model.spectrumText);
      return;
    }
    view.chartReady();
    chart.render(request);
  }

  function paint(): void {
    if (artifact === null) return;
    const model = buildRippleView(artifact, bandIndex);
    bandIndex = model.selectedBand;
    view.paint(model);
    view.setBands(model.bands, model.selectedBand);
    view.setMode(mode);
    renderChart();
  }

  function setMode(next: RippleSpectrumMode): void {
    if (next === mode) return;
    mode = next;
    view.setMode(mode);
    if (artifact !== null) renderChart();
  }

  async function setPair(session: string | null): Promise<void> {
    const gen = ++generation;
    controller.abort();
    controller = new AbortController();
    artifact = null;
    bandIndex = 0;
    if (session === null || session === "") {
      view.clear("");
      return;
    }
    view.begin(session);
    if (opts.api === null) {
      view.fail("unavailable", "", "Клиент ripple недоступен в этой сборке.");
      return;
    }
    try {
      const loaded = await opts.api.artifact(session, { signal: controller.signal });
      if (gen !== generation) return;
      artifact = loaded;
      paint();
    } catch (error) {
      if (gen !== generation || isAbortError(error)) return;
      const failure = failureOf(error);
      view.fail(failure.kind, failure.reason, failure.text);
    }
  }

  function onPsd(): void {
    setMode("psd");
  }
  function onAsd(): void {
    setMode("asd");
  }
  function onBand(): void {
    if (artifact === null) return;
    const index = artifact.bands.findIndex((band) => band.id === view.bandSelect.value);
    if (index < 0) return;
    bandIndex = index;
    paint();
  }

  view.modeButtons.psd.addEventListener("click", onPsd);
  view.modeButtons.asd.addEventListener("click", onAsd);
  view.bandSelect.addEventListener("change", onBand);
  view.setMode(mode);
  view.clear("");

  return {
    root: view.root,
    setPair,
    destroy() {
      generation += 1;
      controller.abort();
      view.modeButtons.psd.removeEventListener("click", onPsd);
      view.modeButtons.asd.removeEventListener("click", onAsd);
      view.bandSelect.removeEventListener("change", onBand);
      artifact = null;
      chart.destroy();
      view.root.remove();
    },
  };
}
