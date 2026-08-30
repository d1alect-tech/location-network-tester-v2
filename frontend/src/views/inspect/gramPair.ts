import { readNpzArrays } from "../../components/charts/npz";
import { sliceTile } from "../../components/charts/spectrogramModel";
import type { SpectrogramLevel } from "../../components/charts/spectrogramModel";
import { initialTileRequest, levelFromNpz } from "../../components/charts/spectrogramSetup";
import { alignGramLevels } from "./gramAlign";
import { getArtifactJson } from "./panels/fetch";
import type { ArtifactClient } from "./panels/fetch";
import { isPointer } from "./w1Parse";

export type GramMode = "a" | "b" | "delta";

export type GramPairTile = {
  readonly kind: "tile";
  readonly tile: {
    readonly times: Float64Array;
    readonly freqs: Float64Array;
    readonly values: Float32Array;
  };
  readonly minDb: number;
  readonly maxDb: number;
};

export type GramPairMismatch = { readonly kind: "mismatch" };

export type GramPairHandle = {
  load(a: string, b: string | null): Promise<void>;
  setMode(mode: GramMode): void;
  mode(): GramMode;
  gridMatches(): boolean;
  current(): GramPairTile | GramPairMismatch;
  dispose(): void;
};

export type GramPairClient = {
  readonly analysis: {
    readonly artifactBytes: (
      session: string,
      key: string,
      filename: string,
      o?: { readonly signal?: AbortSignal },
    ) => Promise<ArrayBuffer | Uint8Array>;
    readonly events?: unknown;
  };
  readonly requestJson?: ArtifactClient["requestJson"];
  readonly rawFetch?: ArtifactClient["rawFetch"];
};

export type GramPairOpts = {
  readonly client: GramPairClient;
  readonly loadLevel?: (session: string, signal: AbortSignal) => Promise<SpectrogramLevel>;
};

class GramPairError extends Error {
  readonly name = "GramPairError";
  constructor(readonly code: "missing_client" | "missing_pointer") {
    super(code);
  }
}

function assertNever(value: never): never {
  throw new Error(`unhandled ${String(value)}`);
}

function isAbort(error: unknown): boolean {
  if (typeof error !== "object" || error === null) return false;
  if (!("name" in error)) return false;
  return error.name === "AbortError";
}

function bytesToArrayBuffer(bytes: ArrayBuffer | Uint8Array): ArrayBuffer {
  if (bytes instanceof ArrayBuffer) return bytes;
  const copy = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(copy).set(bytes);
  return copy;
}

function unusedRawFetch(): Promise<Response> {
  throw new GramPairError("missing_client");
}

async function fetchLevel(
  client: GramPairClient,
  session: string,
  signal: AbortSignal,
): Promise<SpectrogramLevel> {
  const requestJson = client.requestJson;
  if (requestJson === undefined) throw new GramPairError("missing_client");
  const pointerRaw = await getArtifactJson(
    { requestJson, rawFetch: client.rawFetch ?? unusedRawFetch },
    `/api/analysis/sessions/${encodeURIComponent(session)}/.lnt-default-analysis.json`,
    signal,
  );
  if (!isPointer(pointerRaw)) throw new GramPairError("missing_pointer");
  const bytes = await client.analysis.artifactBytes(session, pointerRaw.artifact_key, "spectrogram.npz", {
    signal,
  });
  return levelFromNpz(
    await readNpzArrays(bytesToArrayBuffer(bytes), ["time_s", "frequency_hz", "power_db"]),
  );
}

function finiteDb(values: Float32Array): { minDb: number; maxDb: number } {
  let minDb = Number.POSITIVE_INFINITY;
  let maxDb = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    if (value < minDb) minDb = value;
    if (value > maxDb) maxDb = value;
  }
  return { minDb, maxDb };
}

function symmetricDb(values: Float32Array): { minDb: number; maxDb: number } {
  let peak = 0;
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    const abs = Math.abs(value);
    if (abs > peak) peak = abs;
  }
  return { minDb: -peak, maxDb: peak };
}

function tileOf(level: SpectrogramLevel, scale: "finite" | "symmetric"): GramPairTile {
  const tile = sliceTile(level, initialTileRequest(level));
  const range = scale === "finite" ? finiteDb(tile.values) : symmetricDb(tile.values);
  return { kind: "tile", tile, minDb: range.minDb, maxDb: range.maxDb };
}

function deltaLevel(a: SpectrogramLevel, b: SpectrogramLevel): SpectrogramLevel | null {
  const aligned = alignGramLevels(a, b);
  if (aligned.kind !== "ok") return null;
  return {
    timeS: a.timeS,
    frequencyHz: a.frequencyHz,
    powerDb: aligned.delta,
    timeBins: a.timeBins,
    bands: a.bands,
  };
}

export function createGramPair(opts: GramPairOpts): GramPairHandle {
  const resolveLevel = opts.loadLevel ?? ((session, signal) => fetchLevel(opts.client, session, signal));
  let generation = 0;
  let controller = new AbortController();
  let levelA: SpectrogramLevel | null = null;
  let levelB: SpectrogramLevel | null = null;
  let activeMode: GramMode = "a";
  let matches = false;

  return {
    async load(a, b) {
      const gen = ++generation;
      controller.abort();
      controller = new AbortController();
      const { signal } = controller;
      try {
        const [loadedA, loadedB] = await Promise.all([
          resolveLevel(a, signal),
          b === null ? Promise.resolve(null) : resolveLevel(b, signal),
        ]);
        if (gen !== generation) return;
        levelA = loadedA;
        levelB = loadedB;
        matches = loadedB !== null && alignGramLevels(loadedA, loadedB).kind === "ok";
        activeMode = loadedB !== null ? "b" : "a";
      } catch (error) {
        if (gen !== generation || isAbort(error)) return;
        throw error;
      }
    },
    setMode(mode) {
      if (mode === "delta" && !matches) return;
      if (mode === "b" && levelB === null) return;
      activeMode = mode;
    },
    mode: () => activeMode,
    gridMatches: () => matches,
    current() {
      switch (activeMode) {
        case "a":
          return levelA === null ? { kind: "mismatch" } : tileOf(levelA, "finite");
        case "b":
          return levelB === null ? { kind: "mismatch" } : tileOf(levelB, "finite");
        case "delta": {
          if (levelA === null || levelB === null) return { kind: "mismatch" };
          const delta = deltaLevel(levelA, levelB);
          return delta === null ? { kind: "mismatch" } : tileOf(delta, "symmetric");
        }
        default:
          return assertNever(activeMode);
      }
    },
    dispose() {
      generation += 1;
      controller.abort();
    },
  };
}
