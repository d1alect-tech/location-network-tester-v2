/** Задача 17 RED: пресеты задач живой вкладки — localStorage
 * lnt.live.presets.v1 (прецедент themePreference / lnt.live.meas.v1), только
 * пользовательские (встроенных дефолтов нет), имена нейтральные рабочие.
 * Снимок — ровно то, что реально staged/local: В/дел, пробник, частота,
 * триггер (режим/источник/фронт/уровень), ФНЧ, послесвечение, ряды
 * измерений. Применение — ТОЛЬКО живыми слушателями листьев
 * (applyScopeControlTargets + клики секций меню + rows.set): staged-ручки
 * помечаются «применится при следующем запуске», мгновенного применения
 * старт-ручек нет (фабрикация). Кнопка-триггер — секция меню захвата
 * (геометрия: строка 2 полосы на 1280×720 исчерпана математ-тумблером,
 * отдельная кнопка перенесла бы строку — полоса > 140). Диалог выбора —
 * stateless (Esc = без изменений). */

import { afterEach, describe, expect, it } from "vitest";
import { paintLiveChip } from "../../components/liveStrip/liveChip";
import { el } from "../../components/primitives/dom";
import {
  LIVE_PRESETS_STORAGE_KEY,
  type PresetStorageHost,
  createLivePresetStore,
} from "./livePresetStore";
import { mountLivePresets } from "./livePresets";
import { buildBwFilterMenuSection } from "./scopeBwFilter";
import type { ScopeControlHosts, ScopeControlState } from "./scopeControlState";
import { readScopeControlState } from "./scopeControlState";
import { buildScopeControls } from "./scopeControls";
import { ROW_KEYS, buildScopeMeasureSection, createMeasureRowState } from "./scopeMeasureConfig";
import { buildScopeRateField } from "./scopeRateField";
import { buildScopeTriggerSection } from "./scopeTrigger";
import { buildPersistenceMenuSection } from "./scopeWavePersistence";

/** Хост-кластер меню захвата: реальные листовые контролы + секции
 * ФНЧ/послесвечения (как монтирует scopeStrip) + ряды измерений. */
function mountHarness(): {
  host: HTMLElement;
  controls: ScopeControlHosts;
  measureRows: ReturnType<typeof createMeasureRowState>;
  rateField: ReturnType<typeof buildScopeRateField>;
  root: HTMLElement;
} {
  const controlsView = buildScopeControls(() => undefined);
  const rateField = buildScopeRateField();
  const triggerView = buildScopeTriggerSection({ onTriggerChange: () => undefined });
  const bwSection = buildBwFilterMenuSection({ current: "full", onPick: () => undefined });
  const persistSection = buildPersistenceMenuSection({ current: "off", onPick: () => undefined });
  const captureRoot = el("div", { className: "lnt-live-capture" }, [bwSection, persistSection]);
  const host = el("div", { className: "lnt-live-ctl" }, [captureRoot]);
  const measureRows = createMeasureRowState();
  const controls: ScopeControlHosts = {
    vdiv: controlsView.vdiv,
    probe: controlsView.probe,
    rate: rateField.root,
    level: triggerView.level,
    mode: triggerView.mode,
    source: triggerView.source,
    slope: triggerView.slope,
  };
  const root = el("div", {}, [
    host,
    controlsView.root,
    rateField.root,
    triggerView.root,
    buildScopeMeasureSection(measureRows).root,
  ]);
  document.body.append(root);
  return { host, controls, measureRows, rateField, root };
}

function press(root: ParentNode, selector: string): void {
  const button = root.querySelector<HTMLButtonElement>(selector);
  if (button === null) throw new Error(`нет опции ${selector}`);
  button.click();
}

afterEach(() => {
  window.localStorage.clear();
  document.body.replaceChildren();
});

