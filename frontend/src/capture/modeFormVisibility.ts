/** Видимость полей формы по режиму и источнику: текст проекции каналов,
 * строка базовой сессии, профиль симуляции и секция декларации адаптера
 * (только ripple-режим с осциллографом). Вынесено из modeForm.ts без
 * изменения поведения прежних целей — сплит под потолок 250 чистых LOC. */

import type { CaptureModeDef, CaptureSource } from "./modes";

/** Узлы, которыми управляет видимость; все принадлежат modeFormFields,
 * кроме секции адаптера (adapterDeclarationForm). */
export interface ModeVisibilityTargets {
  readonly channelsText: HTMLElement;
  readonly baselineWrap: HTMLElement;
  readonly profileFieldRoot: HTMLElement;
  /** Секция декларации адаптера: N7, видна только ripple+device. */
  readonly adapterSection: HTMLElement;
}

/** Одна точка правды: что показывает форма при текущем режиме и источнике. */
export function syncModeVisibility(
  mode: CaptureModeDef,
  source: CaptureSource,
  targets: ModeVisibilityTargets,
): void {
  targets.channelsText.textContent =
    mode.channels === 2 ? "Каналы: 2 (CH1 + CH2)" : "Каналы: 1 (только CH1)";
  targets.baselineWrap.hidden = !mode.usesBaseline;
  targets.profileFieldRoot.hidden = source !== "simulator";
  targets.adapterSection.hidden = mode.id !== "ripple_measurement" || source !== "device";
}
