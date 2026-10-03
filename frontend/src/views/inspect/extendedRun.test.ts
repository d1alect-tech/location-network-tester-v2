import { describe, expect, it, vi } from "vitest";
import type { AnalysisRunSnapshot } from "../../api/types-analysis";
import {
  BUNDLE_FILES,
  EXTENDED_RECIPE_NAME,
  createExtendedRun,
  parseCharacterizationSummary,
} from "./extendedRun";
import type { ExtendedRunClient, ExtendedRunHandle } from "./extendedRun";

function snapshot(status: string, artifactKey: string | null): AnalysisRunSnapshot {
  return {
    job_id: "job-1",
    kind: "analysis",
    status,
    stage: "",
    completed: 1,
    total: 1,
    artifact_key: artifactKey,
    error: null,
  };
}

type FamilySpec = {
  readonly id: string;
  readonly status: string;
  /** Отсутствует ключ — payload без reason_codes (обратная совместимость). */
  readonly codes?: readonly string[];
};

function payloadOf(overrides: Readonly<Record<number, FamilySpec>>): unknown {
  return {
    families: Array.from({ length: 18 }, (_, index) => {
      const spec: FamilySpec = overrides[index] ?? {
        id: `f${String(index + 1).padStart(2, "0")}_other`,
        status: "unavailable",
      };
      return {
        family_id: spec.id,
        status: spec.status,
        comparison_summary: index === 0 ? [{ name: "f1_hz", value: 50.01, unit: "Hz" }] : [],
        ...(spec.codes === undefined ? {} : { reason_codes: [...spec.codes] }),
      };
    }),
  };
}

function summaryItems(handle: ExtendedRunHandle): readonly string[] {
  return Array.from(handle.root.querySelectorAll(".lnt-w1-failures li"), (node) =>
    (node.textContent ?? "").trim(),
  );
}

function jsonBytes(payload: unknown): ArrayBuffer {
  return new TextEncoder().encode(JSON.stringify(payload)).buffer as ArrayBuffer;
}

/** Клиент, у которого только скачивание артефакта падает: сводка отдаётся. */
function makeClient(downloadError: Error, payload: unknown = payloadOf([])): ExtendedRunClient {
  let summaryServed = false;
  return {
    ensureReady: async () => undefined,
    recipes: async () => [{ recipe_id: "rec-1", name: EXTENDED_RECIPE_NAME }],
    runAnalysis: async () => snapshot("running", null),
    runStatus: async () => snapshot("succeeded", "art-key"),
    artifactBytes: async () => {
      if (!summaryServed) {
        summaryServed = true;
        return jsonBytes(payload);
      }
      throw downloadError;
    },
  };
}

function mountHandle(client: ExtendedRunClient): ExtendedRunHandle {
  const handle = createExtendedRun({ client });
  document.body.replaceChildren(handle.root);
  handle.setSession("session-1");
  return handle;
}

async function runToDownloads(handle: ExtendedRunHandle): Promise<void> {
  handle.root
    .querySelector<HTMLButtonElement>(".lnt-w1-toolbar button")
    ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await vi.waitFor(() =>
    expect(handle.root.querySelectorAll("[data-bundle-file]")).toHaveLength(3),
  );
}

describe("createExtendedRun: скачивание артефактов", () => {
  it("показывает ошибку скачивания в строке статуса без необработанного отклонения", async () => {
    // Given: сводный прогон завершён, кнопки скачивания отрисованы, артефакт падает.
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown): void => {
      unhandled.push(reason);
    };
    process.on("unhandledRejection", onUnhandled);
    try {
      const handle = mountHandle(makeClient(new Error("404")));
      await runToDownloads(handle);
      const status = handle.root.querySelector<HTMLElement>('[role="status"]');

      // When
      handle.root
        .querySelector<HTMLButtonElement>(`[data-bundle-file="${BUNDLE_FILES[1]}"]`)
        ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));

      // Then
      await vi.waitFor(() => expect(status?.textContent).toContain("404"));
      await vi.waitFor(() => expect(unhandled).toEqual([]));
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  });
});

describe("createExtendedRun: холодный старт без launch-nonce", () => {
  it("получает nonce через ensureReady до первого POST прогона", async () => {
    // Given: клиент без nonce — requireNonce бросил бы uninitialized на мутации.
    const order: string[] = [];
    let releaseReady = (): void => undefined;
    const ready = new Promise<void>((resolve) => {
      releaseReady = resolve;
    });
    const client: ExtendedRunClient = {
      ensureReady: async () => {
        order.push("ensureReady");
        await ready;
      },
      recipes: async () => {
        order.push("recipes");
        return [{ recipe_id: "rec-1", name: EXTENDED_RECIPE_NAME }];
      },
      runAnalysis: async () => {
        order.push("runAnalysis");
        return snapshot("running", null);
      },
      runStatus: async () => snapshot("succeeded", "art-key"),
      artifactBytes: async () => jsonBytes(payloadOf([])),
    };
    const handle = mountHandle(client);

    // When: холодный клик по кнопке расширенного прогона.
    handle.root
      .querySelector<HTMLButtonElement>(".lnt-w1-toolbar button")
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    // Then: первым идёт ensureReady, и до его завершения мутация не уходит.
    await vi.waitFor(() => expect(order[0]).toBe("ensureReady"));
    expect(order).not.toContain("runAnalysis");
    releaseReady();
    await vi.waitFor(() => expect(order).toContain("runAnalysis"));
    handle.destroy();
  });
});

