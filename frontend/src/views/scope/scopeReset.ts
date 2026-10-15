/** «Сброс» (задача 15, план (c)): манифест-контролы возвращаются к
 * дефолтам DEFAULT_LIVE_START_REQUEST — В/дел 5, пробник ×1, частота
 * 8 МГц, уровень 0 В, триггер авто/CH1/подъём — только через живые
 * слушатели DOM (scopeControlState): staged-реестр полосы гаснет той же
 * дорожкой (клик дефолта = отклонение от baseline снимает маркировку),
 * Run читает возвращённые значения. Эхо «манифест → дефолт»; перезапуска
 * сброс НЕ делает — только значения. */

import { DEFAULT_LIVE_START_REQUEST } from "../../api/types-live";
import { el } from "../../components/primitives/dom";
import { applyScopeControlTargets } from "./scopeControlState";
import type { ScopeControlHosts, ScopeControlTargets } from "./scopeControlState";

export interface ScopeResetOptions {
  /** Группа [data-action="reset"] зоны ИЗМЕР (кнопка живёт здесь). */
  host: HTMLElement;
  hosts: ScopeControlHosts;
  /** Слот эха в статус-зоне полосы (10 px, эллипсис). */
  echo: HTMLElement;
}

export interface ScopeResetHandle {
  dispose(): void;
}

const MANIFEST_DEFAULTS: ScopeControlTargets = {
  vdiv: 5,
  probe: 1,
  rateHz: DEFAULT_LIVE_START_REQUEST.sample_rate_hz,
  levelV: 0,
  mode: "auto",
  source: "ch1",
  slope: "rising",
};

export function mountScopeReset(options: ScopeResetOptions): ScopeResetHandle {
  const button = el("button", {
    className: "lnt-live-action-btn",
    text: "Сброс",
    attrs: { type: "button" },
  });
  options.host.append(button);

  function run(): void {
    applyScopeControlTargets(options.hosts, MANIFEST_DEFAULTS);
    // Клик опции частоты фокусирует чип — фокус возвращается кнопке.
    button.focus();
    options.echo.textContent = "Сброс: манифест → дефолт";
    options.echo.hidden = false;
  }

  button.addEventListener("click", run);

  return {
    dispose: () => {
      button.removeEventListener("click", run);
      button.remove();
    },
  };
}
