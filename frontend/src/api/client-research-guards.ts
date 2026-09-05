// Доменные guards исследовательского контура v2 (выделено из client-research.ts):
// проверки конвертов experiments/runs/hypotheses/trends/comparability.
import { ApiError } from "./errors";
import type {
  ComparabilityReport,
  CursorPage,
  ExperimentRecord,
  HypothesisRecord,
  OpenRecord,
  ProtocolRunRecord,
  TrendAnalysisResult,
} from "./types-research";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export type ItemAssert<T> = (item: Record<string, unknown>) => T;

export function assertOpen(item: Record<string, unknown>): OpenRecord {
  return item;
}

export function assertExperiment(item: Record<string, unknown>): ExperimentRecord {
  if (typeof item.experiment_id !== "string") throw new ApiError("parse");
  return item as ExperimentRecord;
}

export function assertHypothesis(item: Record<string, unknown>): HypothesisRecord {
  if (
    typeof item.hypothesis_id !== "string" ||
    typeof item.revision !== "number" ||
    typeof item.status !== "string"
  ) {
    throw new ApiError("parse");
  }
  return item as HypothesisRecord;
}

export function requireCursorPage<T>(payload: unknown, assertItem: ItemAssert<T>): CursorPage<T> {
  if (!isRecord(payload) || !Array.isArray(payload.items)) throw new ApiError("parse");
  const { next_cursor } = payload;
  if (next_cursor !== null && typeof next_cursor !== "string") throw new ApiError("parse");
  return {
    items: payload.items.map((item) => {
      if (!isRecord(item)) throw new ApiError("parse");
      return assertItem(item);
    }),
    next_cursor,
  };
}

export function requireRun(payload: unknown): ProtocolRunRecord {
  if (!isRecord(payload)) throw new ApiError("parse");
  if (
    typeof payload.run_id !== "string" ||
    typeof payload.status !== "string" ||
    typeof payload.revision !== "number"
  ) {
    throw new ApiError("parse");
  }
  return payload as ProtocolRunRecord;
}

export function requireTrendResult(payload: unknown): TrendAnalysisResult {
  if (!isRecord(payload)) throw new ApiError("parse");
  const stamps = payload.normalized_timestamps;
  if (!Array.isArray(stamps) || !stamps.every((item) => typeof item === "string")) {
    throw new ApiError("parse");
  }
  const meta = payload.metadata;
  if (
    !isRecord(meta) ||
    typeof meta.units !== "string" ||
    typeof meta.estimator !== "string" ||
    typeof meta.n !== "number"
  ) {
    throw new ApiError("parse");
  }
  return payload as TrendAnalysisResult;
}

export function requireComparabilityReport(payload: unknown): ComparabilityReport {
  if (!isRecord(payload)) throw new ApiError("parse");
  if (
    typeof payload.comparable !== "boolean" ||
    !Array.isArray(payload.findings) ||
    !payload.findings.every((item) => isRecord(item))
  ) {
    throw new ApiError("parse");
  }
  return payload as unknown as ComparabilityReport;
}
