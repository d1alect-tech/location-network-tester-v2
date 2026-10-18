/** Пресеты задач живой вкладки — UI (задача 17, GATE A 2026-10-18): снимок
 * настроек захвата под нейтральным именем + возврат одним нажатием
 * «Применить»; хранение — livePresetStore. Применение — ТОЛЬКО живыми
 * слушателями листьев (applyScopeControlTargets: старт-ручки staged,
 * горячий триггер config; секции меню кликами; ряды измерений rows.set):
 * мгновенного применения старт-ручек на ходу нет — это фабрикация истины
 * прибора. UI: секция «Пресеты» в меню захвата (кнопка в существующем
 * кластере задачи 21 — строка 2 полосы на 1280×720 исчерпана
 * математ-тумблером задачи 16, отдельная кнопка перенесла бы строку,
 * полоса > 140) + stateless-диалог выбора (прецедент r4: Esc/клик мимо —
 * без изменений). Модуль в views/scope, не в components: снимок
 * типизирован view-модулями, компонент не имеет права их импортировать. */

import { el } from "../../components/primitives/dom";
import { buildLivePresetDom, buildLivePresetRow } from "./livePresetDialog";
import { createLivePresetStore } from "./livePresetStore";
import type { LivePresetStore, PresetStorageHost, ScopePresetSnapshot } from "./livePresetStore";
import type { BwFilterMode } from "./scopeBwFilter";
import { BW_FILTER_MODES } from "./scopeBwFilter";
import type { ScopeControlHosts } from "./scopeControlState";
import { applyScopeControlTargets, readScopeControlState } from "./scopeControlState";
import { ROW_KEYS } from "./scopeMeasureConfig";
import type { MeasureRowState } from "./scopeMeasureConfig";
import type { PersistenceMode } from "./scopePersistence";
import { PERSISTENCE_MODES } from "./scopePersistence";

export interface LivePresetsOptions {
  controls: ScopeControlHosts;
  measureRows: MeasureRowState;
  win?: PresetStorageHost;
}

export interface LivePresetsHandle {
  /** Секция меню захвата (extras, прецедент ФНЧ/послесвечения). */
  readonly section: HTMLElement;
  /** Якорь диалога — группа «capture» полосы (.lnt-live-ctl, position:
   *  relative). Вызывается ПОСЛЕ mountScopeCaptureMenu: диалог идёт в DOM
   *  после кластера меню, поэтому «первая кнопка группы» остаётся кнопкой
   *  «Меню» (контракт scopeCaptureMenu). Внутри группы же живут секции
   *  ФНЧ/послесвечения — опции для чтения/применения живыми кликами. */
  attach(host: HTMLElement): void;
  dispose(): void;
}

/** Снимок текущего состояния: поля манифеста + локальные режимы + ряды. */
function takeSnapshot(options: LivePresetsOptions, host: HTMLElement): ScopePresetSnapshot {
  const state = readScopeControlState(options.controls);
  const bw = pressedMenuValue<BwFilterMode>(host, "data-menu-bw", BW_FILTER_MODES);
  const persist = pressedMenuValue<PersistenceMode>(host, "data-menu-persist", PERSISTENCE_MODES);
  const measureOff = ROW_KEYS.filter((key) => !options.measureRows.enabled(key));
  return {
    ...state,
    bw,
    persist,
    measureOff: measureOff.length === 0 ? undefined : measureOff,
  };
}

function pressedMenuValue<T extends string>(
  host: HTMLElement,
  attr: string,
  allowed: readonly string[],
): T | undefined {
  const button = host.querySelector<HTMLElement>(`[${attr}][aria-pressed="true"]`);
  const value = button?.getAttribute(attr);
  return value !== undefined && value !== null && allowed.includes(value)
    ? (value as T)
    : undefined;
}

/** Применение снимка: только живые слушатели листьев. */
function applyPreset(
  options: LivePresetsOptions,
  host: HTMLElement,
  snapshot: ScopePresetSnapshot,
): void {
  applyScopeControlTargets(options.controls, snapshot);
  clickMenuOption(host, "data-menu-bw", snapshot.bw);
  clickMenuOption(host, "data-menu-persist", snapshot.persist);
  const off = snapshot.measureOff ?? [];
  for (const key of ROW_KEYS) options.measureRows.set(key, !off.includes(key));
}

function clickMenuOption(host: HTMLElement, attr: string, value: string | undefined): void {
  if (value === undefined) return;
  const pressed = host
    .querySelector<HTMLElement>(`[${attr}][aria-pressed="true"]`)
    ?.getAttribute(attr);
  if (pressed === value) return;
  host.querySelector<HTMLButtonElement>(`[${attr}="${value}"]`)?.click();
}

/** Точка входа UI: секция в меню захвата + stateless-диалог (DOM —
 *  livePresetDialog). */
export function mountLivePresets(options: LivePresetsOptions): LivePresetsHandle {
  const store: LivePresetStore = createLivePresetStore(options.win ?? window);
  const dom = buildLivePresetDom();
  let host: HTMLElement | null = null;

  function closeDialog(): void {
    dom.dialog.hidden = true;
    dom.error.hidden = true;
  }

  function renderList(): void {
    dom.list.replaceChildren();
    for (const preset of store.list()) {
      const row = buildLivePresetRow(preset);
      row
        .querySelector<HTMLButtonElement>("[data-presets-apply]")
        ?.addEventListener("click", () => {
          if (host === null) return;
          applyPreset(options, host, preset.snapshot);
          closeDialog();
        });
      row
        .querySelector<HTMLButtonElement>("[data-presets-remove]")
        ?.addEventListener("click", () => {
          store.remove(preset.name);
          renderList();
        });
      dom.list.append(row);
    }
    if (dom.list.childElementCount === 0) {
      dom.list.append(
        el("p", {
          className: "t-compact lnt-live-capture-hint",
          text: "нет сохранённых пресетов",
        }),
      );
    }
  }

  function openDialog(): void {
    if (host === null) return;
    // Меню захвата закрывается (диалог — оверлей того же якоря, кластер 21).
    host.querySelector(".lnt-live-capture-menu")?.setAttribute("hidden", "");
    host.querySelector(".lnt-live-capture-btn")?.setAttribute("aria-expanded", "false");
    renderList();
    dom.dialog.hidden = false;
    dom.nameInput.value = "";
    dom.error.hidden = true;
    dom.nameInput.focus();
  }

  function onDocPointerDown(event: Event): void {
    if (dom.dialog.hidden) return;
    if (
      event.target instanceof Node &&
      (dom.dialog.contains(event.target) || dom.openButton.contains(event.target))
    ) {
      return;
    }
    closeDialog();
  }

  dom.openButton.addEventListener("click", openDialog);
  dom.dialog.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    closeDialog();
    dom.openButton.focus();
  });
  dom.saveButton.addEventListener("click", () => {
    const name = dom.nameInput.value.trim();
    if (name === "" || host === null) {
      if (name === "") dom.error.hidden = false;
      return;
    }
    store.save(name, takeSnapshot(options, host));
    dom.nameInput.value = "";
    dom.error.hidden = true;
    renderList();
    closeDialog();
  });
  document.addEventListener("pointerdown", onDocPointerDown, true);

  return {
    section: dom.section,
    attach(anchor: HTMLElement): void {
      host = anchor;
      anchor.append(dom.dialog);
    },
    dispose(): void {
      document.removeEventListener("pointerdown", onDocPointerDown, true);
      dom.dialog.remove();
      dom.section.remove();
    },
  };
}
