import { describe, expect, it } from "vitest";
import { ApiError } from "../../../api/errors";
import type { ArtifactClient } from "./fetch";
import { HARMONICS_LABEL } from "./harmonics";
import { ABSENT_ARTIFACT, createPanelHost, harmonicsVisible } from "./host";

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

  it("announces a failed branch as an absence chip, not a hollow panel", async () => {
    // Given
    const client = fakeClient({});
    const root = document.createElement("div");
    const host = createPanelHost({ client, root });

    // When
    const bound = await host.bind(
      {
        session: "t1-measurement",
        artifactKey: "art-meas",
        sessionType: "measurement",
        cycles: 200,
        failures: [
          { branch: "harmonics", message: "window underflow" },
          { branch: "psd", message: "нет отсчётов" },
        ],
      },
      new AbortController().signal,
    );

    // Then: имя ветки и причина названы, пустого раскрытия нет.
    expect(root.querySelector('[data-panel="branch-failure"]')).toBeNull();
    expect(root.querySelector('[data-panel="harmonics"]')).toBeNull();
    expect(bound.absent).toContainEqual({
      kind: "harmonics",
      label: HARMONICS_LABEL,
      reason: "ветка не посчитана: window underflow",
      tone: "failed",
    });
    // Ветка без своей панели не теряется.
    expect(bound.absent).toContainEqual({
      kind: "psd",
      label: "psd",
      reason: "ветка не посчитана: нет отсчётов",
      tone: "failed",
    });
    expect(bound.panelCount).toBe(0);
  });

  it("announces every missing artifact of a measurement session", async () => {
    // Given: записан только burst.json.
    const client = fakeClient({ "burst.json": { burst_count: 0, bursts: [] } });
    const root = document.createElement("div");
    const host = createPanelHost({ client, root });

    // When
    const bound = await host.bind(
      {
        session: "t1-measurement",
        artifactKey: "art-meas",
        sessionType: "measurement",
        cycles: 200,
        failures: [],
      },
      new AbortController().signal,
    );

    // Then: пять честных отсутствий, одна панель, ITIC/CM-DM не объявлены
    // (неприменимы к типу сессии — это не отсутствие артефакта).
    expect(bound.panelCount).toBe(1);
    expect(bound.absent.map((row) => row.kind)).toEqual([
      "harmonics",
      "notching",
      "apd",
      "trends",
      "audio",
    ]);
    expect(bound.absent.every((row) => row.reason === ABSENT_ARTIFACT)).toBe(true);
    expect(bound.absent.every((row) => row.tone === "absent")).toBe(true);
  });

  it("names the cycle floor when harmonics are withheld", async () => {
    // Given: артефакт на месте, циклов меньше минимума для лимита THD-V.
    const client = fakeClient({
      "harmonics.json": {
        windows: [{ index: 0, start_time_s: 0, thd: 0.1, fundamental_rms: 230 }],
      },
    });
    const root = document.createElement("div");
    const host = createPanelHost({ client, root });

    // When
    const bound = await host.bind(
      {
        session: "t1-measurement",
        artifactKey: "art-meas",
        sessionType: "measurement",
        cycles: 47,
        failures: [],
      },
      new AbortController().signal,
    );

    // Then
    expect(root.querySelector('[data-panel="harmonics"]')).toBeNull();
    expect(bound.absent).toContainEqual({
      kind: "harmonics",
      label: HARMONICS_LABEL,
      reason: "недостаточно циклов (47 из 100)",
      tone: "withheld",
    });
    // Скаляры THD-V при этом остаются фактом окон, без нормативной оценки.
    expect(bound.windows).toHaveLength(1);
  });

  it("shows the key value in the collapsed summary", async () => {
    // Given
    const client = fakeClient({
      "harmonics.json": {
        windows: [{ index: 0, start_time_s: 0, thd: 0.04, fundamental_rms: 230 }],
      },
      "burst.json": { burst_count: 3, bursts: [] },
    });
    const root = document.createElement("div");
    const host = createPanelHost({ client, root });

    // When
    const bound = await host.bind(
      {
        session: "t1-measurement",
        artifactKey: "art-meas",
        sessionType: "measurement",
        cycles: 200,
        failures: [],
      },
      new AbortController().signal,
    );

    // Then: значение видно без раскрытия, тело по-прежнему ленивое.
    const harmonics = root.querySelector('[data-panel="harmonics"]');
    expect(harmonics?.querySelector("[data-panel-key]")?.textContent).toBe("THD 0.04000");
    expect(harmonics?.querySelector(".lnt-w1-sum-label")?.textContent).toBe(HARMONICS_LABEL);
    expect(root.querySelector('[data-panel="burst"] [data-panel-key]')?.textContent).toBe("3");
    expect(root.querySelector('[data-panel="harmonics"] table')).toBeNull();
    expect(bound.panelCount).toBe(2);
  });
});
