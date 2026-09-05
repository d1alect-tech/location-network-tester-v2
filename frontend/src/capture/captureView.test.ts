import { beforeEach, describe, expect, it } from "vitest";
import type { LntApiClient } from "../api/client";
import type { JobSnapshot } from "../api/types-jobs";
import { createCaptureView } from "./captureView";

function flush(ms = 0): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function flushAll(rounds = 12): Promise<void> {
  for (let i = 0; i < rounds; i += 1) await flush(0);
}

function interruptedJob(): JobSnapshot {
  return {
    schema_version: 1,
    version: 9,
    job_id: "job-interrupted",
    kind: "capture",
    status: "interrupted",
    stage: "capturing",
    series_index: 1,
    series_total: 3,
    written_sessions: ["cap-001"],
    result: null,
    error_code: "server_restart",
    error_message: null,
  };
}

/** Клиент после перезапуска: bootstrap жив, но сохранённого запроса повтора нет. */
function restartedClient(): LntApiClient {
  return {
    bootstrap: async () => ({}),
    currentNonce: "nonce-test",
    jobs: {
      list: async () => ({ items: [interruptedJob()], next_cursor: null }),
      get: async () => interruptedJob(),
      start: async () => {
        throw new Error("не должен стартовать без запроса");
      },
      cancel: async () => interruptedJob(),
    },
    requestJson: async () => {
      throw new Error("не используется в этом сценарии");
    },
  } as unknown as LntApiClient;
}

describe("createCaptureView повтор без запроса (U3: no-op → видимая причина)", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("retry click with no saved request shows an alert instead of silence", async () => {
    const view = createCaptureView(restartedClient());
    document.body.append(view.root);
    await flushAll();

    const retry = [...view.root.querySelectorAll("button")].find(
      (node) => node.textContent === "Повторить задачу",
    ) as HTMLButtonElement | undefined;
    expect(retry).toBeInstanceOf(HTMLButtonElement);
    expect(retry?.disabled).toBe(false);
    retry?.click();
    await flushAll();

    const alert = view.root.querySelector(".capture-alert");
    expect(alert instanceof HTMLElement && !alert.hidden).toBe(true);
    expect(alert?.textContent).toContain("повтор");
    view.dispose();
  });
});
