/** C1: trendResultPanel — описательная маркировка трендов байт-в-байт
 * как в trendView.ts (RED: модулей пока нет). */
import { describe, expect, it } from "vitest";
import type { TrendAnalysisResult } from "../../api/types-research";
import { formatTrendValue, renderTrendResult } from "./trendResultPanel";

function result(overrides: Record<string, unknown> = {}): TrendAnalysisResult {
  return {
    normalized_timestamps: [],
    metadata: { units: "В", estimator: "mean", n: 8, provenance: {} },
    data_quality: {
      input_count: 10,
      missing_timestamp_count: 1,
      duplicate_count: 0,
      dedupe_policy: "first",
    },
    trends: [
      { group_dimension: "condition", group_value: "A", n: 4, mean: 1.234567 },
      { group_dimension: "condition", group_value: "B", n: 4, mean: null },
    ],
    ...overrides,
  };
}

describe("formatTrendValue", () => {
  it("formats finite numbers with 4 decimals, missing as «недоступно»", () => {
    expect(formatTrendValue(1.234567)).toBe("1.2346");
    expect(formatTrendValue(null)).toBe("недоступно");
    expect(formatTrendValue(undefined)).toBe("недоступно");
    expect(formatTrendValue(Number.NaN)).toBe("недоступно");
    expect(formatTrendValue(Number.POSITIVE_INFINITY)).toBe("недоступно");
  });
});

describe("renderTrendResult", () => {
  it("keeps the descriptive grid, group means and limitation texts verbatim", () => {
    const confound = document.createElement("section");
    const nodes = renderTrendResult(result(), 3, confound);
    const text = nodes.map((node) => node.textContent ?? "").join("\n");

    expect(text).toContain("Достаточно данных для описательной сводки.");
    expect(text).toContain("Единицы");
    expect(text).toContain("Рецепт (estimator)");
    expect(text).toContain("mean · описательный");
    expect(text).toContain("N пригодных наблюдений");
    expect(text).toContain("Входных наблюдений");
    expect(text).toContain("Пропусков времени");
    expect(text).toContain("Дубликатов (политика)");
    expect(text).toContain("0 · first");
    expect(text).toContain("Средние по группам (описательные)");
    expect(text).toContain("condition=A: N=4, среднее 1.2346 В (описательное, exploratory)");
    expect(text).toContain("condition=B: N=4, среднее недоступно В (описательное, exploratory)");
    expect(text).toContain("Маркировка результата");
    expect(text).toContain(
      "Описательный разведочный анализ (exploratory). Единицы: В · N=8. Ранговые связи — корреляции, НЕ причинные эффекты.",
    );
    expect(text).toContain(
      "Недостающие данные показаны как «недоступно» с кодом причины и никогда не восполняются вымыслом.",
    );
  });

  it("places the confound node between the group means and the limitations", () => {
    const confound = document.createElement("section");
    confound.textContent = "confound-marker";
    const nodes = renderTrendResult(result(), 3, confound);

    expect(nodes.length).toBe(6);
    expect(nodes[4]).toBe(confound);
    expect(nodes[2]?.textContent).toContain("Средние по группам");
    expect(nodes[5]?.textContent).toContain("Маркировка результата");
  });

  it("marks small-n results as limited with a warn banner", () => {
    const confound = document.createElement("section");
    const small = result({ metadata: { units: "В", estimator: "mean", n: 2, provenance: {} } });
    const nodes = renderTrendResult(small, 3, confound);

    expect(nodes[0]?.textContent).toContain(
      "Мало данных: результат ограничен, интерпретация неустойчива.",
    );
    expect(nodes[0]?.className).toContain("lnt-exp-banner-warn");
  });

  it("omits the data-quality rows when the envelope has none", () => {
    const confound = document.createElement("section");
    const bare: TrendAnalysisResult = {
      normalized_timestamps: [],
      metadata: { units: "В", estimator: "mean", n: 8, provenance: {} },
      trends: [],
    };
    const nodes = renderTrendResult(bare, 3, confound);
    const grid = nodes[1];
    expect(grid?.querySelectorAll("dt").length).toBe(3);
  });
});
