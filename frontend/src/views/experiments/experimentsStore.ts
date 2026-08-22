/** Хранилище рабочего контура экспериментов (todo 43): списки, детали,
 * мутации создания/обновления и клиентский журнал включённости участников.
 * Все загрузки — через createResourceLoader (гонко-защита resource.ts);
 * мутации — через createMutation. Конфликт revision (409) не замалчивается. */

import type { LntApiClient } from "../../api/client";
import type { ApiError } from "../../api/errors";
import type { ExperimentWritePayload, OpenRecord } from "../../api/types-research";
import { createMutation, createResourceLoader } from "../../state/resource";
import type { Experiment } from "./experimentModel";
import {
  type MemberInclusion,
  proposeMember,
  transitionMember,
  undoLastDecision,
} from "./memberQc";

export interface ExperimentDetail {
  experiment: Experiment;
  members: OpenRecord[];
  steps: OpenRecord[];
}

export interface ExperimentsStoreOptions {
  client: Pick<LntApiClient, "research">;
}

export interface CreateExperimentInput {
  payload: ExperimentWritePayload;
}

export class ExperimentsStore {
  readonly list;
  readonly detail;
  readonly createRun;
  readonly updateRun;
  /** Клиентский append-only журнал включённости: experiment_id → member_id → журнал. */
  private readonly inclusionLog = new Map<string, Map<string, MemberInclusion>>();

  constructor(options: ExperimentsStoreOptions) {
    this.list = createResourceLoader<OpenRecord[]>(async (_key, signal) => {
      const page = await options.client.research.experiments(200, null, { signal });
      return page.items;
    });
    this.detail = createResourceLoader<ExperimentDetail>(async (experimentId, signal) => {
      const [experiment, membersPage, stepsPage] = await Promise.all([
        options.client.research.experiment(experimentId, { signal }),
        options.client.research.members(experimentId, 200, null, { signal }),
        options.client.research.steps(experimentId, 200, null, { signal }),
      ]);
      return {
        experiment: experiment as Experiment,
        members: membersPage.items,
        steps: stepsPage.items,
      };
    });
    this.createRun = createMutation<ExperimentWritePayload, OpenRecord>(async (payload) =>
      options.client.research.createExperiment(payload),
    );
    this.updateRun = createMutation<ExperimentWritePayload, OpenRecord>(async (payload) =>
      options.client.research.updateExperiment(payload.experiment.experiment_id, payload),
    );
  }

  /** Журнал участника; при отсутствии создаёт proposed-revision. */
  inclusion(experimentId: string, memberId: string): MemberInclusion {
    const byMember = this.inclusionLog.get(experimentId);
    if (byMember?.has(memberId)) return byMember.get(memberId) as MemberInclusion;
    const created = proposeMember(
      memberId,
      "user:operator",
      "импортирован из состава эксперимента",
    );
    this.setInclusion(experimentId, created);
    return created;
  }

  excludeMember(experimentId: string, memberId: string, reason: string): MemberInclusion {
    const updated = transitionMember(
      this.inclusion(experimentId, memberId),
      "excluded",
      "user:operator",
      reason,
    );
    this.setInclusion(experimentId, updated);
    return updated;
  }

  includeMember(experimentId: string, memberId: string, reason: string): MemberInclusion {
    const updated = transitionMember(
      this.inclusion(experimentId, memberId),
      "included",
      "user:operator",
      reason,
    );
    this.setInclusion(experimentId, updated);
    return updated;
  }

  /** Отмена последнего решения: компенсирующая revision, аудит сохраняется. */
  undoMember(experimentId: string, memberId: string, reason: string): MemberInclusion {
    const updated = undoLastDecision(
      this.inclusion(experimentId, memberId),
      "user:operator",
      reason,
    );
    this.setInclusion(experimentId, updated);
    return updated;
  }

  /** Полная история решений участника для аудита в UI. */
  inclusionHistory(experimentId: string, memberId: string): readonly MemberInclusion[] {
    const inclusion = this.inclusion(experimentId, memberId);
    return [inclusion];
  }

  private setInclusion(experimentId: string, inclusion: MemberInclusion): void {
    let byMember = this.inclusionLog.get(experimentId);
    if (!byMember) {
      byMember = new Map();
      this.inclusionLog.set(experimentId, byMember);
    }
    byMember.set(inclusion.member_id, inclusion);
  }
}

/** Разбор ошибки мутации в русское сообщение без потери кода причины. */
export function mutationErrorText(error: ApiError): string {
  if (error.kind === "conflict") {
    return `Конфликт версий (${error.code ?? "revision_conflict"}): запись изменена другим процессом. Обновите данные и повторите.`;
  }
  return error.message;
}
