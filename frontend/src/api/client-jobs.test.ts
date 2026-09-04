import { describe, expect, it } from "vitest";
import { LntApiClient } from "./client";
import { ApiError } from "./errors";

const CONFIG = {
  root: "C:/lnt-sessions",
  profiles: ["bad"],
  defaults: {
    simulate: { duration_s: 2.4, sample_rate_hz: 500000, seed: 6022, repeat: 1, interval_s: 0 },
    capture: { duration_s: 2.4, sample_rate_hz: 1000000, range_v: 5, repeat: 1, interval_s: 0 },
    ranges: [5],
  },
  build_id: "build-a",
  mutation_nonce: "nonce-a",
  static_asset_hash: "hash-a",
  static_assets: {},
};

const SNAPSHOT = {
  schema_version: 1,
  version: 1,
  job_id: "job-1",
  kind: "simulate",
  status: "queued",
  stage: "queued",
  series_index: null,
  series_total: null,
  written_sessions: [],
  result: null,
  error_code: null,
  error_message: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Fake fetch с таблицей маршрутов и записью вызовов. */
function makeFetch(
  handler: (url: string, init: RequestInit | undefined) => Response | Promise<Response>,
): { fetch: typeof fetch; calls: { url: string; init: RequestInit | undefined }[] } {
  const calls: { url: string; init: RequestInit | undefined }[] = [];
  const impl = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    calls.push({ url, init });
    return handler(url, init);
  };
  return { fetch: impl as unknown as typeof fetch, calls };
}

async function bootstrappedClient(
  handler: (url: string, init: RequestInit | undefined) => Response | Promise<Response>,
): Promise<{ client: LntApiClient; calls: { url: string; init: RequestInit | undefined }[] }> {
  const { fetch, calls } = makeFetch((url, init) => {
    if (url === "/api/config") return jsonResponse(CONFIG);
    return handler(url, init);
  });
  const client = new LntApiClient(fetch);
  await client.bootstrap();
  return { client, calls };
}

describe("JobsApi", () => {
  it("start posts the discriminated request with the launch nonce", async () => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/jobs" ? jsonResponse(SNAPSHOT, 202) : new Response("{}", { status: 404 }),
    );
    const snapshot = await client.jobs.start({ kind: "selftest" });
    expect(snapshot.job_id).toBe("job-1");
    const call = calls[1];
    expect(call?.init?.method).toBe("POST");
    expect(new Headers(call?.init?.headers).get("X-LNT-Mutation-Nonce")).toBe("nonce-a");
    expect(JSON.parse(String(call?.init?.body))).toEqual({ kind: "selftest" });
  });

  it("get encodes the job id into the path", async () => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/jobs/abc%20x" ? jsonResponse(SNAPSHOT) : new Response("{}", { status: 404 }),
    );
    await client.jobs.get("abc x");
    expect(calls[1]?.url).toBe("/api/jobs/abc%20x");
  });

  it("list serializes page_size and offset", async () => {
    const { client, calls } = await bootstrappedClient((url) => {
      if (url === "/api/jobs?page_size=25&offset=5") return jsonResponse({ items: [SNAPSHOT] });
      return new Response("{}", { status: 404 });
    });
    const page = await client.jobs.list(25, 5);
    expect(page.items).toHaveLength(1);
    expect(calls[1]?.url).toBe("/api/jobs?page_size=25&offset=5");
  });

  it("history serializes bounded replay parameters", async () => {
    const { client, calls } = await bootstrappedClient((url) => {
      if (url === "/api/jobs/job-1/history?page_size=10&after_version=3") {
        return jsonResponse({ items: [SNAPSHOT] });
      }
      return new Response("{}", { status: 404 });
    });
    await client.jobs.history("job-1", 10, 3);
    expect(calls[1]?.url).toBe("/api/jobs/job-1/history?page_size=10&after_version=3");
  });

  it("cancel posts with the launch nonce", async () => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/jobs/job-1/cancel"
        ? jsonResponse({ ...SNAPSHOT, status: "cancelling" }, 202)
        : new Response("{}", { status: 404 }),
    );
    const snapshot = await client.jobs.cancel("job-1");
    expect(snapshot.status).toBe("cancelling");
    expect(new Headers(calls[1]?.init?.headers).get("X-LNT-Mutation-Nonce")).toBe("nonce-a");
  });

  it("rejects malformed snapshots with a typed parse error", async () => {
    const { client } = await bootstrappedClient(() => jsonResponse({ job_id: 42 }));
    const err = await client.jobs.get("job-1").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("parse");
  });
});

describe("PlotsApi", () => {
  it("detail returns the guarded session envelope", async () => {
    const detail = {
      name: "s1",
      manifest: { schema_version: 1 },
      analysis: null,
      spectrum_available: true,
      waveform_available: true,
      ch2_available: false,
    };
    const { client } = await bootstrappedClient((url) =>
      url === "/api/sessions/s1" ? jsonResponse(detail) : new Response("{}", { status: 404 }),
    );
    const payload = await client.plots.detail("s1");
    expect(payload.spectrum_available).toBe(true);
    expect(payload.manifest).toEqual({ schema_version: 1 });
  });

  it("spectrum serializes max_points", async () => {
    const spectrum = { frequency_hz: [1], psd_v2_per_hz: [2], point_count: 1 };
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/sessions/s1/spectrum?max_points=2000"
        ? jsonResponse(spectrum)
        : new Response("{}", { status: 404 }),
    );
    await client.plots.spectrum("s1", 2_000);
    expect(calls[1]?.url).toBe("/api/sessions/s1/spectrum?max_points=2000");
  });

  it("spectrumInputReferred hits the input-referred endpoint with guards", async () => {
    const referred = {
      frequency_hz: [1],
      input_referred_excess_psd_v2_per_hz: [2],
      point_count: 1,
      status: "available",
      reason_code: null,
      qualified_bin_count: 1,
      total_bin_count: 1,
      resolution_hz: 100,
    };
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/sessions/s1/spectrum-input-referred?max_points=2000"
        ? jsonResponse(referred)
        : new Response("{}", { status: 404 }),
    );
    const payload = await client.plots.spectrumInputReferred("s1", 2_000);
    expect(calls[1]?.url).toBe("/api/sessions/s1/spectrum-input-referred?max_points=2000");
    expect(payload.resolution_hz).toBe(100);
  });

  it("waveform defaults to ch1 with the server default window", async () => {
    const waveform = { channel: "ch1", time_s: [0], voltage_v: [0], point_count: 1 };
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/sessions/s1/waveform?channel=ch1&max_points=4000"
        ? jsonResponse(waveform)
        : new Response("{}", { status: 404 }),
    );
    await client.plots.waveform("s1");
    expect(calls[1]?.url).toBe("/api/sessions/s1/waveform?channel=ch1&max_points=4000");
  });
});
