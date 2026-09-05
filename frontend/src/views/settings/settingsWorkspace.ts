/** Рабочая область «Настройки» (#/settings): корень сессий (факт + локальная
 * заметка), диагностика устройства (T14: состояние + preflight), честная
 * инструкция сборника поддержки (HTTP-маршрута нет — только CLI), ссылки на
 * профили, сводка приватности (зеркало metadata_collector) и рецепты анализа.
 * V6 (D3=A): секции — .panel/.panel-hd/.panel-bd через panelSection(),
 * формы — .field/.ctl/.form-grid, действия — .btn в .form-actions-футерах.
 * Статическая разметка — в settingsSections.ts, здесь интерактив. */

import type { LntApiClient } from "../../api/client";
import { createDeviceApi } from "../../api/client-device";
import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { refreshProfiles, refreshRecipes } from "./settingsLists";
import { readCapturePreflightRequest } from "./settingsPreflight";
import { createRootNoteBlock } from "./settingsRootNote";
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

  const rootNote = createRootNoteBlock();
  const rootValue = el("code", { className: "t-mono lnt-set-root-value", text: "…" });
  // U2: недоступный /api/config — видимое outage-состояние с повтором,
  // а не тихая строка «недоступно» без выхода.
  const rootRetry = el("button", {
    className: "btn btn-secondary",
    text: "Повторить",
    attrs: { type: "button", id: "lnt-set-root-retry", hidden: "" },
  });
  rootRetry.addEventListener("click", () => void refreshRoot());
  const rootSection = panelSection(
    "Корень сессий",
    [
      el("p", { className: "t-body", text: "Фактический корень (GET /api/config):" }),
      rootValue,
      rootRetry,
      el("div", { className: "form-grid" }, [rootNote.field]),
      el("div", { className: "form-actions" }, [rootNote.saveButton]),
    ],
    "lnt-set-root",
  );

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

  const root = el(
    "div",
    { className: "lnt-set-workspace", attrs: { role: "region", "aria-label": "Настройки" } },
    [
      el("h2", { className: "placeholder-title t-page", text: "Настройки" }),
      rootSection,
      deviceSection,
      buildBundleSection(),
      profilesSection,
      buildPrivacySection(),
      recipesSection,
    ],
  );
  container.append(root);

  /** Факт корня с видимым outage-состоянием и объявлением восстановления. */
  async function refreshRoot(): Promise<void> {
    try {
      const config = await client.bootstrap();
      const recovered = rootRetry.getAttribute("hidden") === null;
      rootValue.textContent = config.root;
      rootValue.removeAttribute("role");
      rootRetry.setAttribute("hidden", "");
      if (recovered) announcePolite("Корень сессий загружен");
    } catch (error) {
      const message = `Корень сессий недоступен: ${error instanceof Error ? error.message : String(error)}. Проверьте, что панель запущена, и повторите.`;
      rootValue.textContent = "недоступно (сервер не отвечает)";
      rootValue.setAttribute("role", "alert");
      rootRetry.removeAttribute("hidden");
      announcePolite(message);
    }
  }

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

  /** Профили с самовосстанавливающимся повтором (U2). */
  async function loadProfiles(): Promise<void> {
    await refreshProfiles(client, profilesHost, () => void loadProfiles());
  }

  async function bootstrapAll(): Promise<void> {
    // Порядок фиксирован: успешные объявления — первыми, ошибки — последними.
    await refreshDevice();
    await refreshRoot();
    await loadProfiles();
    await refreshRecipes(client, recipesHost);
  }

  void client.ensureReady().then(
    () => void bootstrapAll(),
    () => void bootstrapAll(),
  );

  return () => undefined;
}
