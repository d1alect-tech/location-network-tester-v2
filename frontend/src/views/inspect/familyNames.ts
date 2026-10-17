/** Русские имена 18 семейств characterization-v1 для карточек сводки.
 *
 * Идентификаторы — FAMILY_IDS из `src/lnt/analysis_store/characterization_contract.py`;
 * формулировки дословно из выигравшего варианта «Карточки» прототипа
 * `frontend/prototypes/extended-run.html`. Неизвестный идентификатор не
 * прячется: запасной путь печатает сам id, как reasonCodes.ts печатает код.
 */

/** Идентификатор семейства → короткое русское имя для заголовка карточки. */
export const FAMILY_NAME_RU: Readonly<Record<string, string>> = {
  f01_phase_cycle: "Фазовый цикл F01",
  f02_amplitude_time_shape: "Форма амплитуды во времени",
  f03_interharmonic_tracking: "Треки интергармоник",
  f04_multicycle_periodicity: "Многоцикловая периодичность",
  f05_phase_conditioned_statistics: "Статистика по фазе",
  f06_modulation_trajectories: "Траектории модуляции",
  f07_comb_sideband_cepstrum: "Гребёнка и боковые в кепстре",
  f08_transient_morphology: "Морфология переходных",
  f09_event_ordering: "Порядок событий",
  f10_threshold_episode_surface: "Поверхность пороговых эпизодов",
  f11_conditional_distributions: "Условные распределения",
  f12_spectral_kurtosis: "Спектральный эксцесс",
  f13_band_envelope_coactivity: "Соактивность огибающих полос",
  f14_cross_channel_event_association: "Связь событий каналов A/B",
  f15_interpretable_modes: "Интерпретируемые моды",
  f16_multiscale_memory: "Память на нескольких масштабах",
  f17_cyclic_spectral_coherence: "Циклическая спектральная когерентность",
  f18_bicoherence_triads: "Бикогерентность триад",
};

/** Русское имя семейства; неизвестный id виден дословно, а не заменяется. */
export function familyNameRu(familyId: string): string {
  return FAMILY_NAME_RU[familyId] ?? familyId;
}
