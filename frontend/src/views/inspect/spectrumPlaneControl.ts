/** Контрол плоскости спектра scope/input-referred: тумблер, RBW-подпись,
 * disable-правило по квалификации входа. Селекторы и поведение 1-в-1
 * с прежним блоком spectrumPanelV6 (выделено по политике test_module_size). */

import type {
  InputReferredSpectrumPayload,
  SpectrumPayload,
  SpectrumPlane,
} from "../../api/types-plots";
import { el } from "../../components/primitives/dom";

/** ENBW окна Ханна: RBW ≈ 1.5 × df. df — только из payload-поля resolution_hz
 * (шаг полной сетки анализа), НЕ из децимированной сетки frequency_hz. */
export const HANN_ENBW = 1.5;

const ruCompact = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

/** «RBW ≈ X Гц» из честного df; null — подписи нет ( hidden ). */
export function formatRbw(resolutionHz: unknown): string | null {
  if (typeof resolutionHz !== "number" || !Number.isFinite(resolutionHz) || resolutionHz <= 0) {
    return null;
  }
  return `RBW ≈ ${ruCompact.format(HANN_ENBW * resolutionHz)} Гц`;
}

export type InputReferenceInfo = { readonly status: string | null; readonly reason: string | null };

/** Квалификация входа из detail().analysis.ch1_input_reference (открытый объект бэкенда). */
export function inputReferenceOf(analysis: unknown): InputReferenceInfo {
  if (typeof analysis !== "object" || analysis === null) return { status: null, reason: null };
  const reference = Reflect.get(analysis, "ch1_input_reference");
  if (typeof reference !== "object" || reference === null) return { status: null, reason: null };
  const status = Reflect.get(reference, "status");
  const reason = Reflect.get(reference, "reason_code");
  return {
    status: typeof status === "string" ? status : null,
    reason: typeof reason === "string" ? reason : null,
  };
}

export function isPlane(value: string | null): value is SpectrumPlane {
  return value === "scope" || value === "input-referred";
}

/** Входная плоскость маппится на scope-контракт: excess-PSD тоже В²/Гц. */
export function planePayload(
  payload: SpectrumPayload | InputReferredSpectrumPayload,
): SpectrumPayload {
  if ("psd_v2_per_hz" in payload) return payload;
  return {
    frequency_hz: [...payload.frequency_hz],
    psd_v2_per_hz: [...payload.input_referred_excess_psd_v2_per_hz],
    point_count: payload.point_count,
    resolution_hz: payload.resolution_hz,
  };
}

export type PlaneControl = {
  readonly toggle: HTMLElement;
  readonly rbw: HTMLElement;
  plane(): SpectrumPlane;
  /** Disable-правило по квалификации; без входа плоскость возвращается на скоп. */
  paintPlane(analysis: unknown): void;
  paintRbw(payload: SpectrumPayload | null): void;
  /** Запрос смены плоскости: false — смена отклонена, панель не перезагружается. */
  requestPlane(next: SpectrumPlane): boolean;
};

const SCOPE_TITLE = "Плоскость осциллографа";
const REFERRED_TITLE = "Input-referred excess-PSD на входе CH1";

export function createPlaneControl(onAccept?: () => void): PlaneControl {
  let plane: SpectrumPlane = "scope";
  let referredEnabled = false;

  const scopeBtn = el("button", {
    className: "btn-quiet plane-btn",
    text: "Скоп",
    attrs: {
      type: "button",
      "data-spectrum-plane": "scope",
      "aria-pressed": "true",
      title: SCOPE_TITLE,
    },
  }) as HTMLButtonElement;
  const referredBtn = el("button", {
    className: "btn-quiet plane-btn",
    text: "Вход",
    attrs: {
      type: "button",
      "data-spectrum-plane": "input-referred",
      "aria-pressed": "false",
      title: REFERRED_TITLE,
    },
  }) as HTMLButtonElement;
  const toggle = el(
    "div",
    { className: "plane-toggle", attrs: { role: "group", "aria-label": "Плоскость спектра" } },
    [scopeBtn, referredBtn],
  );
  const rbw = el("span", {
    className: "plane-rbw num",
    attrs: {
      "data-spectrum-rbw": "",
      hidden: "",
      title: "Полоса разрешения ≈ 1.5 × df (окно Ханна, ENBW)",
    },
  });

  function paintPressed(): void {
    scopeBtn.setAttribute("aria-pressed", String(plane === "scope"));
    referredBtn.setAttribute("aria-pressed", String(plane === "input-referred"));
  }

  scopeBtn.addEventListener("click", () => {
    if (control.requestPlane("scope")) onAccept?.();
  });
  referredBtn.addEventListener("click", () => {
    if (control.requestPlane("input-referred")) onAccept?.();
  });

  const control: PlaneControl = {
    toggle,
    rbw,
    plane: () => plane,
    paintPlane(analysis) {
      const info = inputReferenceOf(analysis);
      referredEnabled = info.status === "available";
      referredBtn.disabled = !referredEnabled;
      referredBtn.title = referredEnabled
        ? REFERRED_TITLE
        : (info.reason ?? "input-reference недоступен");
      if (!referredEnabled) plane = "scope";
      paintPressed();
    },
    paintRbw(payload) {
      const text = payload === null ? null : formatRbw(payload.resolution_hz);
      if (text === null) {
        rbw.textContent = "";
        rbw.setAttribute("hidden", "");
        return;
      }
      rbw.textContent = text;
      rbw.removeAttribute("hidden");
    },
    requestPlane(next) {
      if (next === plane) return false;
      if (next === "input-referred" && !referredEnabled) return false;
      plane = next;
      paintPressed();
      return true;
    },
  };
  return control;
}
