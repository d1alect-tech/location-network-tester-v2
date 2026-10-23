/**
 * Закреплённое зеркало номиналов адаптера из `src/lnt/ripple/adapter.py`.
 * Числа меняются только парой: Python-источник + этот файл; дрейф ловит
 * `tests/test_adapter_preset_mirror.py` (идиома corpus ↔ mockGolden).
 * Пресет закреплён во фронтенде и никогда не приходит с бэкенда (H9).
 */
export const ADAPTER_PRESET = {
  capNfNominal: 100,
  seriesROhmNominal: 0,
  probeMultiplier: 1,
  rinOhm: 1_000_000,
  settlingTauMultiple: 10,
  topologyId: "series_c_at_dut_tip_x1_v1",
} as const;

/** Зеркало `NPERSEG_POLICY_HZ` из `src/lnt/analysis_v2/ripple_options.py`. */
const NPERSEG_POLICY_HZ = 1;

/**
 * τ = (RIN + Rs)·C·1e-9, установление = 10τ. Пробник фиксирован x1, поэтому
 * null-ветка недостижима; тип допускает зеркало Python-контракта.
 */
export function settlingSeconds(capNf: number, seriesROhm: number): number | null {
  const tau = (ADAPTER_PRESET.rinOhm + seriesROhm) * capNf * 1e-9;
  return ADAPTER_PRESET.settlingTauMultiple * tau;
}

/**
 * Пол анализа: (settleSamples + nperseg) / fs, где settleSamples = ceil(fs·10τ),
 * nperseg = round(fs / NPERSEG_POLICY_HZ). Зеркало происхождения пола
 * «insufficient_samples» из `src/lnt/analysis_v2/ripple_blocks.py`.
 */
export function analysisFloorSeconds(
  capNf: number,
  seriesROhm: number,
  sampleRateHz: number,
): number | null {
  const settling = settlingSeconds(capNf, seriesROhm);
  if (settling === null) {
    return null;
  }
  const settleSamples = Math.ceil(sampleRateHz * settling);
  const nperseg = Math.round(sampleRateHz / NPERSEG_POLICY_HZ);
  return (settleSamples + nperseg) / sampleRateHz;
}
