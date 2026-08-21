/** Характеризационный тест (todo 41): фиксирует наблюдаемые точки входа
 * графиков v2 ДО замены Plotly на uPlot — контракты plots-API, бюджеты
 * точек, гонка устаревших ответов и свобода chartshell от библиотек. */

import { describe, expect, it } from "vitest";
import { LntApiClient } from "../../api/client";
import { SPECTRUM_MAX_POINTS, WAVEFORM_MAX_POINTS } from "../../api/types-plots";
import { createResourceLoader } from "../../state/resource";
import { createChartShell } from "../primitives/chartshell";

type FetchCall = { url: string; init: RequestInit | undefined };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeFetch(
  handler: (url: string, init: RequestInit | undefined) => Response | Promise<Response>,
): { fetch: typeof fetch; calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  const impl = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    calls.push({ url, init });
    return handler(url, init);
  };
  return { fetch: impl as unknown as typeof fetch, calls };
}

describe("графики workbench: характеризация до todo 41", () => {
  it("plots API запрашивает закреплённые эндпоинты с лимитами точек", async () => {
    const { fetch, calls } = makeFetch((url) => {
      if (url.includes("/spectrum")) {
        return jsonResponse({ frequency_hz: [10], psd_v2_per_hz: [1], point_count: 1 });
      }
      return jsonResponse({
        channel: "ch2",
        time_s: [0],
        voltage_v: [-0.5],
        point_count: 1,
      });
    });
    const client = new LntApiClient(fetch);

    const spectrum = await client.plots.spectrum("sess-a", SPECTRUM_MAX_POINTS.default);
    const waveform = await client.plots.waveform("sess-a", "ch2", WAVEFORM_MAX_POINTS.default);

    expect(spectrum.point_count).toBe(1);
    expect(spectrum.frequency_hz).toEqual([10]);
    expect(waveform.channel).toBe("ch2");
    expect(calls[0]?.url).toBe("/api/sessions/sess-a/spectrum?max_points=5000");
    expect(calls[1]?.url).toBe("/api/sessions/sess-a/waveform?channel=ch2&max_points=4000");
  });

  it("искажённая полезная нагрузка графика даёт типизированную ошибку parse", async () => {
    const { fetch } = makeFetch(() => jsonResponse({ frequency_hz: "не массив" }));
    const client = new LntApiClient(fetch);
    await expect(client.plots.spectrum("s")).rejects.toMatchObject({
      name: "ApiError",
      kind: "parse",
    });
  });

  it("бюджеты точек совпадают с контрактами бэкенда", () => {
    expect(SPECTRUM_MAX_POINTS).toEqual({ min: 16, max: 20_000, default: 5_000 });
    expect(WAVEFORM_MAX_POINTS).toEqual({ min: 16, max: 4_000, default: 4_000 });
  });

  it("устаревший ответ графика отбрасывается общим гонко-защитником", async () => {
    interface Deferred<T> {
      promise: Promise<T>;
      resolve: (value: T) => void;
    }
    function deferred<T>(): Deferred<T> {
      let resolve!: (value: T) => void;
      const promise = new Promise<T>((res) => {
        resolve = res;
      });
      return { promise, resolve };
    }

    const slow = deferred<string>();
    const fast = deferred<string>();
    const signals: AbortSignal[] = [];
    const loader = createResourceLoader<string>((key, signal) => {
      signals.push(signal);
      return key === "slow" ? slow.promise : fast.promise;
    });

    const slowRun = loader.load("slow");
    const fastRun = loader.load("fast");
    fast.resolve("быстрые-данные");
    await fastRun;
    slow.resolve("устаревшие-данные");
    await slowRun;

    expect(loader.get()).toEqual({ kind: "ready", key: "fast", value: "быстрые-данные" });
    expect(signals[0]?.aborted).toBe(true);
  });

  it("chartshell остаётся точкой монтирования без библиотек графиков", async () => {
    const source = await import("../primitives/chartshell?raw");
    expect(source.default).not.toMatch(/from\s+["'](echarts|uplot|plotly)/);
    const shell = createChartShell({ title: "Спектр мощности" });
    expect(shell.root.textContent).toContain("Спектр мощности");
  });
});
