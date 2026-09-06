/** Рабочая область «Настройки» (#/settings): корень сессий (факт + локальная
 * заметка), диагностика устройства (T14: состояние + preflight), бэкап
 * и сборник поддержки (D2: задачи backup/support_bundle через POST /api/jobs
 * с SSE-прогрессом; CLI остаётся запасным путём), ссылки на
 * профили, сводка приватности (зеркало metadata_collector) и рецепты анализа.
 * V6 (D3=A): секции — .panel/.panel-hd/.panel-bd через panelSection(),
 * формы — .field/.ctl/.form-grid, действия — .btn в .form-actions-футерах.
 * Статическая разметка — в settingsSections.ts, здесь интерактив. */

import type { LntApiClient } from "../../api/client";
import { createDeviceApi } from "../../api/client-device";
import type { JobSnapshot } from "../../api/types-jobs";
import { watchJobEvents } from "../../capture/sse";
import type { WatchHandle } from "../../capture/sse";
import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { refreshProfiles, refreshRecipes } from "./settingsLists";
import type { BundleJobKind } from "./settingsModel";
import { bundleDone, bundleFailed, bundleFile, bundleRunning } from "./settingsModel";
import { readCapturePreflightRequest } from "./settingsPreflight";
import { createRootSection } from "./settingsRootSection";
import {
  buildBundleSection,
  buildPrivacySection,
  errorBlock,
  panelSection,
  renderDeviceState,
  renderPreflight,
} from "./settingsSections";
import "./settings.css";

export interface SettingsWorkspaceOptions {
  client: LntApiClient;
}

