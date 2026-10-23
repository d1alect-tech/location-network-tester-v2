/** D1: ошибка SSE-транспорта гасит числа живого чипа риппла до следующего
 * ripple-события текущей эпохи. Сам реконнект и heartbeat числа не
 * возвращают.
 * GAP-6 (task 8): композиция доносит маркер базиса компонент адаптера и
 * постоянную подсказку номинальной модели до чипа без изменений провода. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveRipplePayload, LiveStatePayload } from "../../api/types-live";
import { mountScopeRippleReadout } from "./scopeRippleReadout";

const ADAPTER = {
  topology_id: "series_c_at_dut_tip_x1_v1",
  cap_nf: 100,
  series_r_ohm: 0,
  probe_multiplier: 1,
  component_values_basis: "nominal",
  hardware_qualification: "unverified",
  transfer_status: "nominal_transfer_declared",
  rail_nominal_v: null,
  tau_s: 0.1,
  fc_hz: 1.5915,
  settling_s: 1,
  settle_samples: 8000,
  assumption_codes: ["one_pole_nominal_transfer", "settling_policy_10_tau"],
};

const READY: LiveRipplePayload = {
  status: "ready",
  reason_codes: [],
  epoch_id: 1,
  config_id: "cfg1",
  continuity_id: 1,
  continuity_basis: "host_contiguous_unverified",
  gap_count: 0,
  block_count: 3,
  dropped_blocks: 0,
  dropped_samples: 0,
  samples_received: 12_000,
  sample_progress: 12_000,
  ring_capacity_samples: 524_288,
  ring_sample_count: 4000,
  ring_limited: false,
  settle_samples: 8000,
  settled: true,
  startup_discard_samples: 0,
  settling_basis: "capture_start_assuming_preconnected",
  settling_remaining_samples: 0,
  excluded_prefix_samples: 8000,
  span_start_sample: 8000,
  span_sample_count: 4000,
  span_duration_s: 0.5,
  mean_v: 0.0012,
  rms_ac_v: 0.0354,
  vpp_v: 0.1,
  clipped_low: 0,
  clipped_high: 0,
  clip_count_scope: "current_span",
  sample_rate_hz: 8000,
  ch1_range_v: 5,
  ch1_probe_multiplier: 1,
  calibration_used: false,
  voltage_label: "некалиброванные вольты",
  adapter: { ...ADAPTER },
};

const RUNNING: LiveStatePayload = {
  state: "running",
  mode: "sim",
  busy_reason: null,
  trigger: null,
};

/** Минимальный EventSource: те же onopen/onerror/close и именованные события,
 * что использует client-live. */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private readonly handlers = new Map<string, Array<(event: { data: string }) => void>>();

  constructor(public readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: { data: string }) => void): void {
    const list = this.handlers.get(type) ?? [];
    list.push(handler);
    this.handlers.set(type, list);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: unknown): void {
    for (const handler of [...(this.handlers.get(type) ?? [])]) {
      handler({ data: JSON.stringify(data) });
    }
  }
}

function textOf(root: HTMLElement, attr: string): string {
  const node = root.querySelector<HTMLElement>(`[${attr}]`);
  return node?.textContent ?? "";
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeEventSource.instances = [];
});

describe("живой чип риппла: маркер базиса компонент (GAP-6)", () => {
  it("readout доносит базис и подсказку модели до чипа", () => {
    const readout = mountScopeRippleReadout();
    readout.applyLiveState(RUNNING);
    readout.applyRipple(READY);
    expect(textOf(readout.rippleRow, "data-ripple-basis")).toBe("номинал");
    readout.applyRipple({
      ...READY,
      adapter: { ...ADAPTER, component_values_basis: "operator_measured" },
    });
    expect(textOf(readout.rippleRow, "data-ripple-basis")).toBe("измерено оператором");
    expect(textOf(readout.rippleRow, "data-ripple-model-hint")).toBe(
      "живые числа используют номинальную модель адаптера",
    );
    readout.dispose();
  });
});

describe("живой чип риппла при ошибке транспорта", () => {
  it("source.onerror гасит числа; onopen и heartbeat их не возвращают", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const readout = mountScopeRippleReadout();
    const api = createLiveApi(
      new LntApiClient(async () => new Response("unused", { status: 500 })),
    );
    const stream = api.watchFrames(
      {
        onRipple: readout.applyRipple,
        onState: readout.applyLiveState,
        onConnection: readout.setConnection,
      },
      {
        setTimeoutFn: () => 1,
        clearTimeoutFn: () => undefined,
      },
    );

    // Живая эпоха: переход в running, затем готовый снимок с числами.
    readout.applyLiveState(RUNNING);
    const source = FakeEventSource.instances.at(-1);
    source?.onopen?.();
    source?.emit("ripple", READY);
    expect(textOf(readout.rippleRow, "data-ripple-state")).toBe("готов");
    expect(textOf(readout.rippleRow, "data-ripple-rms")).toBe("35.4 мВ");
    expect(textOf(readout.rippleRow, "data-ripple-vpp")).toBe("100.0 мВ");
    expect(textOf(readout.rippleRow, "data-ripple-window")).toBe("500 мс");

    source?.onerror?.();
    expect(textOf(readout.rippleRow, "data-ripple-rms")).toBe("—");
    expect(textOf(readout.rippleRow, "data-ripple-vpp")).toBe("—");
    expect(textOf(readout.rippleRow, "data-ripple-window")).toBe("—");

    // Реконнект и heartbeat не обновляют возраст риппла: числа остаются пустыми.
    source?.onopen?.();
    source?.emit("heartbeat", RUNNING);
    expect(textOf(readout.rippleRow, "data-ripple-rms")).toBe("—");
    expect(textOf(readout.rippleRow, "data-ripple-vpp")).toBe("—");
    expect(textOf(readout.rippleRow, "data-ripple-window")).toBe("—");

    // Следующее ripple-событие текущей эпохи возвращает числа.
    source?.emit("ripple", READY);
    expect(textOf(readout.rippleRow, "data-ripple-state")).toBe("готов");
    expect(textOf(readout.rippleRow, "data-ripple-rms")).toBe("35.4 мВ");
    expect(textOf(readout.rippleRow, "data-ripple-vpp")).toBe("100.0 мВ");
    expect(textOf(readout.rippleRow, "data-ripple-window")).toBe("500 мс");

    stream.close();
    readout.dispose();
  });
});
