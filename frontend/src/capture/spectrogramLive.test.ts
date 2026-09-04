/** Live-панель спектрограммы захвата (S3, TDD RED): ring-buffer renderer,
 * poll-решения, post-hoc fallback, пустое состояние. Источник данных —
 * только существующие GET /api/sessions/{name}/spectrum через plots-api. */

import { afterEach, describe, expect, it, vi } from "vitest";
import type { JobSnapshot } from "../api/types-jobs";
import { snap } from "../testkit/mockJobStore";
import { createSpectrogramLivePanel } from "./spectrogramLivePanel";
import {
  LIVE_POLL_MS,
  createLivePoller,
  pickFallbackSessionName,
  pickLiveSessionName,
  toDbColumn,
} from "./spectrogramLivePoller";
import { FREQ_BINS, TIME_BINS, buildSpectrogramLiveRenderer } from "./spectrogramLiveRenderer";

function runningSnap(written: string[]): JobSnapshot {
  return snap(2, {
    job_id: "job-1",
    status: "running",
    stage: "capturing",
    written_sessions: written,
  });
}

function doneSnap(written: string[]): JobSnapshot {
  return snap(9, {
    job_id: "job-1",
    status: "succeeded",
    stage: "done",
    written_sessions: written,
    result: { sessions: written },
  });
}

function logFreqs(count: number, minHz = 10, maxHz = 10_000_000): number[] {
  const lo = Math.log10(minHz);
  const hi = Math.log10(maxHz);
  return Array.from({ length: count }, (_, i) => 10 ** (lo + ((hi - lo) * i) / (count - 1)));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("renderer: push и ring-buffer", () => {
  it("pushSpectrumColumn накапливает колонки до TIME_BINS", () => {
    const renderer = buildSpectrogramLiveRenderer();
    try {
      const freqs = logFreqs(64);
      renderer.pushSpectrumColumn(
        freqs,
        freqs.map(() => -50),
      );
      renderer.pushSpectrumColumn(
        freqs,
        freqs.map(() => -40),
      );
      expect(renderer.columnCount()).toBe(2);
    } finally {
      renderer.dispose();
    }
  });

  it("кольцо перезаписывает старые колонки после TIME_BINS", () => {
    const renderer = buildSpectrogramLiveRenderer();
    try {
      const freqs = logFreqs(64);
      for (let i = 0; i < TIME_BINS + 5; i += 1) {
        renderer.pushSpectrumColumn(
          freqs,
          freqs.map(() => -50 - i),
        );
      }
      expect(renderer.columnCount()).toBe(TIME_BINS);
      expect(TIME_BINS).toBe(48);
      expect(FREQ_BINS).toBeGreaterThanOrEqual(256);
    } finally {
      renderer.dispose();
    }
  });

  it("setFreqDomain меняет домен вместо attach(plot)", () => {
    const renderer = buildSpectrogramLiveRenderer();
    try {
      renderer.setFreqDomain(100, 1000);
      expect(renderer.freqDomain()).toEqual({ minHz: 100, maxHz: 1000 });
      expect("attach" in renderer).toBe(false);
    } finally {
      renderer.dispose();
    }
  });
});

describe("renderer: rAF-throttle и dispose", () => {
  it("пачка push планирует один rAF-кадр", () => {
    const rafCallbacks: FrameRequestCallback[] = [];
    vi.stubGlobal(
      "requestAnimationFrame",
      vi.fn((cb: FrameRequestCallback) => {
        rafCallbacks.push(cb);
        return rafCallbacks.length;
      }),
    );
    const renderer = buildSpectrogramLiveRenderer();
    try {
      const freqs = logFreqs(64);
      for (let i = 0; i < 5; i += 1) {
        renderer.pushSpectrumColumn(
          freqs,
          freqs.map(() => -50),
        );
      }
      expect(globalThis.requestAnimationFrame).toHaveBeenCalledTimes(1);
      // Кадр отработал — следующий push планирует новый кадр.
      for (const cb of rafCallbacks.splice(0)) cb(16);
      renderer.pushSpectrumColumn(
        freqs,
        freqs.map(() => -50),
      );
      expect(globalThis.requestAnimationFrame).toHaveBeenCalledTimes(2);
    } finally {
      renderer.dispose();
    }
  });

  it("dispose отменяет кадр, отключает observer и снимает sheet", () => {
    const cancel = vi.fn();
    vi.stubGlobal("cancelAnimationFrame", cancel);
    vi.stubGlobal(
      "requestAnimationFrame",
      vi.fn(() => 7),
    );
    const adoptedCount = document.adoptedStyleSheets?.length ?? 0;
    const renderer = buildSpectrogramLiveRenderer();
    const freqs = logFreqs(64);
    renderer.pushSpectrumColumn(
      freqs,
      freqs.map(() => -50),
    );
    renderer.dispose();
    expect(cancel).toHaveBeenCalledWith(7);
    expect(document.adoptedStyleSheets?.length ?? 0).toBeLessThanOrEqual(adoptedCount);
    // После dispose push не планирует кадры.
    renderer.pushSpectrumColumn(
      freqs,
      freqs.map(() => -50),
    );
    expect(globalThis.requestAnimationFrame).toHaveBeenCalledTimes(1);
  });

  it("readout сохраняет формат витрины: частота · секунды · дБ", () => {
    const renderer = buildSpectrogramLiveRenderer();
    try {
      document.body.append(renderer.host);
      const canvas = renderer.host.querySelector("[data-spectrogram-canvas]") as HTMLCanvasElement;
      const readout = renderer.bar.querySelector("[data-spectrogram-readout]") as HTMLElement;
      vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 400, 200));
      const freqs = logFreqs(64);
      renderer.pushSpectrumColumn(
        freqs,
        freqs.map(() => -50),
      );
      canvas.dispatchEvent(new MouseEvent("mousemove", { clientX: 200, clientY: 100 }));
      expect(readout.textContent).toContain("дБ");
      expect(readout.textContent).toContain("с ·");
      expect(readout.textContent).toContain("Гц");
    } finally {
      renderer.dispose();
    }
  });

  it("селекторы и палитра витрины сохранены", () => {
    const renderer = buildSpectrogramLiveRenderer();
    try {
      expect(renderer.host.querySelector("[data-spectrogram-canvas]")).not.toBeNull();
      expect(renderer.bar.querySelector("[data-spectrogram-readout]")).not.toBeNull();
      expect(renderer.bar.querySelector("[data-spectrogram-scale]")).not.toBeNull();
      expect(renderer.bar.querySelector('[data-spectrogram-mode="delta"]')).not.toBeNull();
      renderer.setMode("delta");
      expect(renderer.getMode()).toBe("delta");
    } finally {
      renderer.dispose();
    }
  });
});

