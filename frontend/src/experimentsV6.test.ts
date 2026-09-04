/** V6 RED-контракты раздела «Эксперименты» (TDD RED, T2) — test-side зеркало
 * experiments.spec.ts. Эталон: kit.css (.tabbar/.snav-item/.cmdbar/.meter-grid/
 * .kpi) + variantV6.css (.pairbar/.banner-inline). Падение — только по missing
 * class. Golden-значения гипотез (1.9625/[1.6;2.3125]) НЕ трогаем: здесь свои
 * числа и ни одного импорта hypothesis-спеков. */

import { describe, expect, it } from "vitest";
import type { LntApiClient } from "./api/client";
import type { StatisticsMetadata } from "./api/types-research";
import { RouteStore } from "./state/routeState";
import { ComparisonView } from "./views/experiments/comparisonView";
import { ExperimentWizard } from "./views/experiments/experimentWizard";
import { mountExperimentsWorkspace } from "./views/experiments/experimentsWorkspace";
import { renderResultPanel } from "./views/experiments/resultPanel";

function stubClient(): LntApiClient {
  return {
    ensureReady: async () => undefined,
    catalogSessions: async () => ({ items: [], next_cursor: null }),
    research: { experiments: async () => ({ items: [] }) },
  } as unknown as LntApiClient;
}

function mountWorkspace(): { host: HTMLElement; routes: RouteStore; dispose: () => void } {
  const host = document.createElement("div");
  const routes = new RouteStore();
  const dispose = mountExperimentsWorkspace(host, { client: stubClient(), routes });
  return {
    host,
    routes,
    dispose: () => {
      dispose();
      routes.dispose();
      host.remove();
    },
  };
}

const METADATA = {
  units: "В²/Гц",
  n: 6,
  exclusions: [],
  missing_count: 0,
  estimator: "qualified_within_run_contrast",
  interval_method: "seeded_block_bootstrap_percentile_95",
  provenance: { experiment_id: "exp.demo", experiment_revision: 1, estimand: "band_mid_total" },
} as unknown as StatisticsMetadata;

describe("эксперименты V6: таббар и ленивые панели", () => {
  it("вкладки — .tabbar + .snav-item с aria-selected", () => {
    // Given
    const { host, dispose } = mountWorkspace();
    try {
      // Then: V6-таббар kit.css (активный — полоса ::before, как .snav-item.is-active)
      const tablist = host.querySelector('[role="tablist"]');
      expect(tablist, "должен быть tablist разделов").not.toBeNull();
      expect(
        tablist?.classList.contains("tabbar"),
        "V6-разрыв: tablist без .tabbar (сейчас .lnt-cat-tabs)",
      ).toBe(true);
      const tabs = tablist?.querySelectorAll('[role="tab"].snav-item') ?? [];
      expect(tabs.length, "V6-разрыв: табы без .snav-item (сейчас .lnt-btn.lnt-cat-tab)").toBe(4);
    } finally {
      dispose();
    }
  });

  it("панели вкладок — ленивые .panel (неактивные hidden)", () => {
    // Given
    const { host, dispose } = mountWorkspace();
    try {
      // Then: каждая панель — V6-панель, скрытые грузятся лениво
      const panes = host.querySelectorAll('[role="tabpanel"]');
      expect(panes.length).toBe(4);
      for (const pane of panes) {
        expect(
          pane.classList.contains("panel"),
          `V6-разрыв: панель «${pane.getAttribute("aria-label") ?? "?"}» без .panel`,
        ).toBe(true);
      }
      const hidden = [...panes].filter((pane) => (pane as HTMLElement).hidden);
      expect(hidden.length, "неактивные панели остаются hidden (ленивость)").toBe(3);
    } finally {
      dispose();
    }
  });
});

describe("эксперименты V6: сравнение — cmdbar, gate, pairbar", () => {
  function mountComparison(): { root: HTMLElement } {
    const view = new ComparisonView({
      client: {} as unknown as LntApiClient,
      valueSource: async () => null,
    });
    return { root: view.root };
  }

  it("панель сравнения — .cmdbar с полями и действиями", () => {
    // Given / When
    const { root } = mountComparison();

    // Then: V6-командная полоса (variantV6.css .cmdbar/.cmd-fields/.cmd-actions)
    expect(
      root.querySelector(".cmdbar"),
      "V6-разрыв: сравнение без .cmdbar (сейчас .lnt-exp-actions)",
    ).not.toBeNull();
  });

  it("гейт сравнимости — .comparability-gate блокирует расчёт с причиной", () => {
    // Given / When
    const { root } = mountComparison();

    // Then: гейт смешанных типов с точной причиной (контракт comparisonView)
    expect(
      root.querySelector(".comparability-gate"),
      "V6-разрыв: нет .comparability-gate (гейт смешанных типов)",
    ).not.toBeNull();
  });

  it("пара А—Б — .pairbar со слотами и дельтой", () => {
    // Given / When
    const { root } = mountComparison();

    // Then: полоса пары — главный объект V6 (variantV6.css .pairbar 40px)
    const pairbar = root.querySelector(".pairbar");
    expect(pairbar, "V6-разрыв: сравнение без .pairbar (полоса пары А—Б)").not.toBeNull();
    expect(pairbar?.querySelector(".pair-slot")).not.toBeNull();
  });
});

describe("эксперименты V6: результат — meter-grid/kpi", () => {
  it("панель результата — .meter-grid с .kpi и маркировкой", () => {
    // Given / When
    const root = renderResultPanel({
      title: "Контраст B−A",
      effect: { mean: 2.5, median: 2.4, robust: 2.45, intervalLow: 2.1, intervalHigh: 2.9 },
      metadata: METADATA,
    });

    // Then: V6-метрики kit.css (meter-grid + kpi-плитки, не слитная полоса)
    expect(
      root.querySelector(".meter-grid"),
      "V6-разрыв: результат без .meter-grid (сейчас dl.lnt-exp-result-grid)",
    ).not.toBeNull();
    expect(
      root.querySelector(".meter-grid .kpi, .kpi-tiles .kpi"),
      "V6-разрыв: в сетке метрик нет .kpi",
    ).not.toBeNull();
  });
});

describe("эксперименты V6: мастер — wizard-modal", () => {
  it("мастер создания — .wizard-modal диалог, а не плоская секция", () => {
    // Given / When
    const wizard = new ExperimentWizard({ client: stubClient(), onCreated: () => undefined });

    // Then: V6-модалка мастера (фокус-ловушка и Esc — задача портирования)
    expect(
      wizard.root.classList.contains("wizard-modal"),
      "V6-разрыв: мастер без .wizard-modal (сейчас section.lnt-exp-wizard)",
    ).toBe(true);
    expect(wizard.root.getAttribute("role")).toBe("dialog");
    wizard.root.remove();
  });
});

describe("эксперименты V6: пины (уже зелёные)", () => {
  it("четыре вкладки с tablist и seeded-протоколом по умолчанию", () => {
    // Given
    const { host, dispose } = mountWorkspace();
    try {
      // Then: структура вкладок стабильна под портированием
      const tabs = host.querySelectorAll('[role="tablist"] [role="tab"]');
      expect([...tabs].map((tab) => tab.textContent)).toEqual([
        "Обзор",
        "Сравнение",
        "Тренды",
        "Гипотезы",
      ]);
    } finally {
      dispose();
    }
  });
});
