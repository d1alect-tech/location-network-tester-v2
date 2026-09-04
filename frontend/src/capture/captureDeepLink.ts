/** Deep-link предзаполнение формы capture из параметров маршрута (C1).
 * Ключи повторяют контракт бэкенда (duration_s, sample_rate_hz, range_v),
 * значения — сырые строки: валидация остаётся за validateCaptureForm,
 * здесь только отсев заведомо чужого (неизвестный mode/source/range).
 * Применение идёт через зашитые селекторы modeForm (input[name=…] пинятся
 * e2e capture.spec.ts); modeForm при этом не меняется (бюджет LOC). */

import { CAPTURE_MODE_IDS } from "./modes";
import type { CaptureModeId, CaptureSource } from "./modes";

export interface CapturePrefill {
  readonly modeId?: CaptureModeId;
  readonly source?: CaptureSource;
  readonly durationS?: string;
  readonly sampleRateHz?: string;
  readonly rangeV?: string;
  readonly label?: string;
}

const RANGE_VALUES = new Set(["5", "1", "0.5"]);

function nonEmpty(value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  const trimmed = value.trim();
  return trimmed === "" ? undefined : value;
}

export function captureParamsToPrefill(params: Record<string, string>): CapturePrefill {
  const prefill: Record<string, string> = {};
  const mode = params.mode;
  if (mode !== undefined && (CAPTURE_MODE_IDS as readonly string[]).includes(mode)) {
    prefill.modeId = mode;
  }
  const source = params.source;
  if (source === "simulator" || source === "device") prefill.source = source;
  const range = params.range_v;
  if (range !== undefined && RANGE_VALUES.has(range.trim())) prefill.rangeV = range.trim();
  const duration = nonEmpty(params.duration_s);
  if (duration !== undefined) prefill.durationS = duration;
  const rate = nonEmpty(params.sample_rate_hz);
  if (rate !== undefined) prefill.sampleRateHz = rate;
  const label = nonEmpty(params.label);
  if (label !== undefined) prefill.label = label;
  return prefill as CapturePrefill;
}

function setRadio(root: ParentNode, name: string, value: string): void {
  const radio = root.querySelector(`input[name="${name}"][value="${value}"]`);
  if (radio instanceof HTMLInputElement) radio.checked = true;
}

function setValue(root: ParentNode, name: string, value: string): void {
  const field = root.querySelector(`[name="${name}"]`);
  if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement) {
    field.value = value;
  }
}

function touch(root: ParentNode, name: string): void {
  const field = root.querySelector(`[name="${name}"]`);
  if (field instanceof HTMLElement) {
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }
}

export function applyCapturePrefill(root: HTMLElement, prefill: CapturePrefill): void {
  if (prefill.modeId !== undefined) {
    setRadio(root, "capture-mode", prefill.modeId);
    touch(root, "capture-mode");
  }
  if (prefill.source !== undefined) {
    setRadio(root, "capture-source", prefill.source);
    touch(root, "capture-source");
  }
  if (prefill.durationS !== undefined) setValue(root, "duration_s", prefill.durationS);
  if (prefill.sampleRateHz !== undefined) setValue(root, "sample_rate_hz", prefill.sampleRateHz);
  if (prefill.rangeV !== undefined) setValue(root, "range_v", prefill.rangeV);
  if (prefill.label !== undefined) setValue(root, "label", prefill.label);
  root.dispatchEvent(new Event("change", { bubbles: false }));
}