describe("createLivePresetStore: localStorage lnt.live.presets.v1", () => {
  it("сохранение → перечитка новым store → удаление; ключ пустеет", () => {
    const store = createLivePresetStore();
    expect(store.list()).toEqual([]);
    store.save("рабочий", { vdiv: 1, bw: "5mhz" });
    expect(store.list()).toEqual([{ name: "рабочий", snapshot: { vdiv: 1, bw: "5mhz" } }]);
    const reloaded = createLivePresetStore();
    expect(reloaded.list()).toHaveLength(1);
    reloaded.remove("рабочий");
    expect(reloaded.list()).toEqual([]);
    expect(window.localStorage.getItem(LIVE_PRESETS_STORAGE_KEY)).toBeNull();
  });

  it("перезапись того же имени — одна запись с новым снимком", () => {
    const store = createLivePresetStore();
    store.save("имя", { vdiv: 5 });
    store.save("имя", { vdiv: 0.5 });
    expect(store.list()).toEqual([{ name: "имя", snapshot: { vdiv: 0.5 } }]);
  });

  it("мусорный JSON и невалидные записи не ломают список", () => {
    window.localStorage.setItem(LIVE_PRESETS_STORAGE_KEY, "{не json");
    expect(createLivePresetStore().list()).toEqual([]);
    window.localStorage.setItem(
      LIVE_PRESETS_STORAGE_KEY,
      JSON.stringify([{ name: 42 }, { name: "ок", snapshot: { vdiv: "мусор", bw: "xxx" } }]),
    );
    expect(createLivePresetStore().list()).toEqual([{ name: "ок", snapshot: {} }]);
  });

  it("приватный режим (localStorage кидает) — список живёт в памяти", () => {
    const win: PresetStorageHost = {
      localStorage: {
        getItem: () => {
          throw new Error("denied");
        },
        setItem: () => {
          throw new Error("denied");
        },
        removeItem: () => {
          throw new Error("denied");
        },
      },
    };
    const store = createLivePresetStore(win);
    store.save("память", { vdiv: 1 });
    expect(store.list()).toEqual([{ name: "память", snapshot: { vdiv: 1 } }]);
  });
});

