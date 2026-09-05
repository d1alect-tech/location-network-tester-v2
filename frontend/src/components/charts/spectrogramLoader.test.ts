/** C2: загрузчик артефакта спектрограммы — лист spectrogramLoader. */

import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/errors";
import { createSpectrogramArtifactLoader } from "./spectrogramLoader";

function abortError(): Error {
  const error = new Error("aborted");
  error.name = "AbortError";
  return error;
}

describe("загрузчик артефакта спектрограммы", () => {
  const emptyInventory = (): import("../../api/types-analysis").EventInventoryPayload => ({
    schema_version: 1,
    sample_count: 0,
    events: [],
  });
  it("hides the banner and resets status when a load starts", async () => {
    const hideError = vi.fn();
    const resetStatus = vi.fn();
    const loader = createSpectrogramArtifactLoader({
      client: {
        analysis: {
          artifactBytes: async () => new ArrayBuffer(0),
          events: async () => emptyInventory(),
          recipes: async () => [],
        },
      },
      showError: () => undefined,
      hideError,
      resetStatus,
      applyInitialTile: () => Promise.resolve(),
    });
    // Пустой NPZ упадёт в разбор, но стартовая пара уже вызвана.
    await loader.load("s", "k").catch(() => undefined);
    expect(hideError).toHaveBeenCalledTimes(1);
    expect(resetStatus).toHaveBeenCalledTimes(1);
    loader.dispose();
  });

  it("shows a not-found banner with working retry on 404", async () => {
    let bytesCalls = 0;
    const showError = vi.fn();
    const loader = createSpectrogramArtifactLoader({
      client: {
        analysis: {
          artifactBytes: async (): Promise<ArrayBuffer> => {
            bytesCalls += 1;
            throw new ApiError("http", { status: 404 });
          },
          events: async () => {
            throw new ApiError("http", { status: 404 });
          },
          recipes: async () => [],
        },
      },
      showError,
      hideError: () => undefined,
      resetStatus: () => undefined,
      applyInitialTile: () => Promise.resolve(),
    });
    await loader.load("capture-001", "art-missing");
    expect(showError).toHaveBeenCalledTimes(1);
    expect(String(showError.mock.calls[0]?.[0])).toMatch(/не найден/i);
    const retry = showError.mock.calls[0]?.[1] as (() => void) | undefined;
    expect(typeof retry).toBe("function");
    const before = bytesCalls;
    expect(before).toBeGreaterThan(0);
    (retry as () => void)();
    await Promise.resolve();
    await Promise.resolve();
    expect(bytesCalls).toBeGreaterThan(before);
    loader.dispose();
  });

  it("keeps true aborts silent", async () => {
    const showError = vi.fn();
    const loader = createSpectrogramArtifactLoader({
      client: {
        analysis: {
          artifactBytes: async (): Promise<ArrayBuffer> => {
            throw abortError();
          },
          events: async (): Promise<never> => {
            throw abortError();
          },
          recipes: async () => [],
        },
      },
      showError,
      hideError: () => undefined,
      resetStatus: () => undefined,
      applyInitialTile: () => Promise.resolve(),
    });
    await loader.load("s", "k");
    expect(showError).not.toHaveBeenCalled();
    loader.dispose();
  });

  it("surfaces non-404 failures through the banner idiom", async () => {
    const showError = vi.fn();
    const loader = createSpectrogramArtifactLoader({
      client: {
        analysis: {
          artifactBytes: async (): Promise<ArrayBuffer> => {
            throw new Error("offline");
          },
          events: async () => {
            throw new Error("offline");
          },
          recipes: async () => [],
        },
      },
      showError,
      hideError: () => undefined,
      resetStatus: () => undefined,
      applyInitialTile: () => Promise.resolve(),
    });
    await loader.load("s", "k");
    expect(showError).toHaveBeenCalledWith("offline");
    loader.dispose();
  });
});
