/** Композиция живого чипа риппла (todo 9): readout-секция «Поток» + чип
 * полного тракта. Чип монтируется ОВЕРЛЕЕМ в стекло осциллографа
 * (scopeScreen overlay — абсолютный слой, нулевой след в раскладке), а не в
 * узкий 300px рельс и не в строку ярлыков (её рост просаживает
 * экран-доминанту AC3 на 1280×625). Воркспейс получает ОДИН хэндл: кадры
 * идут в показания секции, событие ripple и состояние владения — в чип,
 * индикатор соединения обновляется колбэком onConnection. */

import type { LiveFramePayload, LiveRipplePayload, LiveStatePayload } from "../../api/types-live";
import { mountScopeRippleChip } from "./scopeRippleChip";
import { buildScopeReadoutSection } from "./scopeSections";

export interface ScopeRippleReadoutHandle {
  readonly root: HTMLElement;
  /** Корень секции «Поток» (показания кадра + соединение). */
  readonly connection: HTMLElement;
  /** Корень чипа риппла: воркспейс передаёт его в overlay стекла. */
  readonly rippleRow: HTMLElement;
  applyFrame(frame: LiveFramePayload): void;
  /** Событие ripple: валидный снимок или null (битое — числа гаснут). */
  applyRipple(payload: LiveRipplePayload | null): void;
  /** Состояние владения: переход в running = новая эпоха, числа гаснут. */
  applyLiveState(state: LiveStatePayload): void;
  /** Индикатор соединения и текст строки соединения одним событием. */
  setConnection(kind: "live" | "reconnecting"): void;
  dispose(): void;
}

export function mountScopeRippleReadout(): ScopeRippleReadoutHandle {
  const chip = mountScopeRippleChip();
  const view = buildScopeReadoutSection();
  return {
    root: view.root,
    connection: view.connection,
    rippleRow: chip.root,
    applyFrame: (frame) => view.applyFrame(frame),
    applyRipple: (payload) => chip.apply(payload),
    applyLiveState: (state) => chip.applyLiveState(state),
    // Ошибка транспорта гасит числа чипа сразу: реконнект сам их не
    // возвращает, это делает только следующее ripple-событие текущей эпохи.
    // Здесь же обновляется индикатор соединения.
    setConnection: (kind) => {
      if (kind === "reconnecting") chip.invalidate();
      view.connection.textContent = kind === "live" ? "передача данных" : "переподключение…";
    },
    dispose: () => chip.dispose(),
  };
}
