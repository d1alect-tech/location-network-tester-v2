/** V6 RED-контракты раздела «Отчёты» (TDD RED, T2) — test-side зеркало
 * reports.spec.ts. Эталон: kit.css (панели .panel/.panel-hd/.panel-title/
 * .panel-bd). Падение — только по missing class. Числа свои (golden гипотез
 * не касаемся). Зелёный пин: provenance и единицы в превью. */

import { describe, expect, it } from "vitest";
import type { ReportDraft, ReportEffectNumbers } from "./views/reports/reportModel";
import { composeReportMarkdown } from "./views/reports/reportModel";
import { previewBlock } from "./views/reports/reportPreview";

function draft(): ReportDraft {
  return {
    title: "Синтетика exp.rep.demo",
    provenance: {
      experiment_id: "exp.rep.demo",
      experiment_revision: 2,
      estimand: "band_mid_total",
      job_id: "job-3",
      generated_at: "2026-08-22T10:00:00Z",
    },
    core: {
      units: "В²/Гц",
      sampling_unit: "measurement_session",
      hierarchy: ["site", "unit"],
      n: 6,
      missing_count: 0,
      exclusions: [],
      estimator: "qualified_within_run_contrast",
      interval_method: "seeded_block_bootstrap_percentile_95",
    },
    outcome: {
      kind: "effect",
      effect: {
        mean_effect: 2.5,
        median_effect: 2.4,
        robust_effect: 2.45,
        interval_low: 2.1,
        interval_high: 2.9,
        confidence_level: 0.95,
      },
      drift: null,
    },
    planes: [{ session_id: "s1", available: true, reason_code: null, model_kind: "rc_shunt_v1" }],
    recipes: [{ recipe_id: "rec-1", name: "Базовый спектр", sha256: "a".repeat(64) }],
    limitations: [],
  };
}

describe("отчёты V6: стек панелей", () => {
  it("превью — стек section.panel с .panel-title", () => {
    // Given / When
    const preview = previewBlock(draft());

    // Then: V6-стек панелей kit.css (§5.2: hairline-стыки)
    const panels = preview.querySelectorAll("section.panel");
    expect(
      panels.length > 0,
      "V6-разрыв: превью без section.panel (сейчас div.lnt-rep-preview + h3)",
    ).toBe(true);
    for (const panel of panels) {
      expect(
        panel.querySelector(".panel-title"),
        "V6-разрыв: панель превью без .panel-title",
      ).not.toBeNull();
      expect(
        panel.querySelector(".panel-bd"),
        "V6-разрыв: панель превью без .panel-bd",
      ).not.toBeNull();
    }
  });
});

describe("отчёты V6: md-блок", () => {
  it("превью содержит .md-блок с тем же markdown, что выгрузка", () => {
    // Given
    const data = draft();
    const markdown = composeReportMarkdown(data);
    expect(markdown.length > 0, "markdown выгрузки непустой").toBe(true);

    // When
    const preview = previewBlock(data);

    // Then: V6 md-блок — превью показывает ровно тот текст, что уйдёт в .md
    const md = preview.querySelector(".md");
    expect(md, "V6-разрыв: в превью нет .md-блока с текстом выгрузки").not.toBeNull();
    expect(md?.textContent).toContain("exp.rep.demo");
  });
});

describe("отчёты V6: тоны баннеров результата", () => {
  it("descriptive — info-баннер с role=status", () => {
    // Given: описательный исход без интервала
    const data = {
      ...draft(),
      outcome: {
        kind: "descriptive",
        effect: (draft().outcome as { effect: ReportEffectNumbers }).effect,
      },
    } as ReportDraft;

    // When
    const preview = previewBlock(data);

    // Then: инфо-тон объявлен статусом, не алёртом
    const info = preview.querySelector(".lnt-rep-banner-info");
    expect(info, "нет .lnt-rep-banner-info для descriptive-исхода").not.toBeNull();
    expect(info?.getAttribute("role")).toBe("status");
    expect(info?.textContent).toContain("Описательная оценка");
  });

  it("refusal — warn-баннер с role=alert", () => {
    // Given: бэкенд заблокировал расчёт
    const data = {
      ...draft(),
      outcome: { kind: "refusal", reason_code: "no_data" },
    } as ReportDraft;

    // When
    const preview = previewBlock(data);

    // Then: блокировка — алёрт
    const warn = preview.querySelector(".lnt-rep-banner-warn");
    expect(warn, "нет .lnt-rep-banner-warn для refusal-исхода").not.toBeNull();
    expect(warn?.getAttribute("role")).toBe("alert");
  });
});

describe("отчёты V6: пины (уже зелёные)", () => {
  it("provenance, единицы и N на месте", () => {
    // Given / When
    const preview = previewBlock(draft());

    // Then: контракты превью стабильны под портированием
    expect(preview.textContent).toContain("exp.rep.demo");
    expect(preview.textContent).toContain("В²/Гц");
    expect(preview.textContent).toContain("Плоскости измерения");
  });
});
