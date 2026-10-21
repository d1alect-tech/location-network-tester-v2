/** RED-first контракт панели: загрузка/готово/недоступно/404/409,
 * фиксированные слоты значений и отсутствие подмены чисел фоном. */

import { afterEach, describe, expect, it } from "vitest";
import { RippleApiError } from "../../../api/client-ripple";
import type { RippleApi } from "../../../api/client-ripple";
import type { RippleArtifactPayload, RippleBaseline } from "../../../api/types-ripple";
import type { ChartHandle, ChartRenderRequest } from "../../../components/charts/types";
import { type RipplePanelHandle, createRipplePanel } from "./ripplePanel";

const hex64 = (char: string): string => char.repeat(64);

function artifact(): RippleArtifactPayload {
  return {
    schema_version: 1,
    algorithm: { id: "ripple_observed_v1", version: 1, rms: "population_centered_float64" },
    options: { band_low_hz: 1, band_high_hz: 500, interval_window_s: 1 },
    session: {
      session_id: "sess-a",
      manifest_sha256: hex64("f"),
      ch1_sha256: hex64("e"),
      channel: "ch1",
      source: "synthetic",
    },
    provenance: {
      capture_metadata_basis: "legacy_capture_metadata_not_adapter_provenance",
      operator_attachment: "preconnected_no_reconnection",
      voltage_plane: "synthetic_mathematical_volts",
      range_code: 1,
      probe_multiplier: 1,
      calibration_used: null,
      calibration_identity: null,
      hardware_qualification: "unverified",
    },
    adapter: {
      topology_id: "series_c_at_dut_tip_x1_v1",
      cap_nf: 100,
      series_r_ohm: 0,
      rin_ohm: 1_000_000,
      probe_multiplier: 1,
      component_values_basis: "nominal",
      rail_nominal_v: 12,
      fc_hz: 1.5915494309189535,
      tau_s: 0.1,
      plateau_gain: 1,
      transfer_status: "nominal_transfer_declared",
      assumption_codes: ["one_pole_nominal_transfer"],
    },
    selection: {
      sample_start_index: 10_000,
      sample_end_index_exclusive: 40_000,
      sample_count: 30_000,
      sample_rate_hz: 10_000,
      realized_duration_s: 3,
      excluded_prefix_samples: 10_000,
      settling_prefix_samples_nominal: 10_000,
      settling_basis: "capture_start_assuming_preconnected",
      continuity_status: "synthetic_exact",
      continuity_reason_codes: [],
    },
    qc: {
      clipping_assessment: "not_applicable_synthetic",
      clip_count_scope: null,
      clip_low_count: null,
      clip_high_count: null,
      nonfinite_count: 0,
      nonfinite_count_scope: "selected_span",
      record_nonfinite_count: 0,
      dropped_samples: 0,
      reason_codes: [],
    },
    time_domain: {
      availability: "available",
      reason_codes: [],
      mean_v: 0.000005173322720890401,
      rms_ac_v: 0.002117531120011638,
      vpp_v: 0.021350678987801075,
    },
    intervals: [
      {
        start_index: 10_000,
        end_index_exclusive: 20_000,
        sample_count: 10_000,
        complete: true,
        realized_duration_s: 1,
        availability: "available",
        reason_codes: [],
        clip_low_count: 0,
        clip_high_count: 0,
        mean_v: 0.000020597415163263122,
        rms_ac_v: 0.002106871774681803,
        vpp_v: 0.019981898367404938,
      },
    ],
    spectrum: {
      availability: "available",
      reason_codes: [],
      settings: {
        nperseg: 10_000,
        overlap_fraction: 0.5,
        window: "hann",
        detector: "mean",
        resolution_hz: 1,
        enbw_hz: 1.5,
        segment_count: 5,
      },
      used_sample_count: 30_000,
      ignored_tail_samples: 0,
      frequency_hz: [0, 1, 2],
      psd_v2_per_hz: [7.40658967308813e-11, 5.662041868960643e-10, 3.6018572984358953e-10],
      asd_v_per_sqrt_hz: [8.605e-6, 2.379e-5, 1.898e-5],
    },
    bands: [
      {
        id: "ripple",
        low_hz: 1,
        high_hz: 500,
        first_center_hz: 1,
        last_center_hz: 500,
        bin_count: 500,
        availability: "available",
        reason_codes: [],
        rms_v: 0.0006369719075516393,
      },
    ],
    baseline: null,
  };
}

type FakeView = ChartHandle & { readonly requests: ChartRenderRequest[] };

function fakeView(): (options: { container: HTMLElement }) => FakeView {
  return (options) => {
    const root = document.createElement("div");
    options.container.append(root);
    const requests: ChartRenderRequest[] = [];
    return {
      root,
      requests,
      render(request) {
        requests.push(request);
      },
      applyTheme() {},
      getData: () => null,
      destroy() {},
    };
  };
}

