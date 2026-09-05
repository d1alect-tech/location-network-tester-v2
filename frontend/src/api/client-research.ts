/** Доменный под-клиент исследовательского контура v2 (Todo 34):
 * эксперименты, запуски протоколов, гипотезы, тренды и сравнимость.
 * Маршруты: routes_experiments.py, routes_research.py, routes_quality.py.
 * Все мутации подписываются nonce запуска (middleware требует его на
 * каждый POST/PUT/PATCH/DELETE); конверты проверяются перед выдачей.
 * Группы методов живут в client-research-experiments/runs/hypotheses;
 * здесь только iface ResearchApi и фабрика-проводка без логики. */

import type { LntApiClient } from "./client";
import {
  type ExperimentsResearchGroup,
  createExperimentsGroup,
} from "./client-research-experiments";
import { type HypothesesResearchGroup, createHypothesesGroup } from "./client-research-hypotheses";
import { type RunsResearchGroup, createRunsGroup } from "./client-research-runs";

export {
  assertExperiment,
  assertHypothesis,
  assertOpen,
  isRecord,
  requireComparabilityReport,
  requireCursorPage,
  requireRun,
  requireTrendResult,
} from "./client-research-guards";
export {
  createExperimentsGroup,
  type ExperimentsResearchGroup,
} from "./client-research-experiments";
export {
  createHypothesesGroup,
  type HypothesesResearchGroup,
} from "./client-research-hypotheses";
export { V2, experimentPath, fetchPage, mutation, runPath } from "./client-research-paths";
export { createRunsGroup, type RunsResearchGroup } from "./client-research-runs";

export interface ResearchApi
  extends ExperimentsResearchGroup,
    RunsResearchGroup,
    HypothesesResearchGroup {}

export function createResearchApi(client: LntApiClient): ResearchApi {
  return {
    ...createExperimentsGroup(client),
    ...createRunsGroup(client),
    ...createHypothesesGroup(client),
  };
}
