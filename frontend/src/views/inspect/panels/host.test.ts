import { describe, expect, it } from "vitest";
import { ApiError } from "../../../api/errors";
import type { ArtifactClient } from "./fetch";
import { createPanelHost, harmonicsVisible } from "./host";

/** Given / When / Then: harmonics card visibility vs cycles and BranchFailure. */

function fakeClient(files: Readonly<Record<string, unknown>>): ArtifactClient & {
  readonly requested: string[];
} {
  const requested: string[] = [];
  return {
    requested,
    requestJson: async (_method, path) => {
      requested.push(path);
      const name = path.split("/").pop() ?? "";
      if (!(name in files)) throw new ApiError("http", { status: 404 });
      return files[name];
    },
    rawFetch: async (input) => {
      const path = String(input);
      requested.push(path);
      const name = path.split("/").pop() ?? "";
      if (!(name in files)) {
        return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
      }
      const body = files[name];
      return new Response(typeof body === "string" ? body : JSON.stringify(body), { status: 200 });
    },
  };
}

describe("harmonicsVisible", () => {
  it("hides the card when cycles_analyzed is below 100", () => {
    // Given
    const cycles = 99;
    const failures: readonly { readonly branch: string; readonly message: string }[] = [];

    // When
    const visible = harmonicsVisible(cycles, failures);

    // Then
    expect(visible).toBe(false);
  });

  it("hides the card when the harmonics branch failed", () => {
    // Given
    const cycles = 200;
    const failures = [{ branch: "harmonics", message: "window underflow" }];

    // When
    const visible = harmonicsVisible(cycles, failures);

    // Then
    expect(visible).toBe(false);
  });

  it("shows the card when cycles are enough and harmonics did not fail", () => {
    // Given
    const cycles = 100;
    const failures = [{ branch: "apd", message: "skip" }];

    // When
    const visible = harmonicsVisible(cycles, failures);

    // Then
    expect(visible).toBe(true);
  });
});

describe("createPanelHost.bind", () => {
  it("does not request ITIC or CM/DM on measurement and leaves panels closed", async () => {
    // Given
    const client = fakeClient({
      "harmonics.json": {
        windows: [{ index: 0, start_time_s: 0, thd: 0.1, fundamental_rms: 230 }],
      },
      "notching.json": { notches: [] },
    });
    const root = document.createElement("div");
    const host = createPanelHost({ client, root });

    // When
    await host.bind(
      {
        session: "t1-measurement",
        artifactKey: "art-meas",
        sessionType: "measurement",
        cycles: 118,
        failures: [],
      },
      new AbortController().signal,
    );

    // Then
    expect(client.requested.some((path) => path.includes("power_quality.json"))).toBe(false);
    expect(client.requested.some((path) => path.includes("cm_dm_spectrum.csv"))).toBe(false);
    expect(root.querySelector('[data-panel="harmonics"]')).not.toBeNull();
    expect(root.querySelector('[data-panel="itic"]')).toBeNull();
    expect(root.querySelector('[data-panel="cm_dm"]')).toBeNull();
    expect(root.querySelector("details[open]")).toBeNull();
  });

  it("repeats the BranchFailure branch name on the failure panel", async () => {
    // Given
    const client = fakeClient({});
    const root = document.createElement("div");
    const host = createPanelHost({ client, root });

    // When
    await host.bind(
      {
        session: "t1-measurement",
        artifactKey: "art-meas",
        sessionType: "measurement",
        cycles: 200,
        failures: [{ branch: "harmonics", message: "window underflow" }],
      },
      new AbortController().signal,
    );

    // Then
    const failure = root.querySelector('[data-panel="branch-failure"]');
    expect(failure).not.toBeNull();
    expect(failure?.querySelector("summary")?.textContent).toBe("harmonics");
    expect(root.querySelector('[data-panel="harmonics"]')).toBeNull();
  });
});
