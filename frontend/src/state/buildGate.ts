/** Контрольная точка идентичности сборки (build id).
 * Расхождение версии сервера — детерминированное состояние восстановления
 * с русской подсказкой перезагрузки; контролы разблокируются только после
 * успешного recover() + повторной сверки. Секреты (nonce) через гейт не текут. */

import type { LntApiClient } from "../api/client";
import { normalizeThrown } from "../api/errors";

export type BuildGateState =
  | { kind: "idle" }
  | { kind: "verifying" }
  | { kind: "ready"; buildId: string }
  | { kind: "mismatch"; message: string };

export interface BuildGate {
  getState(): BuildGateState;
  subscribe(listener: (state: BuildGateState) => void): () => void;
  /** Контролы мутаций активны только в состоянии ready. */
  isUnlocked(): boolean;
  verify(): Promise<void>;
  recover(): Promise<void>;
}

export function createBuildGate(client: LntApiClient): BuildGate {
  let state: BuildGateState = { kind: "idle" };
  const listeners = new Set<(state: BuildGateState) => void>();

  function set(next: BuildGateState): void {
    state = next;
    for (const listener of listeners) listener(next);
  }

  async function verify(): Promise<void> {
    set({ kind: "verifying" });
    try {
      await client.verifyBuild();
    } catch (error) {
      const apiError = normalizeThrown(error);
      if (apiError.kind === "build_mismatch") {
        set({ kind: "mismatch", message: apiError.message });
        return;
      }
      set({ kind: "idle" }); // сверка не состоялась — возвращаемся к исходному
      throw apiError;
    }
    set({ kind: "ready", buildId: client.currentBuildId ?? "" });
  }

  async function recover(): Promise<void> {
    // Сбой повторного bootstrap не решает исход: финальную оценку делает verify().
    try {
      await client.recover();
    } catch {
      // игнорируем: готовность определяет только сверка версий ниже
    }
    await verify();
  }

  return {
    getState: () => state,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    isUnlocked: () => state.kind === "ready",
    verify,
    recover,
  };
}
