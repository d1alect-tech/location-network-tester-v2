/** Тесты моделей графиков (todo 41): гонка устаревших ответов, отмена
 * запроса при смене диапазона/выбора, числовой паритет с фикстурой бэкенда,
 * искажённые полезные нагрузки → типизированная ошибка в оболочке. */

import { beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "../../api/errors";
import type { SpectrumPayload, WaveformPayload } from "../../api/types-plots";
import type { ChartShellHandle } from "../primitives/chartshell";
import { createChartShell } from "../primitives/chartshell";
import type { ChartHandle, ChartRenderRequest } from "./types";
import { createChartModel, spectrumToRequest, waveformToRequest } from "./viewModels";

const STYLE_A = { label: "Сессия А", color: "#00a3ff", marker: "●" } as const;
const STYLE_B = {
  label: "Сессия Б",
  color: "#ffb000",
  marker: "■",
  dash: [6, 4],
} as const;

/** Бэкенд-фикстура: спектр из 8 бинов с известными min/max. */
const SPECTRUM_FIXTURE: SpectrumPayload = {
  frequency_hz: [10, 50, 100, 500, 1000, 5000, 10_000, 20_000],
  psd_v2_per_hz: [1e-4, 1e-3, 1e-2, 5e-2, 1e-2, 1e-3, 1e-4, 1e-5],
  point_count: 8,
};

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

interface FakeShell extends ChartShellHandle {
  states(): string[];
}

function makeFakeShell(): FakeShell {
  const history: string[] = [];
  const shell = createChartShell({ title: "Тест" }) as FakeShell;
  const setLoading = shell.setLoading.bind(shell);
  const setError = shell.setError.bind(shell);
  const setContent = shell.setContent.bind(shell);
  shell.setLoading = () => {
    history.push("loading");
    setLoading();
  };
  shell.setError = (message, retry) => {
    history.push(`error:${message}`);
    setError(message, retry);
  };
  shell.setContent = (content) => {
    history.push("ready");
    setContent(content);
  };
  shell.states = () => history;
  return shell;
}

function makeFakeHandle(): ChartHandle & { renders: ChartRenderRequest[] } {
  const root = document.createElement("div");
  return {
    root,
    renders: [],
    render(request) {
      this.renders.push(request);
    },
    applyTheme() {},
    getData: () => null,
    destroy() {},
  };
}

describe("createChartModel", () => {
  let shell: FakeShell;

  beforeEach(() => {
    document.body.textContent = "";
    shell = makeFakeShell();
  });

  it("устаревший ответ не может отрисовать старую серию (гонка)", async () => {
    const handle = makeFakeHandle();
    const gates = {
      slow: deferred<SpectrumPayload>(),
      fast: deferred<SpectrumPayload>(),
    };
    const model = createChartModel<SpectrumPayload>({
      shell,
      handle,
      fetch: (name) => (name === "slow" ? gates.slow.promise : gates.fast.promise),
      toRequest: (payload) => spectrumToRequest(payload, STYLE_A, { kind: "psd" }, false, []),
      toCsv: () => null,
    });

    const slowRun = model.load("slow");
    const fastRun = model.load("fast");
    gates.fast.resolve(SPECTRUM_FIXTURE);
    await fastRun;
    // Поздний ответ медленного запроса игнорируется целиком.
    gates.slow.resolve({ ...SPECTRUM_FIXTURE, psd_v2_per_hz: [-1] });
    await slowRun;

    expect(handle.renders).toHaveLength(1);
    expect(handle.renders[0]?.x).toEqual(SPECTRUM_FIXTURE.frequency_hz);
    expect(shell.states()).toEqual(["loading", "loading", "ready"]);
  });

  it("новый запрос отменяет предыдущий через AbortSignal", async () => {
    const handle = makeFakeHandle();
    const signals: AbortSignal[] = [];
    const model = createChartModel<SpectrumPayload>({
      shell,
      handle,
      fetch: (_name, signal) => {
        signals.push(signal);
        return Promise.resolve(SPECTRUM_FIXTURE);
      },
      toRequest: (payload) => spectrumToRequest(payload, STYLE_A, { kind: "psd" }, false, []),
      toCsv: () => null,
    });
    await model.load("первая");
    await model.load("вторая");
    expect(signals[0]?.aborted).toBe(true);
    expect(signals[1]?.aborted).toBe(false);
    expect(model.currentName()).toBe("вторая");
  });

  it("искажённая нагрузка → ошибка в оболочке с повтором, не пустой график", async () => {
    const handle = makeFakeHandle();
    const model = createChartModel<SpectrumPayload>({
      shell,
      handle,
      fetch: async () => {
        throw new ApiError("parse");
      },
      toRequest: (payload) => spectrumToRequest(payload, STYLE_A, { kind: "psd" }, false, []),
      toCsv: () => null,
    });
    await model.load("сломанная");
    expect(handle.renders).toHaveLength(0);
    const states = shell.states().join("|");
    expect(states).toContain("error:");
    expect(spectrumShellErrorText(shell)).toContain("Некорректный ответ сервера");
    // Кнопка «Повторить» присутствует и перезапускает загрузку.
    const retry = [...shell.root.querySelectorAll("button")].find(
      (b) => b.textContent === "Повторить",
    );
    expect(retry).not.toBeNull();
  });

  it("числовой паритет: линейные оси передают значения фикстуры без изменений", () => {
    const request = spectrumToRequest(SPECTRUM_FIXTURE, STYLE_A, { kind: "psd" }, false, []);
    expect(request.x).toEqual(SPECTRUM_FIXTURE.frequency_hz);
    expect(request.series[0]?.values).toEqual(SPECTRUM_FIXTURE.psd_v2_per_hz);
    expect(request.xLog).toBe(true); // ось X логарифмическая, фильтрация не нужна
    expect(request.yLog).toBe(false);
  });

  it("лог-ось Y детерминированно отбрасывает пары ≤ 0", () => {
    const payload: SpectrumPayload = {
      frequency_hz: [1, 2, 3, 4],
      psd_v2_per_hz: [5, -7, 0, 9],
      point_count: 4,
    };
    const request = spectrumToRequest(payload, STYLE_A, { kind: "psd" }, true, []);
    expect(request.x).toEqual([1, 4]);
    expect(request.series[0]?.values).toEqual([5, 9]);
  });

  it("ASD считается как корень из PSD", () => {
    const request = spectrumToRequest(SPECTRUM_FIXTURE, STYLE_A, { kind: "asd" }, true, []);
    expect(request.series[0]?.values?.[2]).toBeCloseTo(Math.sqrt(1e-2), 12);
    expect(request.yLabel).toContain("ASD");
  });

  it("стиль Б: янтарный пунктир и квадрат в метке серии", () => {
    const waveform: WaveformPayload = {
      channel: "ch2",
      time_s: [0, 0.1],
      voltage_v: [1, -1],
      point_count: 2,
    };
    const request = waveformToRequest(waveform, STYLE_B);
    expect(request.series[0]?.color).toBe("#ffb000");
    expect([...(request.series[0]?.dash ?? [])]).toEqual([6, 4]);
    expect(request.series[0]?.marker).toBe("■");
  });
});

function spectrumShellErrorText(shell: ChartShellHandle): string {
  return shell.body.textContent ?? "";
}
