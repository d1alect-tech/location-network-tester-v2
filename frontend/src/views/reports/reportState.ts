import { knownMetricUnits } from "../../api/sessionMetrics";
import type { ExperimentDetail } from "../experiments/experimentsStore";

export function reportFeatureKey(detail: ExperimentDetail): string {
  return String(detail.experiment.primary_estimands?.[0]?.feature_key ?? "").trim();
}

export function resetReportResult(
  detailHost: HTMLElement,
  downloadButton: HTMLButtonElement,
  clearMarkdown: () => void,
): void {
  clearMarkdown();
  detailHost.querySelector(".lnt-rep-preview")?.remove();
  downloadButton.disabled = true;
  downloadButton.title = "Станет доступна после сборки отчёта";
}

export function setReportUnits(detail: ExperimentDetail, unitsInput: HTMLInputElement): void {
  unitsInput.value = knownMetricUnits(reportFeatureKey(detail)) ?? "";
  unitsInput.placeholder = unitsInput.value === "" ? "Укажите единицы" : "";
}
