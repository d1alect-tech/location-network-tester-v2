/** Todo 9 RED: живой чип риппла — состояния, честность чисел и свежесть.
 * Контракт события — models_ripple_live.py (строгая модель, числа только у
 * ready). Чип чит-only: ни одной кнопки, никакой математики на клиенте. */

import { describe, expect, it } from "vitest";
import type { LiveRipplePayload, LiveStatePayload } from "../../api/types-live";
import { mountScopeRippleChip } from "./scopeRippleChip";

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

function ripple(overrides: Partial<LiveRipplePayload>): LiveRipplePayload {
  return {
    status: "settling",
    reason_codes: ["settling_window"],
    epoch_id: 1,
    config_id: "cfg1",
    continuity_id: 1,
    continuity_basis: "host_contiguous_unverified",
    gap_count: 0,
    block_count: 3,
    dropped_blocks: 0,
    dropped_samples: 0,
    samples_received: 1000,
    sample_progress: 1000,
    ring_capacity_samples: 524_288,
    ring_sample_count: 1000,
    ring_limited: false,
    settle_samples: 8000,
    settled: false,
    startup_discard_samples: 0,
    settling_basis: "capture_start_assuming_preconnected",
    settling_remaining_samples: 7000,
    excluded_prefix_samples: 8000,
    span_start_sample: null,
    span_sample_count: 0,
    span_duration_s: null,
    mean_v: null,
    rms_ac_v: null,
    vpp_v: null,
    clipped_low: 0,
    clipped_high: 0,
    clip_count_scope: "current_span",
    sample_rate_hz: 8000,
    ch1_range_v: 5,
    ch1_probe_multiplier: 1,
    calibration_used: false,
    voltage_label: "некалиброванные вольты",
    adapter: { ...ADAPTER },
    ...overrides,
  };
}

const SETTLING = ripple({});
const READY = ripple({
  status: "ready",
  reason_codes: [],
  settled: true,
  settling_remaining_samples: 0,
  span_start_sample: 8000,
  span_sample_count: 4000,
  span_duration_s: 0.5,
  mean_v: 0.0012,
  rms_ac_v: 0.0354,
  vpp_v: 0.1,
  samples_received: 12_000,
  sample_progress: 12_000,
  ring_sample_count: 4000,
});
const UNAVAILABLE = ripple({
  status: "unavailable",
  reason_codes: ["insufficient_samples"],
  settle_samples: null,
  settling_basis: "settling_unknown",
  settling_remaining_samples: null,
  excluded_prefix_samples: null,
});
const STOPPED = ripple({
  status: "stopped",
  reason_codes: ["capture_stopped"],
  settled: true,
  settling_remaining_samples: 0,
  span_sample_count: 0,
  samples_received: 12_500,
  sample_progress: 12_500,
});

const RUNNING_STATE: LiveStatePayload = {
  state: "running",
  mode: "sim",
  busy_reason: null,
  trigger: null,
};

interface Timers {
  armed: Array<() => void>;
  cleared: unknown[];
}

function chipWithTimers(): { chip: ReturnType<typeof mountScopeRippleChip>; timers: Timers } {
  const timers: Timers = { armed: [], cleared: [] };
  const chip = mountScopeRippleChip({
    staleTimeoutMs: 2000,
    setTimeoutFn: (fn) => {
      timers.armed.push(fn);
      return timers.armed.length;
    },
    clearTimeoutFn: (handle) => {
      timers.cleared.push(handle);
    },
  });
  return { chip, timers };
}

function textOf(root: HTMLElement, attr: string): string {
  const node = root.querySelector<HTMLElement>(`[${attr}]`);
  return node?.textContent ?? "";
}

