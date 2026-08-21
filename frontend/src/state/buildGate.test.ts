import { describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import { createBuildGate } from "./buildGate";

/** Минимальная заглушка клиента: только поверхность, читаемая гейтом. */
interface GateClientOverrides {
  currentBuildId?: string;
  verifyBuild?: (...args: unknown[]) => unknown;
  recover?: (...args: unknown[]) => unknown;
}

function fakeClient(overrides: GateClientOverrides = {}): LntApiClient {
  const stub = {
    currentBuildId: "build-a",
    verifyBuild: vi.fn(),
    recover: vi.fn(),
    ...overrides,
  };
  return stub as unknown as LntApiClient;
}

describe("createBuildGate", () => {
  it("starts locked in the idle state", () => {
    const gate = createBuildGate(fakeClient());
    expect(gate.getState().kind).toBe("idle");
    expect(gate.isUnlocked()).toBe(false);
  });

  it("unlocks controls when the served build id matches", async () => {
    const gate = createBuildGate(fakeClient());
    await gate.verify();
    expect(gate.getState()).toMatchObject({ kind: "ready", buildId: "build-a" });
    expect(gate.isUnlocked()).toBe(true);
  });

  it("wrong build id produces a visible Russian recovery state and keeps controls locked", async () => {
    const gate = createBuildGate(
      fakeClient({
        verifyBuild: vi.fn().mockRejectedValue(new ApiError("build_mismatch")),
      }),
    );
    await gate.verify();
    const state = gate.getState();
    expect(state.kind).toBe("mismatch");
    if (state.kind === "mismatch") {
      expect(state.message).toMatch(/перезагруз|устарел/i);
    }
    expect(gate.isUnlocked()).toBe(false);
  });

  it("recover() re-syncs identity and unlocks controls deterministically", async () => {
    let mismatch = true;
    const gate = createBuildGate(
      fakeClient({
        verifyBuild: vi.fn(() =>
          mismatch ? Promise.reject(new ApiError("build_mismatch")) : Promise.resolve(),
        ),
        recover: vi.fn(async () => {
          mismatch = false;
          return undefined;
        }),
        currentBuildId: "build-b",
      }),
    );
    await gate.verify();
    expect(gate.isUnlocked()).toBe(false);
    await gate.recover();
    expect(gate.getState()).toMatchObject({ kind: "ready", buildId: "build-b" });
    expect(gate.isUnlocked()).toBe(true);
  });

  it("keeps the recovery state when the server still serves a different build", async () => {
    const gate = createBuildGate(
      fakeClient({
        verifyBuild: vi.fn().mockRejectedValue(new ApiError("build_mismatch")),
      }),
    );
    await gate.verify();
    await gate.recover();
    expect(gate.getState().kind).toBe("mismatch");
    expect(gate.isUnlocked()).toBe(false);
  });

  it("announces every state transition to subscribers", async () => {
    const gate = createBuildGate(fakeClient());
    const seen: string[] = [];
    gate.subscribe((state) => {
      seen.push(state.kind);
    });
    await gate.verify();
    expect(seen).toEqual(["verifying", "ready"]);
  });
});
