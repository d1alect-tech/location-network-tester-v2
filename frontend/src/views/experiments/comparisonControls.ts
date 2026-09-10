import { el } from "../../components/primitives/dom";

export function knownMetricUnits(featureKey: string): string {
  return featureKey === "needle_mean_v" || featureKey === "needle.needle_mean_v" ? "V" : "";
}

export function labeled(labelText: string, control: HTMLElement): HTMLElement {
  return el("label", { className: "lnt-field-inline field cmd-field" }, [
    el("span", { className: "lnt-label-text field-label cmd-label", text: labelText }),
    control,
  ]);
}