describe("scopeRippleChip (todo 9)", () => {
  it("нейтрален до первого события: прочерки, ярлык честности уже на месте", () => {
    const chip = mountScopeRippleChip();
    expect(textOf(chip.root, "data-ripple-state")).toBe("—");
    expect(textOf(chip.root, "data-ripple-progress")).toBe("—");
    expect(textOf(chip.root, "data-ripple-rms")).toBe("—");
    expect(textOf(chip.root, "data-ripple-vpp")).toBe("—");
    expect(textOf(chip.root, "data-ripple-window")).toBe("—");
    expect(textOf(chip.root, "data-ripple-adapter")).toBe("—");
    expect(textOf(chip.root, "data-ripple-label")).toContain("некалиброванные вольты");
    expect(chip.root.hasAttribute("data-readonly")).toBe(true);
  });

  it("settling без чисел: статус, прогресс установления, прочерки значений", () => {
    const chip = mountScopeRippleChip();
    chip.apply(SETTLING);
    expect(textOf(chip.root, "data-ripple-state")).toBe("установление");
    expect(textOf(chip.root, "data-ripple-progress")).toBe("осталось ~875 мс");
    expect(textOf(chip.root, "data-ripple-rms")).toBe("—");
    expect(textOf(chip.root, "data-ripple-vpp")).toBe("—");
    expect(textOf(chip.root, "data-ripple-window")).toBe("—");
  });

  it("ready показывает числа, окно, адаптер и ярлык", () => {
    const chip = mountScopeRippleChip();
    chip.apply(READY);
    expect(textOf(chip.root, "data-ripple-state")).toBe("готов");
    expect(textOf(chip.root, "data-ripple-rms")).toBe("35.4 мВ");
    expect(textOf(chip.root, "data-ripple-vpp")).toBe("100.0 мВ");
    expect(textOf(chip.root, "data-ripple-window")).toBe("500 мс");
    expect(textOf(chip.root, "data-ripple-adapter")).toBe("100 нФ · 0 Ом · ×1");
    expect(textOf(chip.root, "data-ripple-label")).toContain("полные отсчёты");
  });

  it("unavailable честно без чисел", () => {
    const chip = mountScopeRippleChip();
    chip.apply(UNAVAILABLE);
    expect(textOf(chip.root, "data-ripple-state")).toBe("недоступно");
    expect(textOf(chip.root, "data-ripple-rms")).toBe("—");
    expect(textOf(chip.root, "data-ripple-vpp")).toBe("—");
  });

  it("stopped чистит числа", () => {
    const chip = mountScopeRippleChip();
    chip.apply(READY);
    chip.apply(STOPPED);
    expect(textOf(chip.root, "data-ripple-state")).toBe("остановлен");
    expect(textOf(chip.root, "data-ripple-rms")).toBe("—");
    expect(textOf(chip.root, "data-ripple-vpp")).toBe("—");
  });

  it("freshness: только ready вооружает таймер; истечение гасит числа", () => {
    const { chip, timers } = chipWithTimers();
    chip.apply(SETTLING);
    expect(timers.armed).toHaveLength(0);
    chip.apply(READY);
    expect(timers.armed).toHaveLength(1);
    timers.armed[0]?.();
    expect(textOf(chip.root, "data-ripple-state")).toBe("нет данных");
    expect(textOf(chip.root, "data-ripple-rms")).toBe("—");
    expect(textOf(chip.root, "data-ripple-vpp")).toBe("—");
    // адаптер и ярлык остаются: провенанс не зависит от свежести чисел
    expect(textOf(chip.root, "data-ripple-adapter")).toBe("100 нФ · 0 Ом · ×1");
  });

  it("новое ready событие после устаревания возвращает числа и перевзводит таймер", () => {
    const { chip, timers } = chipWithTimers();
    chip.apply(READY);
    timers.armed[0]?.();
    chip.apply(READY);
    expect(textOf(chip.root, "data-ripple-state")).toBe("готов");
    expect(textOf(chip.root, "data-ripple-rms")).toBe("35.4 мВ");
    expect(timers.armed).toHaveLength(2);
  });

  it("heartbeat не продлевает свежесть: таймер один, числа гаснут без событий", () => {
    const { chip, timers } = chipWithTimers();
    // Монтаж при живом захвате: первый running — переход (сброс), затем события.
    chip.applyLiveState(RUNNING_STATE);
    chip.apply(READY);
    // Повторный running (heartbeat) не трогает чип и не перевзводит таймер.
    chip.applyLiveState(RUNNING_STATE);
    expect(timers.armed).toHaveLength(1);
    timers.armed[0]?.();
    chip.applyLiveState(RUNNING_STATE);
    expect(textOf(chip.root, "data-ripple-state")).toBe("нет данных");
    // адаптер и ярлык остаются: провенанс не зависит от свежести чисел
    expect(textOf(chip.root, "data-ripple-adapter")).toBe("100 нФ · 0 Ом · ×1");
  });

  it("битое событие (null) гасит числа", () => {
    const chip = mountScopeRippleChip();
    chip.apply(READY);
    chip.apply(null);
    expect(textOf(chip.root, "data-ripple-state")).toBe("нет данных");
    expect(textOf(chip.root, "data-ripple-rms")).toBe("—");
  });

  it("устаревшая эпоха отбрасывается: значения не откатываются", () => {
    const chip = mountScopeRippleChip();
    chip.apply(READY);
    chip.apply(
      ripple({
        epoch_id: 0,
        status: "ready",
        settled: true,
        settling_remaining_samples: 0,
        span_start_sample: 8000,
        span_sample_count: 4000,
        span_duration_s: 0.5,
        mean_v: -5,
        rms_ac_v: 9.9,
        vpp_v: 19.9,
      }),
    );
    expect(textOf(chip.root, "data-ripple-rms")).toBe("35.4 мВ");
  });

  it("регресс continuity_id и sample_progress отбрасывается", () => {
    const chip = mountScopeRippleChip();
    chip.apply(READY);
    chip.apply(ripple({ ...READY, continuity_id: 0 }));
    chip.apply(ripple({ ...READY, sample_progress: 11_000 }));
    expect(textOf(chip.root, "data-ripple-rms")).toBe("35.4 мВ");
    expect(textOf(chip.root, "data-ripple-state")).toBe("готов");
  });

  it("переход в running сбрасывает чип; повторный running (heartbeat) — нет", () => {
    const chip = mountScopeRippleChip();
    chip.apply(READY);
    chip.applyLiveState(RUNNING_STATE);
    expect(textOf(chip.root, "data-ripple-state")).toBe("—");
    expect(textOf(chip.root, "data-ripple-rms")).toBe("—");
    // Heartbeat с running не переход: числа живы.
    chip.apply(READY);
    chip.applyLiveState(RUNNING_STATE);
    expect(textOf(chip.root, "data-ripple-rms")).toBe("35.4 мВ");
  });

  it("stopped не вооружает таймер свежести", () => {
    const { chip, timers } = chipWithTimers();
    chip.apply(READY);
    chip.apply(STOPPED);
    expect(timers.armed).toHaveLength(1);
    expect(timers.cleared).toHaveLength(1);
  });

  it("dispose снимает таймер", () => {
    const { chip, timers } = chipWithTimers();
    chip.apply(READY);
    chip.dispose();
    expect(timers.cleared).toHaveLength(1);
  });
});
