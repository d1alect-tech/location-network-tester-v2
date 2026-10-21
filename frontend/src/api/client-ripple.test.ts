/** Контракт ripple-клиента (routes_ripple.py): 200 → разобранный и
 * проверенный сайдкар; 404/409/422 → типизированные отказы с машинными
 * кодами причин; сетевые сбои и битые тела — тоже типизированы. */

import { describe, expect, it } from "vitest";
import { LntApiClient } from "./client";
import { RippleApiError, createRippleApi } from "./client-ripple";

const VALID_ARTIFACT = {
  schema_version: 1,
  algorithm: { id: "ripple_observed_v1", version: 1, rms: "population_centered_float64" },
  options: { band_low_hz: 99, band_high_hz: 101, interval_window_s: 1 },
  session: {
    session_id: "sess-alpha",
    manifest_sha256: "a".repeat(64),
    ch1_sha256: "b".repeat(64),
    channel: "ch1",
    source: "synthetic",
  },
  provenance: {
    capture_metadata_basis: "legacy_capture_metadata_not_adapter_provenance",
    operator_attachment: "preconnected_no_reconnection",
    voltage_plane: "synthetic_mathematical_volts",
    range_code: 10,
    probe_multiplier: 1,
    calibration_used: false,
    calibration_identity: "legacy_bit_identical_conversion",
    hardware_qualification: "unverified",
  },
  adapter: {
    topology_id: "series_c_at_dut_tip_x1_v1",
    cap_nf: 100,
    series_r_ohm: 0,
    rin_ohm: 1_000_000,
    probe_multiplier: 1,
    component_values_basis: "nominal",
    rail_nominal_v: null,
    fc_hz: 1.5915494309189535,
    tau_s: 0.1,
    plateau_gain: 1,
    transfer_status: "nominal_transfer_declared",
    assumption_codes: ["one_pole_nominal_transfer"],
  },
  selection: {
    sample_start_index: 10_000,
    sample_end_index_exclusive: 20_000,
    sample_count: 10_000,
    sample_rate_hz: 10_000,
    realized_duration_s: 1,
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
    mean_v: 0.5,
    rms_ac_v: 0.035355339059327,
    vpp_v: 0.09999990463256836,
  },
  intervals: [],
  spectrum: {
    availability: "available",
    reason_codes: [],
    settings: { nperseg: 10_000, segment_count: 1 },
    used_sample_count: 10_000,
    ignored_tail_samples: 0,
    frequency_hz: [0, 1],
    psd_v2_per_hz: [1e-10, 8.33e-4],
    asd_v_per_sqrt_hz: [1e-5, 0.0289],
  },
  bands: [
    {
      id: "ripple",
      low_hz: 99,
      high_hz: 101,
      first_center_hz: 99,
      last_center_hz: 101,
      bin_count: 3,
      availability: "available",
      reason_codes: [],
      rms_v: 0.035355339059327376,
    },
  ],
  baseline: null,
};

const VALID_JSON = JSON.stringify(VALID_ARTIFACT);

interface Call {
  url: string;
  init: RequestInit | undefined;
}

function json(body: unknown, status = 200): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(
  body: unknown,
  status = 200,
): { api: ReturnType<typeof createRippleApi>; calls: Call[] } {
  const calls: Call[] = [];
  const fetchStub = (async (input: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return json(body, status);
  }) as typeof fetch;
  return { api: createRippleApi(new LntApiClient(fetchStub)), calls };
}

/** Тело 200 с изменённым полем: нарушение типа/инварианта, а не схемы. */
function mutatedBody(mutate: (artifact: Record<string, unknown>) => void): string {
  const artifact = JSON.parse(VALID_JSON) as Record<string, unknown>;
  mutate(artifact);
  return JSON.stringify(artifact);
}

async function rejection(promise: Promise<unknown>): Promise<unknown> {
  return promise.then(
    () => new Error("ожидался отказ, получен ответ"),
    (error: unknown) => error,
  );
}