export function mountSettingsWorkspace(
  container: HTMLElement,
  options: SettingsWorkspaceOptions,
): () => void {
  const { client } = options;
  const device = createDeviceApi(client);
  const deviceHost = el("div", { className: "lnt-set-device" });
  const preflightHost = el("div", {});
  const recipesHost = el("div", {});
  const profilesHost = el("div", { className: "t-body", text: "Загрузка профилей…" });

  const rootSection = createRootSection(client);

  const checkDeviceButton = el("button", {
    className: "btn",
    text: "Проверить устройство",
    attrs: { type: "button", id: "lnt-set-device-check" },
  });
  const preflightButton = el("button", {
    className: "btn btn-secondary",
    text: "Проверить готовность захвата",
    attrs: { type: "button", id: "lnt-set-preflight" },
  });
  checkDeviceButton.addEventListener("click", () => void refreshDevice());
  preflightButton.addEventListener("click", () => void runPreflight());
  const deviceSection = panelSection(
    "Диагностика устройства",
    [
      el("p", {
        className: "t-body",
        text: "Состояние цепочки драйвер → устройство → прошивка (без изменения устройства). Отсутствие прибора — штатное типизированное состояние, а не ошибка.",
      }),
      deviceHost,
      el("div", { className: "form-actions" }, [checkDeviceButton, preflightButton]),
      preflightHost,
    ],
    "lnt-set-diagnostics",
  );

  const profilesSection = panelSection(
    "Профили",
    [
      profilesHost,
      el("div", { className: "form-actions" }, [
        el("a", {
          className: "btn btn-secondary",
          text: "Открыть управление профилями в каталоге",
          attrs: { href: "#/catalog", id: "lnt-set-profiles-link" },
        }),
      ]),
    ],
    "lnt-set-profiles",
  );

  const recipesSection = panelSection(
    "Рецепты анализа (только чтение)",
    [
      el("p", {
        className: "t-body",
        text: "Рецепты неизменяемы; удаление бэкенд отклоняет (409), потому что на рецепты могут ссылаться опубликованные артефакты.",
      }),
      recipesHost,
    ],
    "lnt-set-recipes-section",
  );

  const bundleSection = buildBundleSection();
  const bundleStatus = bundleSection.querySelector("#lnt-set-bundle-status");
  for (const [id, kind] of [
    ["lnt-set-backup-run", "backup"],
    ["lnt-set-bundle-run", "support_bundle"],
  ] as const) {
    const button = bundleSection.querySelector(`#${id}`);
    if (button instanceof HTMLButtonElement) {
      button.addEventListener("click", () => void runBundleJob(kind, button));
    }
  }

  const root = el(
    "div",
    { className: "lnt-set-workspace", attrs: { role: "region", "aria-label": "Настройки" } },
    [
      el("h2", { className: "placeholder-title t-page", text: "Настройки" }),
      rootSection.section,
      deviceSection,
      bundleSection,
      profilesSection,
      buildPrivacySection(),
      recipesSection,
    ],
  );
  container.append(root);

  async function refreshDevice(): Promise<void> {
    clearElement(deviceHost);
    deviceHost.append(el("p", { className: "t-compact", text: "Проверка устройства…" }));
    try {
      const state = await device.state();
      clearElement(deviceHost);
      deviceHost.append(renderDeviceState(state));
      announcePolite(`Устройство: ${state.description_ru}`);
    } catch (error) {
      clearElement(deviceHost);
      deviceHost.append(
        errorBlock(
          `Не удалось получить состояние устройства: ${error instanceof Error ? error.message : String(error)}. Проверьте, что панель запущена, и повторите.`,
        ),
      );
    }
  }

  async function runPreflight(): Promise<void> {
    clearElement(preflightHost);
    preflightHost.append(el("p", { className: "t-compact", text: "Проверка готовности захвата…" }));
    try {
      // U3 BIND: запрос собирается из живой формы захвата, а не из хардкода.
      const report = await device.preflight(readCapturePreflightRequest());
      clearElement(preflightHost);
      preflightHost.append(renderPreflight(report));
      announcePolite(report.ready ? "Захват готов к запуску" : "Захват заблокирован проверкой");
    } catch (error) {
      clearElement(preflightHost);
      preflightHost.append(
        errorBlock(
          `Предстартовая проверка не выполнена: ${error instanceof Error ? error.message : String(error)}`,
        ),
      );
    }
  }

  let bundleStream: WatchHandle | null = null;

  function clearBundleErrors(): void {
    for (const old of bundleSection.querySelectorAll(".lnt-set-error")) old.remove();
  }

  /** D2: бэкап/сборник — ensureReady → disable → start → SSE с poll fallback. */
  async function runBundleJob(kind: BundleJobKind, button: HTMLButtonElement): Promise<void> {
    const running = bundleRunning(kind);
    const fail = (reason: string): void => {
      const text = bundleFailed(kind, reason);
      clearBundleErrors();
      bundleSection.append(errorBlock(text));
      if (bundleStatus !== null) bundleStatus.textContent = text;
      announcePolite(text);
      button.disabled = false;
    };
    const onSnapshot = (snapshot: JobSnapshot): void => {
      if (snapshot.status === "succeeded") {
        const done = bundleDone(kind, bundleFile(snapshot.result));
        clearBundleErrors();
        if (bundleStatus !== null) bundleStatus.textContent = done;
        announcePolite(done);
        button.disabled = false;
      } else if (snapshot.status === "failed") {
        fail(snapshot.error_message ?? snapshot.error_code ?? "причина неизвестна");
      }
    };
    button.disabled = true;
    clearBundleErrors();
    if (bundleStatus !== null) bundleStatus.textContent = running;
    announcePolite(running);
    try {
      await client.ensureReady();
      const first = await client.jobs.start({ kind });
      onSnapshot(first);
      bundleStream?.close();
      bundleStream = watchJobEvents(
        first.job_id,
        { onSnapshot, onConnection: () => undefined },
        { pollSnapshot: () => client.jobs.get(first.job_id) },
      );
    } catch (error) {
      fail(error instanceof Error ? error.message : String(error));
    }
  }

  /** Профили с самовосстанавливающимся повтором (U2). */
  async function loadProfiles(): Promise<void> {
    await refreshProfiles(client, profilesHost, () => void loadProfiles());
  }

  async function bootstrapAll(): Promise<void> {
    // Порядок фиксирован: успешные объявления — первыми, ошибки — последними.
    await refreshDevice();
    await rootSection.refresh();
    await loadProfiles();
    await refreshRecipes(client, recipesHost);
  }

  void client.ensureReady().then(
    () => void bootstrapAll(),
    () => void bootstrapAll(),
  );

  return () => {
    bundleStream?.close();
  };
}