function apiOf(
  handler: (
    session: string,
    options?: { readonly signal?: AbortSignal },
  ) => Promise<RippleArtifactPayload>,
): RippleApi {
  return { artifact: handler };
}

const cleanups: Array<() => void> = [];

function mount(api: RippleApi | null): { panel: RipplePanelHandle; view: FakeView } {
  const container = document.createElement("div");
  document.body.append(container);
  const createView = fakeView();
  let view: FakeView | null = null;
  const panel = createRipplePanel({
    api,
    createView: (options) => {
      view = createView(options);
      return view;
    },
  });
  container.append(panel.root);
  cleanups.push(() => panel.destroy());
  if (view === null) throw new Error("chart view not created");
  return { panel, view };
}

function metricValue(root: HTMLElement, key: string): string | null {
  return root.querySelector(`[data-metric="${key}"]`)?.getAttribute("data-value") ?? null;
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  document.body.replaceChildren();
});

describe("createRipplePanel", () => {
  it("готовый артефакт: сырые байты в data-value, текст по формату", async () => {
    const { panel } = mount(apiOf(async () => artifact()));
    await panel.setPair("sess-a");
    expect(panel.root.dataset.state).toBe("ready");
    expect(panel.root.dataset.availability).toBe("available");
    expect(metricValue(panel.root, "mean")).toBe("0.000005173322720890401");
    expect(metricValue(panel.root, "rms-ac")).toBe("0.002117531120011638");
    expect(metricValue(panel.root, "vpp")).toBe("0.021350678987801075");
    expect(metricValue(panel.root, "band")).toBe("0.0006369719075516393");
    expect(panel.root.querySelector('[data-metric="rms-ac"] .ripple-card-value')?.textContent).toBe(
      "2,12\u00A0мВ",
    );
  });

  it("спектр рисуется из сохранённых байтов, тумблер ASD меняет представление", async () => {
    const { panel, view } = mount(apiOf(async () => artifact()));
    await panel.setPair("sess-a");
    expect(view.requests).toHaveLength(1);
    expect(view.requests[0]?.series[0]?.values[0]).toBeCloseTo(
      10 * Math.log10(5.662041868960643e-10),
      12,
    );
    const asd = panel.root.querySelector('[data-ripple-mode="asd"]') as HTMLButtonElement;
    asd.click();
    expect(asd.getAttribute("aria-pressed")).toBe("true");
    expect(view.requests).toHaveLength(2);
    expect(view.requests[1]?.yLog).toBe(true);
  });

  it("недоступная ветка: н/д + причина, никаких нулей", async () => {
    const payload = artifact();
    payload.time_domain = {
      availability: "unavailable",
      reason_codes: ["clipping_unknown"],
      mean_v: null,
      rms_ac_v: null,
      vpp_v: null,
    };
    const { panel } = mount(apiOf(async () => payload));
    await panel.setPair("sess-a");
    expect(panel.root.dataset.state).toBe("ready");
    expect(panel.root.dataset.availability).toBe("unavailable");
    for (const key of ["mean", "rms-ac", "vpp"]) {
      expect(metricValue(panel.root, key)).toBe("null");
      expect(
        panel.root.querySelector(`[data-metric="${key}"] .ripple-card-value`)?.textContent,
      ).toBe("н/д");
      expect(panel.root.querySelector(`[data-metric="${key}"]`)?.getAttribute("title")).toBe(
        "клиппинг не определён",
      );
    }
  });

  it("при смене сессии старые числа не остаются на экране", async () => {
    const deferred: { resolve?: (value: RippleArtifactPayload) => void } = {};
    const api = apiOf(async (session) => {
      if (session === "slow") {
        return await new Promise<RippleArtifactPayload>((resolve) => {
          deferred.resolve = resolve;
        });
      }
      return artifact();
    });
    const { panel } = mount(api);
    await panel.setPair("sess-a");
    expect(metricValue(panel.root, "mean")).not.toBe("null");
    const pending = panel.setPair("slow");
    expect(panel.root.dataset.state).toBe("loading");
    expect(metricValue(panel.root, "mean")).toBe("null");
    expect(panel.root.querySelector('[data-metric="mean"] .ripple-card-value')?.textContent).toBe(
      "н/д",
    );
    deferred.resolve?.(artifact());
    await pending;
    expect(panel.root.dataset.state).toBe("ready");
  });

  it("404 not_built — честная причина, без выдуманного артефакта", async () => {
    const { panel } = mount(
      apiOf(async () => {
        throw new RippleApiError("not_built", { status: 404 });
      }),
    );
    await panel.setPair("sess-a");
    expect(panel.root.dataset.state).toBe("error");
    expect(panel.root.dataset.error).toBe("not_built");
    const message = panel.root.querySelector('[data-role="ripple-message"]')?.textContent ?? "";
    expect(message).toContain("не построен");
    expect(metricValue(panel.root, "mean")).toBe("null");
  });

  it("409 stale_input — машинный код в data-reason и причиной в тексте", async () => {
    const { panel } = mount(
      apiOf(async () => {
        throw new RippleApiError("conflict", { status: 409, reason: "stale_input" });
      }),
    );
    await panel.setPair("sess-a");
    expect(panel.root.dataset.state).toBe("error");
    expect(panel.root.dataset.error).toBe("conflict");
    expect(panel.root.dataset.reason).toBe("stale_input");
    const message = panel.root.querySelector('[data-role="ripple-message"]')?.textContent ?? "";
    expect(message).toContain("входные файлы изменились");
    expect(message).toContain("stale_input");
  });

  it("409 без машинной причины не подменяет причину догадкой", async () => {
    const { panel } = mount(
      apiOf(async () => {
        throw new RippleApiError("conflict", { status: 409 });
      }),
    );
    await panel.setPair("sess-a");
    expect(panel.root.dataset.reason).toBe("");
    const message = panel.root.querySelector('[data-role="ripple-message"]')?.textContent ?? "";
    expect(message).toContain("причина не указана сервером");
  });

  it("сетевой отказ — сообщение, а не пустой экран", async () => {
    const { panel } = mount(
      apiOf(async () => {
        throw new RippleApiError("network");
      }),
    );
    await panel.setPair("sess-a");
    expect(panel.root.dataset.error).toBe("network");
    expect(panel.root.textContent).toContain("Нет связи");
  });

  it("abort прошлой загрузки не оставляет ошибку и не перетирает новую", async () => {
    const api = apiOf(async (session, options) => {
      if (session === "slow") {
        return await new Promise<RippleArtifactPayload>((_resolve, reject) => {
          options?.signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          });
        });
      }
      return artifact();
    });
    const { panel } = mount(api);
    const slow = panel.setPair("slow");
    await panel.setPair("sess-a");
    await slow;
    expect(panel.root.dataset.state).toBe("ready");
    expect(panel.root.dataset.error).toBe("");
  });

  it("единственная сохранённая полоса — селектор не показывается", async () => {
    const { panel } = mount(apiOf(async () => artifact()));
    await panel.setPair("sess-a");
    const select = panel.root.querySelector<HTMLSelectElement>("[data-ripple-band]");
    expect(select?.hidden).toBe(true);
  });

  it("несколько сохранённых полос — выбор только из них, без пересчёта", async () => {
    const payload = artifact();
    payload.bands.push({
      ...payload.bands[0]!,
      id: "wide",
      low_hz: 10,
      high_hz: 2000,
      rms_v: 0.001,
    });
    let calls = 0;
    const { panel } = mount(
      apiOf(async () => {
        calls += 1;
        return payload;
      }),
    );
    await panel.setPair("sess-a");
    const select = panel.root.querySelector<HTMLSelectElement>("[data-ripple-band]");
    expect(select?.hidden).toBe(false);
    expect(select?.options).toHaveLength(2);
    select!.value = "wide";
    select!.dispatchEvent(new Event("change"));
    expect(metricValue(panel.root, "band")).toBe("0.001");
    expect(calls).toBe(1);
  });

  it("фон рядом: свои числа и статус сравнения, измерение не подменяется", async () => {
    const payload = artifact();
    const baseline: RippleBaseline = {
      session: {
        session_id: "bg",
        manifest_sha256: hex64("a"),
        ch1_sha256: hex64("b"),
        channel: "ch1",
        source: "synthetic",
      },
      attachment_basis: "same_adapter_tip_shorted_to_return",
      comparison_status: "unavailable",
      reason_codes: ["baseline_incompatible"],
      selection: null,
      time_domain: {
        availability: "available",
        reason_codes: [],
        mean_v: 0,
        rms_ac_v: 0.001,
        vpp_v: 0.003,
      },
      spectrum: {
        availability: "unavailable",
        reason_codes: ["baseline_incompatible"],
        settings: {},
        used_sample_count: null,
        ignored_tail_samples: null,
        frequency_hz: [],
        psd_v2_per_hz: [],
        asd_v_per_sqrt_hz: [],
      },
      bands: [],
    };
    payload.baseline = baseline;
    const { panel } = mount(apiOf(async () => payload));
    await panel.setPair("sess-a");
    expect(panel.root.querySelector("[data-baseline-status]")?.textContent).toContain("недоступно");
    expect(panel.root.querySelector("[data-baseline-rms]")?.textContent).toBe("1,00\u00A0мВ");
    expect(panel.root.querySelector("[data-baseline-vpp]")?.textContent).toBe("3,00\u00A0мВ");
    expect(metricValue(panel.root, "rms-ac")).toBe("0.002117531120011638");
  });

  it("без API панель честно говорит об отсутствии клиента", async () => {
    const { panel } = mount(null);
    await panel.setPair("sess-a");
    expect(panel.root.dataset.state).toBe("error");
    expect(panel.root.dataset.error).toBe("unavailable");
    expect(panel.root.textContent).toContain("Клиент ripple недоступен");
  });
});
