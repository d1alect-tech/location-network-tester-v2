/** Русские фразы для машинных кодов причин characterization-v1 (18 семейств).
 *
 * Ключи — дословно те значения, что бэкенд кладёт в `family.reason_codes` и
 * `family.qc.reason_codes` (`src/lnt/characterization/metadata_mapping.py`,
 * `family_mapping`). Словарь собран из объявленных бэкендом наборов:
 * `DECLARED_CODES` каждого семейства, `PHASE_ROOT_REASON_CODES` в
 * `characterization/phase.py`, литералы F01/F02 и `NOT_COMPUTED` в
 * `characterization/family_envelope.py`. Формулировки, совпавшие с глоссой
 * `frontend/prototypes/extended-run.html`, переиспользованы дословно; остальные
 * написаны по образцу `recovery_action_ru` из `capture/capture_preflight.py` —
 * коротко, без жаргона, от лица оператора.
 *
 * Код печатается рядом с фразой, а не заменяется ею: неизвестный код обязан
 * остаться видимым, поэтому запасной путь возвращает сам код, а не «н/д».
 */

/** Объявленный бэкендом код причины → короткая русская фраза. */
export const REASON_CODE_RU: Readonly<Record<string, string>> = {
  // Фазовый корень: characterizations/phase.py, PHASE_ROOT_REASON_CODES.
  phase_reference_unavailable: "нет фазовой опоры F01",
  no_sync_reference: "не найдено событие синхронизации",
  grid_unstable: "сетка частот неустойчива",
  insufficient_phase_support: "недостаточно данных по фазе",
  phase_transform_work_budget_too_small: "слишком мал бюджет фазового преобразования",
  phase_cycle_work_budget_too_small: "слишком мал бюджет расчёта фазового цикла",
  phase_cycle_work_budget_exceeded: "исчерпан бюджет расчёта фазового цикла",
  not_computed: "семейство не считалось",

  // F01 phase_cycle.
  window_too_short: "окно слишком короткое",
  fundamental_absent: "основная частота не обнаружена",
  phase_unstable: "фаза неустойчива",

  // F02 amplitude_shape.
  template_unavailable: "шаблон F01 недоступен",
  baseline_unavailable: "базовый участок недоступен",
  overlapping_events: "события перекрываются",
  event_truncated: "событие обрезано границей записи",
  below_snr: "ниже отношения сигнал/шум",

  // F03 interharmonic_tracking.
  below_resolution: "ниже разрешения по частоте",
  peak_not_observed: "пик не наблюдался",
  track_too_short: "трек слишком короткий",
  leakage_ambiguous: "утечка между пиками неоднозначна",

  // F04 periodicity.
  record_too_short_for_tau: "запись короче требуемого окна",
  carrier_unavailable: "несущая F01 недоступна",
  phase_unwrap_failed: "фаза не развернулась однозначно",
  not_enough_samples: "недостаточно отсчётов",

  // F05 phase_conditioned_statistics.
  insufficient_support: "недостаточно поддержки",

  // F06 modulation_trajectories.
  multiple_components: "несколько компонент в полосе",
  low_snr: "низкое отношение сигнал/шум",
  envelope_zero: "огибающая равна нулю",
  band_invalid: "полоса непригодна для расчёта",
  phase_aliased: "фаза алиасится",

  // F07 comb_sideband_cepstrum.
  harmonic_comb_only: "только гребёнка гармоник",
  window_dependent: "результат зависит от окна",
  no_dominant_quefrency: "нет доминирующей кепстральной частоты",
  log_floor_unstable: "порог по логу неустойчив",

  // F08 transient_morphology.
  clipped: "сигнал обрезан ограничителем",
  single_exponential_poor: "одно экспоненциальное описание не подходит",
  too_few_samples: "слишком мало отсчётов",
  multimode: "в событии несколько мод",

  // F09 event_ordering.
  insufficient_events: "недостаточно событий",
  dead_time_overlap: "мёртвое время перекрывается",
  single_cycle_record: "в записи один цикл",
  gaps_present: "в записи есть пропуски",

  // F10 threshold_episode_surface.
  scale_zero: "шкала нулевая",
  duration_below_sample_resolution: "длительность ниже разрешения отсчётов",

  // F11 conditional_distributions.
  bin_empty: "пустой бин",
  dominant_band_unavailable: "доминирующая полоса недоступна",
  mode_unavailable: "мода недоступна",
  mode_assignment_unavailable: "моду нельзя назначить",
  event_limit: "достигнут лимит событий",

  // F12 spectral_kurtosis.
  scale_unsupported: "шкала не поддерживается",
  insufficient_frames: "не набрано минимум кадров",
  zero_power: "нулевая мощность",
  no_significant_bin: "нет значимых бинов",

  // F13 band_envelope_coactivity.
  band_above_nyquist: "полоса выше Найквиста",
  filter_support_too_short: "опора фильтра слишком короткая",
  filter_context_unstable: "контекст фильтрации неустойчив",
  nonfinite_input: "во входе есть нечисловые отсчёты",
  mixed_unavailable_support: "поддержка частично недоступна",
  insufficient_activity: "недостаточно активности",
  lag_support_too_short: "опора по задержке слишком короткая",

  // F14 cross_channel_event_association.
  channel_missing: "канал B отсутствует в записи",
  channels_not_synchronous: "каналы не синхронны",
  insufficient_triggers: "недостаточно триггеров",
  window_truncated: "окно обрезано",

  // F15 interpretable_modes.
  insufficient_windows: "недостаточно окон",
  feature_unavailable: "признак недоступен",
  feature_scale_zero: "признак нулевой",
  empty_cluster: "пустой кластер",
  label_limit: "достигнут лимит меток",
  stability_block_too_short: "блок устойчивости слишком короткий",

  // F16 multiscale_memory.
  lag_above_support: "задержка больше длины записи",
  insufficient_pairs: "недостаточно пар отсчётов",
  insufficient_count_windows: "недостаточно счётных окон",
  zero_event_rate: "нулевая частота событий",

  // F17 cyclic_spectral_coherence.
  cyclic_frequency_off_grid: "циклическая частота вне сетки",
  insufficient_cycles: "недостаточно циклов",
  zero_denominator: "нулевой знаменатель",
  no_significant_cell: "нет значимых ячеек",

  // F18 bicoherence_triads.
  triad_off_grid: "триада вне сетки",
  triad_above_nyquist: "триада выше Найквиста",
  iaaft_not_converged: "сурогат IAAFT не сошёлся",
  no_significant_triad: "нет значимых триад",

  // Общий для F10/F12/F17/F18.
  artifact_limit: "превышен лимит артефакта",
};

/** Префикс запасного пути: фраза остаётся читаемой, код печатается рядом. */
const UNKNOWN_PREFIX = "неизвестный код";
const BLANK_CODE = "код причины не указан";

/** Русская фраза кода причины; неизвестный код виден дословно, а не прячется. */
export function reasonCodeRu(code: string): string {
  if (code.trim().length === 0) return BLANK_CODE;
  const known = REASON_CODE_RU[code];
  if (known !== undefined) return known;
  return `${UNKNOWN_PREFIX}: ${code}`;
}