describe("poller: poll-решения", () => {
  it("live: running/capturing с written — поллить последнюю сессию", () => {
    expect(pickLiveSessionName(runningSnap(["cap-001", "cap-002"]))).toBe("cap-002");
  });

  it("live: running без written — не поллить", () => {
    expect(pickLiveSessionName(runningSnap([]))).toBeNull();
    expect(pickLiveSessionName(null)).toBeNull();
  });

  it("live: терминальный снимок — не поллить", () => {
    expect(pickLiveSessionName(doneSnap(["cap-001"]))).toBeNull();
  });

  it("fallback: idle с завершённой сессией — последняя", () => {
    expect(pickFallbackSessionName(doneSnap(["cap-001", "cap-002"]))).toBe("cap-002");
    expect(pickFallbackSessionName(runningSnap(["cap-001"]))).toBeNull();
    expect(pickFallbackSessionName(null)).toBeNull();
    expect(pickFallbackSessionName(doneSnap([]))).toBeNull();
  });

  it("toDbColumn: линейная PSD в дБ, неположительная — пол −120", () => {
    expect(toDbColumn([1e-6, 0, -5, Number.NaN])).toEqual([-60, -120, -120, -120]);
  });
});

describe("poller: тиканье каждые ~1500мс", () => {
  it("активная задача поллит спектр последней written_session", async () => {
    vi.useFakeTimers();
    const spectrum = vi.fn(async () => ({
      frequency_hz: logFreqs(32),
      psd_v2_per_hz: logFreqs(32).map(() => 1e-6),
      point_count: 32,
    }));
    const onColumn = vi.fn();
    const poller = createLivePoller(
      { spectrum },
      { onColumn, onSession: () => undefined, onEmpty: () => undefined },
    );
    try {
      poller.notifySnapshot(runningSnap(["cap-007"]));
      expect(LIVE_POLL_MS).toBe(1500);
      await vi.advanceTimersByTimeAsync(1600);
      expect(spectrum).toHaveBeenCalledWith("cap-007", expect.any(Number));
      expect(onColumn).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(1500);
      expect(onColumn).toHaveBeenCalledTimes(2);
    } finally {
      poller.dispose();
    }
  });

  it("смена сессии переключает опрос на новую", async () => {
    vi.useFakeTimers();
    const spectrum = vi.fn(async (name: string) => ({
      frequency_hz: logFreqs(32),
      psd_v2_per_hz: logFreqs(32).map(() => 1e-6),
      point_count: 32,
      name,
    }));
    const poller = createLivePoller(
      { spectrum: spectrum as never },
      { onColumn: () => undefined, onSession: () => undefined, onEmpty: () => undefined },
    );
    try {
      poller.notifySnapshot(runningSnap(["cap-001"]));
      await vi.advanceTimersByTimeAsync(1600);
      poller.notifySnapshot(runningSnap(["cap-001", "cap-002"]));
      await vi.advanceTimersByTimeAsync(1600);
      const names = spectrum.mock.calls.map((call) => call[0]);
      expect(names).toContain("cap-002");
    } finally {
      poller.dispose();
    }
  });

  it("завершение останавливает опрос и показывает fallback один раз", async () => {
    vi.useFakeTimers();
    const spectrum = vi.fn(async () => ({
      frequency_hz: logFreqs(32),
      psd_v2_per_hz: logFreqs(32).map(() => 1e-6),
      point_count: 32,
    }));
    const onSession = vi.fn();
    const poller = createLivePoller(
      { spectrum },
      { onColumn: () => undefined, onSession, onEmpty: () => undefined },
    );
    try {
      poller.notifySnapshot(runningSnap(["cap-001"]));
      await vi.advanceTimersByTimeAsync(1600);
      const callsAfterLive = spectrum.mock.calls.length;
      poller.notifySnapshot(doneSnap(["cap-001"]));
      await vi.advanceTimersByTimeAsync(5000);
      // Post-hoc fallback: ровно одна догрузка, периодический опрос остановлен.
      expect(spectrum.mock.calls.length).toBe(callsAfterLive + 1);
      expect(onSession).toHaveBeenLastCalledWith("cap-001", "fallback");
    } finally {
      poller.dispose();
    }
  });

  it("нет данных — пустое состояние, без fetch", async () => {
    vi.useFakeTimers();
    const spectrum = vi.fn(async () => ({
      frequency_hz: [],
      psd_v2_per_hz: [],
      point_count: 0,
    }));
    const onEmpty = vi.fn();
    const poller = createLivePoller(
      { spectrum },
      { onColumn: () => undefined, onSession: () => undefined, onEmpty },
    );
    try {
      poller.notifySnapshot(null);
      await vi.advanceTimersByTimeAsync(5000);
      expect(spectrum).not.toHaveBeenCalled();
      expect(onEmpty).toHaveBeenCalled();
    } finally {
      poller.dispose();
    }
  });
});

