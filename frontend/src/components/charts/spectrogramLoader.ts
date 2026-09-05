/** Загрузчик артефакта спектрограммы (C2-лист): loadArtifact с гонко-защитой
 * уровня (поколение + Abort) и типизированными U3-ошибками (404-баннер
 * с повтором). Вынесен из spectrogramPanel.ts без изменения поведения;
 * лист без обратного импорта панели. */

import type { LntApiClient } from "../../api/client";
import type { CandidateEventPayload } from "../../api/types-analysis";
import { readNpzArrays } from "./npz";
import type { SpectrogramLevel } from "./spectrogramModel";
import { levelFromNpz } from "./spectrogramSetup";

export interface SpectrogramArtifactDeps {
  client: Pick<LntApiClient, "analysis">;
  showError(message: string, onRetry?: () => void): void;
  hideError(): void;
  resetStatus(): void;
  applyInitialTile(
    level: SpectrogramLevel,
    events: readonly CandidateEventPayload[],
  ): Promise<void> | void;
}

export interface SpectrogramArtifactLoaderHandle {
  load(session: string, key: string): Promise<void>;
  dispose(): void;
}

export function createSpectrogramArtifactLoader(
  deps: SpectrogramArtifactDeps,
): SpectrogramArtifactLoaderHandle {
  let loadGeneration = 0;
  let loadAbort = new AbortController();

  async function load(session: string, key: string): Promise<void> {
    // Гонко-защита загрузки уровня (паттерн createTileLoader): устаревший
    // ответ отбрасывается по поколению, прежний полёт обрывается Abort'ом.
    const generation = ++loadGeneration;
    loadAbort.abort();
    loadAbort = new AbortController();
    const signal = loadAbort.signal;
    deps.hideError();
    deps.resetStatus();
    try {
      const [bytes, inventory] = await Promise.all([
        deps.client.analysis.artifactBytes(session, key, "spectrogram.npz", { signal }),
        deps.client.analysis.events(session, key, { signal }),
      ]);
      if (generation !== loadGeneration) return; // устаревшая загрузка — игнорируем
      const parsed = levelFromNpz(
        await readNpzArrays(bytes, ["time_s", "frequency_hz", "power_db"]),
      );
      await deps.applyInitialTile(parsed, inventory.events);
    } catch (error) {
      if (generation !== loadGeneration || isAbort(error)) return;
      if (
        typeof error === "object" &&
        error !== null &&
        (error as { status?: unknown }).status === 404
      ) {
        deps.showError("Сессия или артефакт анализа не найден.", () => {
          void load(session, key);
        });
        return;
      }
      deps.showError(error instanceof Error ? error.message : String(error));
    }
  }

  return {
    load,
    dispose() {
      loadAbort.abort();
      loadGeneration += 1;
    },
  };
}

function isAbort(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { name?: unknown }).name === "AbortError"
  );
}