describe("сводка: коды причин", () => {
  it("дописывает коды к строке семейства через одну метку", async () => {
    // Given: реальная выдача probe — F17 недоступен из-за вне-сеточной циклической частоты.
    const payload = payloadOf({
      0: { id: "f01_phase_cycle", status: "available", codes: [] },
      16: {
        id: "f17_cyclic_spectral_coherence",
        status: "unavailable",
        codes: ["cyclic_frequency_off_grid"],
      },
    });

    // When
    const handle = mountHandle(makeClient(new Error("404"), payload));
    await runToDownloads(handle);

    // Then
    await vi.waitFor(() => expect(summaryItems(handle)).toHaveLength(18));
    expect(summaryItems(handle)[16]).toBe(
      "f17_cyclic_spectral_coherence: unavailable — Причина: cyclic_frequency_off_grid",
    );
  });

  it("печатает доминирующий код реальной выдачи без перевода", async () => {
    const payload = payloadOf({
      0: { id: "f01_phase_cycle", status: "available", codes: [] },
      4: {
        id: "f05_phase_conditioned_statistics",
        status: "unavailable",
        codes: ["phase_reference_unavailable"],
      },
    });

    const handle = mountHandle(makeClient(new Error("404"), payload));
    await runToDownloads(handle);

    await vi.waitFor(() => expect(summaryItems(handle)).toHaveLength(18));
    expect(summaryItems(handle)[4]).toBe(
      "f05_phase_conditioned_statistics: unavailable — Причина: phase_reference_unavailable",
    );
  });

  it("не печатает метку для семейства без кодов", async () => {
    const payload = payloadOf({
      0: { id: "f01_phase_cycle", status: "available" },
      1: { id: "f02_amplitude_time_shape", status: "unavailable", codes: [] },
    });

    const handle = mountHandle(makeClient(new Error("404"), payload));
    await runToDownloads(handle);

    await vi.waitFor(() => expect(summaryItems(handle)).toHaveLength(18));
    expect(summaryItems(handle)[1]).toBe("f02_amplitude_time_shape: unavailable");
  });
});

describe("parseCharacterizationSummary: границы", () => {
  it("reads F01 f1_hz and all 18 family statuses", () => {
    const payload = payloadOf({
      0: { id: "f01_phase_cycle", status: "available", codes: [] },
      1: { id: "f02_amplitude_time_shape", status: "unavailable", codes: ["baseline_unavailable"] },
    });

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.f1Hz).toBeCloseTo(50.01, 5);
    expect(summary?.families).toHaveLength(18);
    expect(summary?.families[0]).toEqual({
      id: "f01_phase_cycle",
      status: "available",
      reasonCodes: [],
    });
  });

  it("keeps reason codes verbatim in backend order", () => {
    const payload = payloadOf({
      0: { id: "f01_phase_cycle", status: "available", codes: [] },
      1: {
        id: "f03_interharmonic_tracking",
        status: "partial",
        codes: ["below_resolution", "peak_not_observed", "track_too_short"],
      },
    });

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.families[1]?.reasonCodes).toEqual([
      "below_resolution",
      "peak_not_observed",
      "track_too_short",
    ]);
  });

  it("reports null reason codes when the bundle omits them", () => {
    const payload = {
      families: Array.from({ length: 18 }, (_, index) => ({
        family_id: `f${String(index + 1).padStart(2, "0")}`,
        status: "unavailable",
        comparison_summary: [],
      })),
    };

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.families.every((family) => family.reasonCodes === null)).toBe(true);
  });

  it("rejects bundles without exactly 18 families", () => {
    expect(parseCharacterizationSummary({ families: [] })).toBeNull();
    expect(parseCharacterizationSummary(null)).toBeNull();
  });

  it("reports null F01 when the summary carries no f1_hz", () => {
    const payload = {
      families: Array.from({ length: 18 }, (_, index) => ({
        family_id: `f${String(index + 1).padStart(2, "0")}`,
        status: "unavailable",
        comparison_summary: [],
      })),
    };

    expect(parseCharacterizationSummary(payload)?.f1Hz).toBeNull();
  });
});
