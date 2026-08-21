import { describe, expect, it } from "vitest";
import { LntApiClient } from "./client";
import { ApiError } from "./errors";

const CONFIG_A = {
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
  static_assets: { app: "/static/app.hash-a.js" },
};

const CONTEXT_S1 = {
  session_id: "s1",
  revision: 1,
  health: "ok",
  reason_codes: [],
  fields: {},
  tags: [],
  notes: null,
};

type FetchCall = { url: string; init: RequestInit | undefined };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Fake fetch with a programmable route table and call recording. */
function makeFetch(
  handler: (
    url: string,
    init: RequestInit | undefined,
    call: number,
  ) => Response | Promise<Response>,
): { fetch: typeof fetch; calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  const impl = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    calls.push({ url, init });
    return handler(url, init, calls.length);
  };
  return { fetch: impl as unknown as typeof fetch, calls };
}

describe("LntApiClient", () => {
  it("bootstrap stores build id and nonce from /api/config", async () => {
    const { fetch } = makeFetch(() => jsonResponse(CONFIG_A));
    const client = new LntApiClient(fetch);
    const cfg = await client.bootstrap();
    expect(cfg.build_id).toBe("build-a");
    expect(client.currentBuildId).toBe("build-a");
    expect(client.currentNonce).toBe("nonce-a");
  });

  it("mutations send the X-LNT-Mutation-Nonce header from bootstrap", async () => {
    const { fetch, calls } = makeFetch((url) => {
      if (url === "/api/config") return jsonResponse(CONFIG_A);
      return jsonResponse(CONTEXT_S1);
    });
    const client = new LntApiClient(fetch);
    await client.bootstrap();
    await client.updateContext("s1", { expected_revision: 1, notes: "x" });
    const mutation = calls[calls.length - 1];
    expect(mutation?.init?.method).toBe("PUT");
    const headers = new Headers(mutation?.init?.headers);
    expect(headers.get("X-LNT-Mutation-Nonce")).toBe("nonce-a");
  });

  it("mutation without bootstrap fails deterministically in Russian", async () => {
    const { fetch } = makeFetch(() => jsonResponse(CONTEXT_S1));
    const client = new LntApiClient(fetch);
    const err = await client.updateContext("s1", { expected_revision: 0 }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("uninitialized");
    expect((err as ApiError).message).toContain("инициализир");
  });

  it("wrong build id is detected and recover() re-syncs identity", async () => {
    let serverBuild = "build-a";
    const serverNonce = "nonce-a";
    const { fetch } = makeFetch((url) => {
      if (url === "/api/health") return jsonResponse({ status: "ok", build_id: serverBuild });
      if (url === "/api/config")
        return jsonResponse({ ...CONFIG_A, build_id: serverBuild, mutation_nonce: serverNonce });
      return jsonResponse(CONTEXT_S1);
    });
    const client = new LntApiClient(fetch);
    await client.bootstrap();
    serverBuild = "build-b";
    await expect(client.verifyBuild()).rejects.toMatchObject({
      kind: "build_mismatch",
    });
    await expect(client.verifyBuild()).rejects.toThrow(/перезагруз|устарел/i);
    // Deterministic recovery: re-bootstrap picks up the new build.
    await client.recover();
    expect(client.currentBuildId).toBe("build-b");
    await expect(client.verifyBuild()).resolves.toBeUndefined();
  });

  it("server restart invalidates nonce; recover() restores mutations", async () => {
    let nonce = "nonce-old";
    const { fetch } = makeFetch((url) => {
      if (url === "/api/config") return jsonResponse({ ...CONFIG_A, mutation_nonce: nonce });
      if (url.startsWith("/api/context")) {
        if (nonce === "nonce-old") {
          return jsonResponse(
            { code: "mutation_nonce_invalid", detail: "неверный одноразовый nonce запуска" },
            403,
          );
        }
        return jsonResponse(CONTEXT_S1);
      }
      throw new Error(`unexpected url ${url}`);
    });
    const client = new LntApiClient(fetch);
    await client.bootstrap();
    const failure = await client
      .updateContext("s1", { expected_revision: 1 })
      .catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).kind).toBe("server_restart");
    expect((failure as ApiError).message).toContain("перезапущен");
    // Server restarted: config now issues a fresh nonce.
    nonce = "nonce-new";
    await client.recover();
    expect(client.currentNonce).toBe("nonce-new");
    await expect(client.updateContext("s1", { expected_revision: 1 })).resolves.toMatchObject({
      session_id: "s1",
    });
  });

  it("409 conflict maps to a Russian conflict error with status", async () => {
    const { fetch } = makeFetch((url) => {
      if (url === "/api/config") return jsonResponse(CONFIG_A);
      return jsonResponse({ detail: { detail: "revision conflict", current_revision: 4 } }, 409);
    });
    const client = new LntApiClient(fetch);
    await client.bootstrap();
    const err = await client.updateContext("s1", { expected_revision: 1 }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("conflict");
    expect((err as ApiError).status).toBe(409);
    expect((err as ApiError).message.length).toBeGreaterThan(0);
  });

  it("network failure produces a Russian network error", async () => {
    const broken = async (): Promise<Response> => {
      throw new TypeError("fetch failed");
    };
    const client = new LntApiClient(broken as unknown as typeof fetch);
    const err = await client.health().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("network");
    expect((err as ApiError).message).toContain("связ");
  });

  it("malformed JSON body produces a Russian parse error", async () => {
    const bad = async (): Promise<Response> =>
      new Response("{not json", { status: 200, headers: { "Content-Type": "application/json" } });
    const client = new LntApiClient(bad as unknown as typeof fetch);
    const err = await client.health().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("parse");
    expect((err as ApiError).message).toContain("ответ");
  });

  it("aborted requests surface as AbortError for stale-response control", async () => {
    const aborting = (_url: RequestInfo | URL, init?: RequestInit): Promise<Response> =>
      new Promise((_resolve, reject) => {
        const fail = (): void => {
          reject(new DOMException("aborted", "AbortError"));
        };
        if (init?.signal?.aborted) {
          fail();
          return;
        }
        init?.signal?.addEventListener("abort", fail);
      }) as Promise<Response>;
    const client = new LntApiClient(aborting as unknown as typeof fetch);
    const ctrl = new AbortController();
    ctrl.abort();
    await expect(client.context("s1", { signal: ctrl.signal })).rejects.toMatchObject({
      name: "AbortError",
    });
  });

  it("catalogSessions serializes query filters into the URL", async () => {
    const { fetch, calls } = makeFetch((url) => {
      if (url === "/api/config") return jsonResponse(CONFIG_A);
      return jsonResponse({ items: [], next_cursor: null });
    });
    const client = new LntApiClient(fetch);
    await client.catalogSessions({
      health: "ok",
      label: "kit",
      page_size: 25,
      include_paths: true,
    });
    const url = new URL(calls[0]?.url ?? "", "http://127.0.0.1");
    expect(url.pathname + url.search).toBe(
      "/api/catalog/sessions?health=ok&label=kit&page_size=25&include_paths=true",
    );
  });
});
