/** Экранные настройки и независимые смещения каналов, без изменения payload. */
import { DEFAULT_SCOPE_SETTINGS, type ScopeDisplaySettings } from "./scopeScale";
import type { ScopeGroundBridge } from "./scopeWorkspaceHosts";

export function createScopeDisplayState(repaint: (settings: ScopeDisplaySettings) => void) {
  let settings = { ...DEFAULT_SCOPE_SETTINGS };
  function apply(next: ScopeDisplaySettings): void {
    settings = { ...next, groundCh1V: settings.groundCh1V, groundCh2V: settings.groundCh2V };
    repaint(settings);
  }
  const ground: ScopeGroundBridge = {
    read: () => ({ ch1V: settings.groundCh1V, ch2V: settings.groundCh2V }),
    write: (channel, volts) => {
      settings = { ...settings, [channel === "ch1" ? "groundCh1V" : "groundCh2V"]: volts };
      repaint(settings);
    },
  };
  return { read: () => settings, apply, ground };
}