async function expectRippleError(promise: Promise<unknown>): Promise<RippleApiError> {
  const error = await rejection(promise);
  if (!(error instanceof RippleApiError)) {
    throw new Error(`ожидался RippleApiError, получен ${String(error)}`);
  }
  return error;
}

describe("createRippleApi: 200", () => {
  it("разбирает и проверяет сохранённый сайдкар", async () => {
    const { api, calls } = stubFetch(VALID_JSON);
    const artifact = await api.artifact("meas");
    expect(artifact.session.session_id).toBe("sess-alpha");
    expect(artifact.time_domain.rms_ac_v).toBeCloseTo(0.035355339059327, 15);
    expect(artifact.bands[0]?.rms_v).not.toBeNull();
    expect(artifact.baseline).toBeNull();
    expect(calls).toHaveLength(1);
    expect(calls[0]?.url).toBe("/api/sessions/meas/ripple");
    expect(calls[0]?.init?.method).toBe("GET");
  });

  it("кодирует идентификатор сессии в путь", async () => {
    const { api, calls } = stubFetch(VALID_JSON);
    await api.artifact("sess alpha");
    expect(calls[0]?.url).toBe("/api/sessions/sess%20alpha/ripple");
  });

  it("отбрасывает битую схему тела 200 как parse", async () => {
    const body = mutatedBody((artifact) => {
      const timeDomain = artifact.time_domain as Record<string, unknown>;
      timeDomain.mean_v = "0.5";
    });
    const { api } = stubFetch(body);
    const error = await expectRippleError(api.artifact("meas"));
    expect(error.kind).toBe("parse");
  });

  it("сохраняет null недоступных веток, не подменяя их значениями", async () => {
    const body = mutatedBody((artifact) => {
      artifact.time_domain = {
        availability: "unavailable",
        reason_codes: ["settling_unknown"],
        mean_v: null,
        rms_ac_v: null,
        vpp_v: null,
      };
      artifact.spectrum = {
        availability: "unavailable",
        reason_codes: ["settling_unknown"],
        settings: {},
        used_sample_count: null,
        ignored_tail_samples: null,
        frequency_hz: [],
        psd_v2_per_hz: [],
        asd_v_per_sqrt_hz: [],
      };
      artifact.bands = [
        {
          id: "ripple",
          low_hz: 99,
          high_hz: 101,
          first_center_hz: null,
          last_center_hz: null,
          bin_count: null,
          availability: "unavailable",
          reason_codes: ["settling_unknown"],
          rms_v: null,
        },
      ];
    });
    const { api } = stubFetch(body);
    const artifact = await api.artifact("meas");
    expect(artifact.time_domain.rms_ac_v).toBeNull();
    expect(artifact.time_domain.reason_codes).toEqual(["settling_unknown"]);
    expect(artifact.spectrum.frequency_hz).toEqual([]);
    expect(Object.keys(artifact.spectrum.settings)).toEqual([]);
    expect(artifact.bands[0]?.rms_v).toBeNull();
    expect(artifact.bands[0]?.low_hz).toBe(99);
  });

  it("не добавляет параметры запроса и заголовок мутации", async () => {
    const { api, calls } = stubFetch(VALID_JSON);
    await api.artifact("meas");
    expect(calls[0]?.url).not.toContain("?");
    expect(calls[0]?.init?.headers).toBeUndefined();
    expect(calls[0]?.init?.body).toBeUndefined();
  });

  it("отбрасывает не-JSON тело 200 как parse", async () => {
    const { api } = stubFetch("не JSON вовсе");
    const error = await expectRippleError(api.artifact("meas"));
    expect(error.kind).toBe("parse");
  });

  it("отбрасывает Infinity из 1e999 в теле 200 как parse", async () => {
    const inflated = VALID_JSON.replace('"band_low_hz":99', '"band_low_hz":1e999');
    const { api } = stubFetch(inflated);
    const error = await expectRippleError(api.artifact("meas"));
    expect(error.kind).toBe("parse");
  });
});

