/** Хранилище пресетов задач живой вкладки (сплит из livePresets, задача 17 —
 * точка разбиения названа в коммите ДО роста модуля): контракт
 * localStorage lnt.live.presets.v1 (прецедент themePreference /
 * lnt.live.meas.v1) и терпимая разборка. Только пользовательские записи —
 * встроенных дефолтов нет; то же имя — перезапись. Мусорный JSON и битые
 * поля не ломают вкладку. Приватный режим localStorage — список живёт в
 * памяти. UI (секция меню + stateless-диалог) — в livePresets. */

import type { LiveTriggerMode, LiveTriggerSlope, LiveTriggerSource } from "../../api/types-live";
import type { BwFilterMode } from "./scopeBwFilter";
import { BW_FILTER_MODES } from "./scopeBwFilter";
import type { ScopeControlState } from "./scopeControlState";
import { ROW_KEYS } from "./scopeMeasureConfig";
import type { MeasureRowKey } from "./scopeMeasureConfig";
import type { PersistenceMode } from "./scopePersistence";
import { PERSISTENCE_MODES } from "./scopePersistence";

/** Контракт хранения (префикс lnt.live.*, версия 1). */
export const LIVE_PRESETS_STORAGE_KEY = "lnt.live.presets.v1";

export interface ScopePresetSnapshot extends ScopeControlState {
  bw?: BwFilterMode;
  persist?: PersistenceMode;
  measureOff?: MeasureRowKey[];
}

export interface LivePreset {
  name: string;
  snapshot: ScopePresetSnapshot;
}

/** Минимальный хост хранения: окно с localStorage (или его стаб). */
export type PresetStorageHost = {
  localStorage: Pick<Storage, "getItem" | "setItem" | "removeItem">;
};

export interface LivePresetStore {
  list(): LivePreset[];
  save(name: string, snapshot: ScopePresetSnapshot): void;
  remove(name: string): void;
}

const TRIGGER_MODES: readonly string[] = ["auto", "normal", "single"];
const TRIGGER_SOURCES: readonly string[] = ["ch1", "ch2"];
const TRIGGER_SLOPES: readonly string[] = ["rising", "falling"];

function finiteOrUndefined(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function enumOrUndefined<T extends string>(
  value: unknown,
  allowed: readonly string[],
): T | undefined {
  return typeof value === "string" && allowed.includes(value) ? (value as T) : undefined;
}

/** Терпимая разборка: мусорные поля молча отбрасываются — хранилище
 * пользователя не должно ломать вкладку. */
export function parseSnapshot(raw: unknown): ScopePresetSnapshot {
  const source = typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};
  const measureRaw = Array.isArray(source.measureOff) ? source.measureOff : [];
  const measureOff = measureRaw.filter(
    (key): key is MeasureRowKey =>
      typeof key === "string" && (ROW_KEYS as readonly string[]).includes(key),
  );
  return {
    vdiv: finiteOrUndefined(source.vdiv),
    probe: finiteOrUndefined(source.probe),
    rateHz: finiteOrUndefined(source.rateHz),
    levelV: finiteOrUndefined(source.levelV),
    mode: enumOrUndefined<LiveTriggerMode>(source.mode, TRIGGER_MODES),
    source: enumOrUndefined<LiveTriggerSource>(source.source, TRIGGER_SOURCES),
    slope: enumOrUndefined<LiveTriggerSlope>(source.slope, TRIGGER_SLOPES),
    bw: enumOrUndefined<BwFilterMode>(source.bw, BW_FILTER_MODES),
    persist: enumOrUndefined<PersistenceMode>(source.persist, PERSISTENCE_MODES),
    measureOff: measureOff.length === 0 ? undefined : measureOff,
  };
}

function storage(win: PresetStorageHost): PresetStorageHost["localStorage"] | null {
  try {
    return win.localStorage;
  } catch {
    return null;
  }
}

/** Хранилище пресетов: JSON-массив [{name, snapshot}]; запись с битым
 * именем пропускается; приватный режим — список живёт в памяти. */
export function createLivePresetStore(win: PresetStorageHost = window): LivePresetStore {
  const disk = storage(win);
  let memory: LivePreset[] | null = disk === null ? [] : null;
  let diskCache: LivePreset[] | null = null;

  function read(): LivePreset[] {
    if (memory !== null) return memory;
    if (diskCache !== null) return diskCache;
    if (disk === null) return [];
    let raw: unknown;
    try {
      raw = JSON.parse(disk.getItem(LIVE_PRESETS_STORAGE_KEY) ?? "null");
    } catch {
      raw = null;
    }
    const entries = Array.isArray(raw) ? raw : [];
    diskCache = entries.flatMap((entry): LivePreset[] => {
      if (typeof entry !== "object" || entry === null) return [];
      const record = entry as Record<string, unknown>;
      if (typeof record.name !== "string" || record.name.trim() === "") return [];
      return [{ name: record.name, snapshot: parseSnapshot(record.snapshot) }];
    });
    return diskCache;
  }

  function persist(next: LivePreset[]): void {
    if (memory !== null) {
      memory = next;
      return;
    }
    if (disk === null) return;
    try {
      if (next.length === 0) disk.removeItem(LIVE_PRESETS_STORAGE_KEY);
      else disk.setItem(LIVE_PRESETS_STORAGE_KEY, JSON.stringify(next));
      diskCache = next;
    } catch {
      // Квота/доступ отвалились: список остаётся в памяти этой сессии.
      memory = next;
    }
  }

  return {
    list: () => [...read()],
    save(name, snapshot) {
      const next = read().filter((preset) => preset.name !== name);
      next.push({ name, snapshot });
      persist(next);
    },
    remove(name) {
      persist(read().filter((preset) => preset.name !== name));
    },
  };
}
