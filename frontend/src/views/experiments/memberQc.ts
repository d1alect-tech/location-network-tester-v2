/** QC-логика участников эксперимента (todo 43): append-only inclusion state
 * по семантике бэкенда lnt/comparability/state.py (MemberInclusion) и
 * qc.py (InclusionState). Исключение — явное решение с причиной; undo
 * добавляет компенсирующую revision, никогда не удаляя аудит.
 * Verdict выводится из health каталога (routes_catalog.py) — рекомендация,
 * а не автоматическая команда (qc.py: «рекомендация оператору»). */

export type InclusionState = "proposed" | "included" | "excluded";

export interface StateRevision {
  readonly revision: number;
  readonly state: InclusionState;
  readonly actor: string;
  readonly reason: string;
  /** Ссылка на компенсируемую revision (undo), null для обычных решений. */
  readonly undo_of_revision: number | null;
}

export interface MemberInclusion {
  readonly member_id: string;
  readonly history: readonly StateRevision[];
}

/** Первая proposed-revision участника. */
export function proposeMember(memberId: string, actor: string, reason: string): MemberInclusion {
  return {
    member_id: memberId,
    history: [{ revision: 1, state: "proposed", actor, reason, undo_of_revision: null }],
  };
}

/** Явный переход состояния; только вперёд по журналу. */
export function transitionMember(
  member: MemberInclusion,
  state: Exclude<InclusionState, "proposed">,
  actor: string,
  reason: string,
): MemberInclusion {
  const current = currentRevision(member);
  return {
    member_id: member.member_id,
    history: [
      ...member.history,
      { revision: current + 1, state, actor, reason, undo_of_revision: null },
    ],
  };
}

/** Компенсирующая revision: возвращает состояние предыдущего решения,
 * сохраняя исходное решение в истории (аудит не переписывается). */
export function undoLastDecision(
  member: MemberInclusion,
  actor: string,
  reason: string,
): MemberInclusion {
  if (member.history.length < 2) {
    throw new Error("отмена невозможна: нет предыдущего решения");
  }
  const last = member.history[member.history.length - 1];
  const previous = member.history[member.history.length - 2];
  if (!last || !previous) throw new Error("повреждённая история участника");
  return {
    member_id: member.member_id,
    history: [
      ...member.history,
      {
        revision: last.revision + 1,
        state: previous.state,
        actor,
        reason,
        undo_of_revision: last.revision,
      },
    ],
  };
}

export function currentRevision(member: MemberInclusion): number {
  const last = member.history[member.history.length - 1];
  if (!last) throw new Error("пустая история участника");
  return last.revision;
}

export function currentState(member: MemberInclusion): InclusionState {
  const last = member.history[member.history.length - 1];
  if (!last) throw new Error("пустая история участника");
  return last.state;
}

export function isExcluded(member: MemberInclusion): boolean {
  return currentState(member) === "excluded";
}

export interface QcVerdict {
  tone: "ok" | "warn" | "error";
  label: string;
  recommended_state: InclusionState | null;
  reason_code: string | null;
}

const HEALTH_LABELS: Record<string, string> = {
  ok: "QC пройден",
  degraded: "Данные с замечаниями",
};

const BLOCKING_HEALTH = new Set([
  "corrupt_manifest",
  "incomplete_capture",
  "clipping",
  "missing_metrics",
]);

/** Verdict из health каталога: текст+код причины (не только цвет). */
export function deriveQcVerdict(health: string): QcVerdict {
  if (health === "ok") {
    return {
      tone: "ok",
      label: HEALTH_LABELS.ok ?? "QC пройден",
      recommended_state: null,
      reason_code: null,
    };
  }
  if (health === "degraded") {
    return {
      tone: "warn",
      label: HEALTH_LABELS.degraded ?? "Данные с замечаниями",
      recommended_state: null,
      reason_code: "qc_degraded",
    };
  }
  if (BLOCKING_HEALTH.has(health)) {
    return {
      tone: "error",
      label: `Блокирующий дефект: ${health}`,
      recommended_state: "excluded",
      reason_code: `qc_${health}`,
    };
  }
  // Неизвестный код — явное предупреждение, а не молчаливый пропуск.
  return {
    tone: "warn",
    label: `Неизвестное состояние данных: ${health}`,
    recommended_state: null,
    reason_code: "qc_unknown_health",
  };
}