describe("createRippleApi: конверт ошибок", () => {
  it("404 с reason=not_built даёт kind=not_built", async () => {
    const { api } = stubFetch({ detail: "ripple-артефакт не построен", reason: "not_built" }, 404);
    const error = await expectRippleError(api.artifact("plain"));
    expect(error.kind).toBe("not_built");
    expect(error.status).toBe(404);
    expect(error.detail).toBe("ripple-артефакт не построен");
  });

  it("404 без reason даёт kind=not_found", async () => {
    const { api } = stubFetch({ detail: "сессия не найдена" }, 404);
    const error = await expectRippleError(api.artifact("ghost"));
    expect(error.kind).toBe("not_found");
    expect(error.status).toBe(404);
  });

  it.each(["corrupt", "schema_incompatible", "stale_input", "unsafe_sidecar"] as const)(
    "409 сохраняет машинную причину %s",
    async (reason) => {
      const { api } = stubFetch({ detail: "ripple.json не согласован", reason }, 409);
      const error = await expectRippleError(api.artifact("meas"));
      expect(error.kind).toBe("conflict");
      expect(error.status).toBe(409);
      expect(error.reason).toBe(reason);
      expect(error.detail).toBe("ripple.json не согласован");
    },
  );

  it("409 без reason (неоднозначность) даёт conflict без кода", async () => {
    const { api } = stubFetch({ detail: "идентификатор сессии неоднозначен" }, 409);
    const error = await expectRippleError(api.artifact("twin-id"));
    expect(error.kind).toBe("conflict");
    expect(error.reason).toBeUndefined();
  });

  it("422 даёт kind=invalid_request с серверным detail", async () => {
    const { api } = stubFetch({ detail: "GET ripple не принимает параметры запроса" }, 422);
    const error = await expectRippleError(api.artifact("meas"));
    expect(error.kind).toBe("invalid_request");
    expect(error.status).toBe(422);
    expect(error.detail).toBe("GET ripple не принимает параметры запроса");
  });

  it("неожиданный статус даёт kind=http", async () => {
    const { api } = stubFetch({ detail: "внутренняя ошибка" }, 500);
    const error = await expectRippleError(api.artifact("meas"));
    expect(error.kind).toBe("http");
    expect(error.status).toBe(500);
  });

  it("тело ошибки без JSON не ломает типизацию", async () => {
    const failing = (async () => new Response("<html>502</html>", { status: 502 })) as typeof fetch;
    const api = createRippleApi(new LntApiClient(failing));
    const error = await expectRippleError(api.artifact("meas"));
    expect(error.kind).toBe("http");
    expect(error.detail).toBeUndefined();
  });
});

describe("createRippleApi: сеть и отмена", () => {
  it("сетевой сбой даёт kind=network с исходной причиной", async () => {
    const failure = new TypeError("fetch failed");
    const offline = (async () => {
      throw failure;
    }) as typeof fetch;
    const api = createRippleApi(new LntApiClient(offline));
    const error = await expectRippleError(api.artifact("meas"));
    expect(error.kind).toBe("network");
    expect(error.cause).toBe(failure);
  });

  it("AbortError проходит насквозь без оборачивания", async () => {
    const abort = new DOMException("Aborted", "AbortError");
    const aborted = (async () => {
      throw abort;
    }) as typeof fetch;
    const api = createRippleApi(new LntApiClient(aborted));
    const error = await rejection(api.artifact("meas"));
    expect(error).toBe(abort);
  });

  it("передаёт AbortSignal в fetch", async () => {
    const calls: Array<RequestInit | undefined> = [];
    const recording = (async (_input: string | URL | Request, init?: RequestInit) => {
      calls.push(init);
      return json(VALID_JSON);
    }) as typeof fetch;
    const api = createRippleApi(new LntApiClient(recording));
    const controller = new AbortController();
    await api.artifact("meas", { signal: controller.signal });
    expect(calls[0]?.signal).toBe(controller.signal);
  });
});

describe("RippleApiError", () => {
  it("несёт имя, kind и русское сообщение по умолчанию", async () => {
    const { api } = stubFetch({ detail: "x", reason: "not_built" }, 404);
    const error = await expectRippleError(api.artifact("plain"));
    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("RippleApiError");
    expect(error.message.length).toBeGreaterThan(0);
  });
});
