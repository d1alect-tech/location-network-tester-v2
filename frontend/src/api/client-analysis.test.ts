import { describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "./client";
import { createAnalysisApi } from "./client-analysis";
import { ApiError } from "./errors";

describe("AnalysisApi recipes", () => {
  it("accepts the StoredRecipe payload where recipe_id is the only identity", async () => {
    const recipeId = "a".repeat(64);
    const client = {
      requestJson: vi.fn(async () => ({
        items: [{ recipe_id: recipeId, name: "Базовый", recipe: { mode: "spectrum" } }],
      })),
    } as unknown as LntApiClient;

    await expect(createAnalysisApi(client).recipes()).resolves.toEqual([
      { recipe_id: recipeId, name: "Базовый", recipe: { mode: "spectrum" } },
    ]);
  });

  it("rejects a recipe without its canonical recipe_id", async () => {
    const client = {
      requestJson: vi.fn(async () => ({ items: [{ name: "Базовый", recipe: {} }] })),
    } as unknown as LntApiClient;

    await expect(createAnalysisApi(client).recipes()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("AnalysisApi extended run", () => {
  const snapshot = {
    job_id: "a".repeat(32),
    kind: "analyze",
    status: "succeeded",
    stage: "done",
    completed: 1,
    total: 1,
    artifact_key: "b".repeat(64),
    error: null,
  };

  it("posts the run request with mutation and returns the snapshot", async () => {
    const requestJson = vi.fn(async () => snapshot);
    const client = { requestJson } as unknown as LntApiClient;
    const request = { session: "s1", recipe_id: "c".repeat(64) };

    await expect(createAnalysisApi(client).runAnalysis(request)).resolves.toEqual(snapshot);
    expect(requestJson).toHaveBeenCalledWith("POST", "/api/analysis/runs", request, {
      mutation: true,
    });
  });

  it("reads the run status snapshot", async () => {
    const requestJson = vi.fn(async () => snapshot);
    const client = { requestJson } as unknown as LntApiClient;

    await expect(createAnalysisApi(client).runStatus("a".repeat(32))).resolves.toEqual(snapshot);
  });

  it("rejects a malformed run snapshot", async () => {
    const client = {
      requestJson: vi.fn(async () => ({ job_id: 7 })),
    } as unknown as LntApiClient;

    await expect(
      createAnalysisApi(client).runAnalysis({ session: "s1", recipe_id: "c".repeat(64) }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
