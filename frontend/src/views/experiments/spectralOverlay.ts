/** Спектральное наложение условий сравнения (todo 43): uPlot-оверлей
 * средних спектров по включённым участникам каждого условия.
 * Переиспользует createChartShell/createUplotView/theme из todo 41. */

import type { SpectrumPayload } from "../../api/types-plots";
import { filterLogSafePairs } from "../../components/charts/series";
import { readChartTheme } from "../../components/charts/theme";
import type { ChartHandle } from "../../components/charts/types";
import { MARKER_A, MARKER_B } from "../../components/charts/types";
import { createUplotView } from "../../components/charts/uplotView";
import { createChartShell } from "../../components/primitives/chartshell";
import type { ChartShellHandle } from "../../components/primitives/chartshell";
import { el } from "../../components/primitives/dom";

const SYNC_KEY = "lnt-exp-comparison-spectrum";

export type SpectrumFetcher = (sessionId: string, signal: AbortSignal) => Promise<SpectrumPayload>;

function meanSeries(payloads: SpectrumPayload[]): { x: number[]; y: number[] } | null {
  if (payloads.length === 0) return null;
  const reference = payloads[0];
  if (!reference) return null;
  const x = reference.frequency_hz;
  const acc = new Array<number>(x.length).fill(0);
  let used = 0;
  for (const payload of payloads) {
    if (payload.frequency_hz.length !== x.length) continue;
    for (let i = 0; i < x.length; i += 1) {
      const v = payload.psd_v2_per_hz[i];
      if (typeof v === "number") acc[i] = (acc[i] ?? 0) + v;
    }
    used += 1;
  }
  if (used === 0) return null;
  return { x: [...x], y: acc.map((sum) => sum / used) };
}

export class SpectralOverlay {
  readonly root: HTMLElement;
  private readonly shell: ChartShellHandle;
  private readonly handle: ChartHandle;
  private readonly fetcher: SpectrumFetcher;

  constructor(fetcher: SpectrumFetcher, createView?: typeof createUplotView) {
    this.fetcher = fetcher;
    const theme = readChartTheme();
    const factory = createView ?? createUplotView;
    this.shell = createChartShell({ title: "Спектральное наложение условий" });
    this.handle = factory({ container: this.shell.body, syncKey: SYNC_KEY });
    this.root = el("section", { className: "lnt-exp-overlay" }, [
      el("h3", { className: "lnt-exp-subtitle", text: "Спектр/полосы/гармоники" }),
      el("p", {
        className: "lnt-helper-text",
        text: "Средние сырые PSD (scope-plane) участников каждого условия; приведение ко входу не применяется.",
      }),
      this.shell.root,
    ]);
    void theme;
  }

  async show(
    conditions: { label: string; sessionIds: string[] }[],
    signal: AbortSignal,
  ): Promise<void> {
    this.shell.setLoading();
    const series: {
      label: string;
      values: number[];
      color: string;
      dash?: readonly [number, number];
      marker?: string;
    }[] = [];
    const markers = [MARKER_A, MARKER_B];
    let sharedX: number[] | null = null;
    try {
      for (const [index, condition] of conditions.entries()) {
        const payloads = await Promise.all(
          condition.sessionIds.map((id) => this.fetcher(id, signal)),
        );
        const mean = meanSeries(payloads);
        if (mean === null) continue;
        sharedX = sharedX ?? mean.x;
        series.push({
          label: condition.label,
          values: mean.y,
          color: index === 0 ? "var(--lnt-accent-a)" : "var(--lnt-accent-b)",
          dash: index === 0 ? undefined : ([6, 4] as const),
          marker: markers[index] ?? "●",
        });
      }
    } catch (error) {
      if (signal.aborted) return;
      this.shell.setError("Не удалось загрузить спектры для наложения.", () => undefined);
      return;
    }
    if (sharedX === null || series.length === 0) {
      this.shell.setEmpty("Нет спектров для наложения: данные недоступны.");
      return;
    }
    const filtered = series.map((s) => filterLogSafePairs(sharedX ?? [], s.values));
    const first = filtered[0];
    if (!first) return;
    this.shell.setContent(this.handle.root);
    this.handle.render({
      xLabel: "Частота, Гц",
      yLabel: "PSD, В²/Гц",
      xLog: true,
      yLog: true,
      x: first.x,
      series: filtered.map((pairs, i) => {
        const base = series[i];
        return {
          label: base?.label ?? `Условие ${String(i + 1)}`,
          values: pairs.y,
          color: base?.color ?? "var(--lnt-accent-a)",
          dash: base?.dash,
          marker: base?.marker,
        };
      }),
    });
  }

  destroy(): void {
    this.handle.destroy();
  }
}