describe("mountLivePresets: секция меню + stateless-диалог", () => {
  it("секция с кнопкой «Открыть…»; диалог скрыт; открытие закрывает панель меню", () => {
    const { host, controls, measureRows, root } = mountHarness();
    const presets = mountLivePresets({ controls, measureRows });
    presets.attach(host);
    root.append(presets.section);
    const dialog = root.querySelector<HTMLElement>(".lnt-live-presets");
    expect(dialog).toBeInstanceOf(HTMLElement);
    expect(dialog?.hidden).toBe(true);
    const open = root.querySelector<HTMLButtonElement>("[data-presets-open]");
    expect(open).toBeInstanceOf(HTMLButtonElement);

    // Панель меню захвата в харнессе — имитация открытого состояния.
    const panel = el("div", { className: "lnt-live-capture-menu" });
    host.querySelector(".lnt-live-capture")?.append(panel);
    open?.click();
    expect(dialog?.hidden).toBe(false);
    expect(panel.hidden).toBe(true);
    expect(document.activeElement).toBe(root.querySelector("[data-presets-name]"));
  });

  it("Esc закрывает диалог без изменений (stateless)", () => {
    const { host, controls, measureRows, root } = mountHarness();
    const presets = mountLivePresets({ controls, measureRows });
    presets.attach(host);
    root.append(presets.section);
    const dialog = root.querySelector<HTMLElement>(".lnt-live-presets");
    root.querySelector<HTMLButtonElement>("[data-presets-open]")?.click();
    expect(dialog?.hidden).toBe(false);
    dialog?.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }),
    );
    expect(dialog?.hidden).toBe(true);
    expect(createLivePresetStore().list()).toEqual([]);
  });

  it("пустое имя — видимая ошибка, ничего не сохраняется", () => {
    const { host, controls, measureRows, root } = mountHarness();
    const presets = mountLivePresets({ controls, measureRows });
    presets.attach(host);
    root.append(presets.section);
    root.querySelector<HTMLButtonElement>("[data-presets-open]")?.click();
    root.querySelector<HTMLButtonElement>("[data-presets-save]")?.click();
    const error = root.querySelector<HTMLElement>("[data-presets-error]");
    expect(error?.hidden).toBe(false);
    expect(createLivePresetStore().list()).toEqual([]);
  });

  it("снимок: все staged/local поля уходят в хранилище под именем", () => {
    const { host, controls, measureRows, rateField, root } = mountHarness();
    const presets = mountLivePresets({ controls, measureRows });
    presets.attach(host);
    root.append(presets.section);
    press(root, '#lnt-scope-vdiv [data-value="1"]');
    press(root, '#lnt-scope-probe [data-value="10"]');
    press(root, '[data-trigger-slope="falling"]');
    const level = root.querySelector<HTMLInputElement>("#lnt-scope-level");
    if (level === null) throw new Error("нет поля уровня");
    level.value = "0.5";
    press(root, "[role='option'][data-value='2000000']");
    // Статус-модель полосы помечает цель чипа (paintLiveChip); харнесс
    // повторяет её проводку — маркировка не ответственность пресетов.
    paintLiveChip(rateField.root, String(8_000_000), "2000000");
    press(root, '[data-menu-bw="1mhz"]');
    press(root, '[data-menu-persist="short"]');
    measureRows.set("vpp", false);

    root.querySelector<HTMLButtonElement>("[data-presets-open]")?.click();
    const name = root.querySelector<HTMLInputElement>("[data-presets-name]");
    if (name === null) throw new Error("нет поля имени");
    name.value = "  линия-1  ";
    name.dispatchEvent(new Event("input", { bubbles: true }));
    root.querySelector<HTMLButtonElement>("[data-presets-save]")?.click();

    const list = createLivePresetStore().list();
    expect(list).toHaveLength(1);
    expect(list[0]?.name).toBe("линия-1");
    expect(list[0]?.snapshot).toMatchObject({
      vdiv: 1,
      probe: 10,
      rateHz: 2_000_000,
      levelV: 0.5,
      slope: "falling",
      bw: "1mhz",
      persist: "short",
      measureOff: ["vpp"],
    });
  });

  it("применение: значения восстановлены ЖИВЫМИ слушателями листьев; диалог закрыт", () => {
    const { host, controls, measureRows, root } = mountHarness();
    const presets = mountLivePresets({ controls, measureRows });
    presets.attach(host);
    root.append(presets.section);
    press(root, '#lnt-scope-vdiv [data-value="1"]');
    press(root, '[data-menu-bw="1mhz"]');
    press(root, '[data-menu-persist="short"]');
    measureRows.set("vpp", false);
    root.querySelector<HTMLButtonElement>("[data-presets-open]")?.click();
    const name = root.querySelector<HTMLInputElement>("[data-presets-name]");
    if (name === null) throw new Error("нет поля имени");
    name.value = "снимок";
    root.querySelector<HTMLButtonElement>("[data-presets-save]")?.click();

    // Уходим от снимка: другие значения.
    press(root, '#lnt-scope-vdiv [data-value="0.5"]');
    press(root, '[data-menu-bw="full"]');
    press(root, '[data-menu-persist="off"]');
    measureRows.set("vpp", true);

    root.querySelector<HTMLButtonElement>("[data-presets-open]")?.click();
    root.querySelector<HTMLButtonElement>("[data-presets-apply]")?.click();

    const state: ScopeControlState = readScopeControlState(controls);
    expect(state.vdiv).toBe(1);
    expect(root.querySelector('[data-menu-bw="1mhz"]')?.getAttribute("aria-pressed")).toBe("true");
    expect(root.querySelector('[data-menu-persist="short"]')?.getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(measureRows.enabled("vpp")).toBe(false);
    expect(root.querySelector<HTMLElement>(".lnt-live-presets")?.hidden).toBe(true);
  });

  it("удаление: пресет исчезает из списка и хранилища", () => {
    const { host, controls, measureRows, root } = mountHarness();
    const presets = mountLivePresets({ controls, measureRows });
    presets.attach(host);
    root.append(presets.section);
    root.querySelector<HTMLButtonElement>("[data-presets-open]")?.click();
    const name = root.querySelector<HTMLInputElement>("[data-presets-name]");
    if (name === null) throw new Error("нет поля имени");
    name.value = "временный";
    root.querySelector<HTMLButtonElement>("[data-presets-save]")?.click();
    expect(root.querySelector("[data-presets-list]")?.textContent).toContain("временный");

    root.querySelector<HTMLButtonElement>("[data-presets-remove]")?.click();
    expect(root.querySelector("[data-presets-list]")?.textContent).not.toContain("временный");
    expect(createLivePresetStore().list()).toEqual([]);
  });

  it("dispose: слушатели сняты, узлы убраны", () => {
    const { host, controls, measureRows, root } = mountHarness();
    const presets = mountLivePresets({ controls, measureRows });
    presets.attach(host);
    root.append(presets.section);
    presets.dispose();
    expect(root.querySelector(".lnt-live-presets")).toBeNull();
    expect(root.contains(presets.section)).toBe(false);
  });
});

describe("mountLivePresets: ряды измерений", () => {
  it("measureOff содержит все выключенные ряды и только их", () => {
    const { host, controls, measureRows, root } = mountHarness();
    const presets = mountLivePresets({ controls, measureRows });
    presets.attach(host);
    root.append(presets.section);
    measureRows.set("vmax", false);
    measureRows.set("duty", false);
    root.querySelector<HTMLButtonElement>("[data-presets-open]")?.click();
    const name = root.querySelector<HTMLInputElement>("[data-presets-name]");
    if (name === null) throw new Error("нет поля имени");
    name.value = "ряды";
    root.querySelector<HTMLButtonElement>("[data-presets-save]")?.click();
    const snapshot = createLivePresetStore().list()[0]?.snapshot;
    expect(snapshot?.measureOff).toEqual(["vmax", "duty"]);
    expect(ROW_KEYS).toContain("vmax");
  });
});
