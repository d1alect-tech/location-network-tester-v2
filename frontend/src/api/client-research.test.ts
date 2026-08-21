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

const EXPERIMENT = { experiment_id: "exp-1", revision: 2 };
const RUN = { run_id: "run-1", status: "planned", revision: 1 };
const HYPOTHESIS = {
  schema_version: 1,
  hypothesis_id: "h1",
  revision: 1,
  statement: "s",
  mechanism: "m",
  status: "open",
  status_label: "Открыта",
};
const TREND = {
  slope: 0.1,
  normalized_timestamps: ["2026-01-01T00:00:00Z"],
  metadata: { units: "В", estimator: "descriptive_longitudinal", n: 5, provenance: {} },
};
const REPORT = { comparable: false, findings: [{ level: "blocking" }] };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

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

describe("ResearchApi experiments", () => {
  it("maps a cursor page and validates the experiment core field", async () => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/v2/experiments?page_size=25&cursor=Mg"
        ? jsonResponse({ items: [EXPERIMENT], next_cursor: null })
        : new Response("{}", { status: 404 }),
    );
    const page = await client.research.experiments(25, "Mg");
    expect(page.items[0]?.experiment_id).toBe("exp-1");
    expect(page.next_cursor).toBeNull();
    expect(calls[1]?.url).toBe("/api/v2/experiments?page_size=25&cursor=Mg");
  });

  it("createExperiment posts the write payload with the launch nonce", async () => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/v2/experiments"
        ? jsonResponse(EXPERIMENT, 201)
        : new Response("{}", { status: 404 }),
    );
    await client.research.createExperiment({
      experiment: { experiment_id: "exp-1" },
      expected_revision: 0,
    });
    const call = calls[1];
    expect(call?.init?.method).toBe("POST");
    expect(new Headers(call?.init?.headers).get("X-LNT-Mutation-Nonce")).toBe("nonce-a");
    expect(JSON.parse(String(call?.init?.body))).toEqual({
      experiment: { experiment_id: "exp-1" },
      expected_revision: 0,
    });
  });

  it("updateExperiment PUTs to the experiment path", async () => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/v2/experiments/exp-1"
        ? jsonResponse(EXPERIMENT)
        : new Response("{}", { status: 404 }),
    );
    await client.research.updateExperiment("exp-1", {
      experiment: { experiment_id: "exp-1" },
      expected_revision: 2,
    });
    expect(calls[1]?.init?.method).toBe("PUT");
  });

  it.each([
    [
      "/api/v2/experiments/exp-1/revisions?page_size=10",
      (c: LntApiClient) => c.research.revisions("exp-1", 10),
    ],
    [
      "/api/v2/experiments/exp-1/members?page_size=10",
      (c: LntApiClient) => c.research.members("exp-1", 10),
    ],
    [
      "/api/v2/experiments/exp-1/steps?page_size=10",
      (c: LntApiClient) => c.research.steps("exp-1", 10),
    ],
  ])("component pages hit %s", async (expectedUrl, act) => {
    const { client, calls } = await bootstrappedClient(() =>
      jsonResponse({ items: [], next_cursor: null }),
    );
    await act(client);
    expect(calls[1]?.url).toBe(expectedUrl);
  });

  it("rejects an envelope whose items lack the core id", async () => {
    const { client } = await bootstrappedClient(() =>
      jsonResponse({ items: [{ revision: 1 }], next_cursor: null }),
    );
    const err = await client.research.experiments().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("parse");
  });
});

describe("ResearchApi protocol runs", () => {
  it("startRun posts RunStart with the launch nonce and validates the record", async () => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/v2/experiments/exp-1/runs"
        ? jsonResponse(RUN, 201)
        : new Response("{}", { status: 404 }),
    );
    const record = await client.research.startRun("exp-1", {
      run_id: "run-1",
      mode: "simulator",
      seed: 7,
    });
    expect(record.run_id).toBe("run-1");
    expect(new Headers(calls[1]?.init?.headers).get("X-LNT-Mutation-Nonce")).toBe("nonce-a");
    expect(JSON.parse(String(calls[1]?.init?.body))).toEqual({
      run_id: "run-1",
      mode: "simulator",
      seed: 7,
    });
  });

  it.each([
    ["confirm", "/api/v2/protocol-runs/run-1/confirm"],
    ["resume", "/api/v2/protocol-runs/run-1/resume"],
    ["cancel", "/api/v2/protocol-runs/run-1/cancel"],
  ])("%s posts to %s with the nonce", async (_verb, expectedUrl) => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === expectedUrl ? jsonResponse(RUN, 202) : new Response("{}", { status: 404 }),
    );
    if (expectedUrl.endsWith("/confirm")) {
      await client.research.confirmRun("run-1", { actor: "user" });
    } else if (expectedUrl.endsWith("/resume")) {
      await client.research.resumeRun("run-1");
    } else {
      await client.research.cancelRun("run-1");
    }
    expect(calls[1]?.url).toBe(expectedUrl);
    expect(new Headers(calls[1]?.init?.headers).get("X-LNT-Mutation-Nonce")).toBe("nonce-a");
  });
});

describe("ResearchApi hypotheses and analysis", () => {
  it("hypotheses serializes the status alias filter", async () => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/v2/hypotheses?status=open"
        ? jsonResponse({ items: [HYPOTHESIS], next_cursor: null })
        : new Response("{}", { status: 404 }),
    );
    const page = await client.research.hypotheses({ status: "open" });
    expect(page.items[0]?.status_label).toBe("Открыта");
    expect(calls[1]?.url).toBe("/api/v2/hypotheses?status=open");
  });

  it("queryTrends posts observations and validates the result envelope", async () => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/v2/trends/query" ? jsonResponse(TREND) : new Response("{}", { status: 404 }),
    );
    const result = await client.research.queryTrends({
      units: "В",
      observations: [
        {
          observation_id: "o1",
          timestamp: null,
          source_offset: "a",
          location: "home",
          condition: "base",
          predictor: 1,
          outcome: 2,
          metadata: [],
        },
      ],
    });
    expect(result.metadata.estimator).toBe("descriptive_longitudinal");
    expect(result.normalized_timestamps).toHaveLength(1);
    expect(calls[1]?.init?.method).toBe("POST");
  });

  it("comparabilityCheck posts the pair and returns the guarded report", async () => {
    const { client, calls } = await bootstrappedClient((url) =>
      url === "/api/v2/comparability/check"
        ? jsonResponse(REPORT)
        : new Response("{}", { status: 404 }),
    );
    const report = await client.research.comparabilityCheck({
      left: { session_id: "a" },
      right: { session_id: "b" },
    });
    expect(report.comparable).toBe(false);
    expect(report.findings).toHaveLength(1);
    expect(JSON.parse(String(calls[1]?.init?.body))).toEqual({
      left: { session_id: "a" },
      right: { session_id: "b" },
    });
  });

  it("malformed trend envelopes surface as typed parse errors", async () => {
    const { client } = await bootstrappedClient(() =>
      jsonResponse({ normalized_timestamps: "not-a-list", metadata: {} }),
    );
    const err = await client.research
      .queryTrends({ units: "В", observations: [] })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("parse");
  });
});
