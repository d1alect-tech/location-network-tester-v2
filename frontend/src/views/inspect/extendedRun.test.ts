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

function summaryPayload(): unknown {
  return {
    families: Array.from({ length: 18 }, (_, index) => ({
      family_id: `f${String(index + 1).padStart(2, "0")}_family`,
      status: "available",
      comparison_summary: index === 0 ? [{ name: "f1_hz", value: 50.01, unit: "Hz" }] : [],
    })),
  };
}

function jsonBytes(payload: unknown): ArrayBuffer {
  return new TextEncoder().encode(JSON.stringify(payload)).buffer as ArrayBuffer;
}

/** Клиент, у которого только скачивание артефакта падает: сводка отдаётся. */
function makeClient(downloadError: Error): ExtendedRunClient {
  let summaryServed = false;
  return {
    recipes: async () => [{ recipe_id: "rec-1", name: EXTENDED_RECIPE_NAME }],
    runAnalysis: async () => snapshot("running", null),
    runStatus: async () => snapshot("succeeded", "art-key"),
    artifactBytes: async () => {
      if (!summaryServed) {
        summaryServed = true;
        return jsonBytes(summaryPayload());
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

describe("parseCharacterizationSummary", () => {
  it("reads F01 f1_hz and all 18 family statuses", () => {
    const payload = {
      families: Array.from({ length: 18 }, (_, index) => ({
        family_id: index === 0 ? "f01_phase_cycle" : `f${String(index + 1).padStart(2, "0")}_other`,
        status: index === 0 ? "available" : "unavailable",
        comparison_summary:
          index === 0 ? [{ name: "f1_hz", value: 50.01, unit: "Hz", circular: false }] : [],
      })),
    };

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.f1Hz).toBeCloseTo(50.01, 5);
    expect(summary?.families).toHaveLength(18);
    expect(summary?.families[0]).toEqual({ id: "f01_phase_cycle", status: "available" });
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