describe("panel: section.panel и жизненный цикл", () => {
  function stubPlots() {
    return {
      spectrum: vi.fn(async () => ({
        frequency_hz: logFreqs(64),
        psd_v2_per_hz: logFreqs(64).map(() => 1e-6),
        point_count: 64,
      })),
    };
  }

  it("панель — section.panel с V6-классами и пустым состоянием", () => {
    const panel = createSpectrogramLivePanel({ plots: stubPlots() });
    try {
      expect(panel.root.tagName).toBe("SECTION");
      expect(panel.root.classList.contains("panel")).toBe(true);
      expect(panel.root.querySelector("[data-live-spectrogram]")).not.toBeNull();
      expect(panel.root.querySelector(".panel-title")).not.toBeNull();
      expect(panel.root.querySelector("[data-livegram-empty]")).not.toBeNull();
      expect(panel.root.querySelector("[data-spectrogram-canvas]")).not.toBeNull();
    } finally {
      panel.dispose();
      panel.root.remove();
    }
  });

  it("fallback-сессия скрывает пустое состояние и подписывает сессию", async () => {
    vi.useRealTimers();
    const panel = createSpectrogramLivePanel({ plots: stubPlots() });
    try {
      document.body.append(panel.root);
      panel.onSnapshot(doneSnap(["sim-003"]));
      await vi.waitFor(() => {
        expect(panel.root.querySelector("[data-livegram-empty]")?.hasAttribute("hidden")).toBe(
          true,
        );
      });
      expect(panel.root.querySelector("[data-livegram-session]")?.textContent).toContain("sim-003");
    } finally {
      panel.dispose();
      panel.root.remove();
    }
  });

  it("dispose панели останавливает опрос и renderer", () => {
    const plots = stubPlots();
    const panel = createSpectrogramLivePanel({ plots });
    panel.onSnapshot(runningSnap(["cap-001"]));
    panel.dispose();
    panel.root.remove();
    expect(plots.spectrum).not.toHaveBeenCalled();
  });
});
