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
