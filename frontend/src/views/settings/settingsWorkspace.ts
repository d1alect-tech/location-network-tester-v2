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
import { createField } from "../../components/primitives/forms";
import { announcePolite } from "../../components/primitives/status";
import { refreshProfiles, refreshRecipes } from "./settingsLists";
import { ROOT_NOTE_MAX_LENGTH, validateRootNote } from "./settingsModel";
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

const ROOT_NOTE_KEY = "lnt-root-note";

export function mountSettingsWorkspace(
  container: HTMLElement,
  options: SettingsWorkspaceOptions,
): () => void {
  const { client } = options;
  const device = createDeviceApi(client);
  const deviceHost = el("div", { className: "lnt-set-device" });
  const preflightHost = el("div", {});
  const recipesHost = el("div", {});
  const profilesHost = el("p", { className: "t-body", text: "Загрузка профилей…" });

  const rootNoteInput = el("input", {
    className: "ctl",
    attrs: {
      type: "text",
      id: "lnt-set-root-note",
      maxlength: String(ROOT_NOTE_MAX_LENGTH),
      autocomplete: "off",
    },
  });
  const rootNoteField = createField({
    label: "Локальная заметка о корне (не меняет сервер)",
    control: rootNoteInput,
    hintText:
      "Фактический корень отдаёт сервер и меняется только перезапуском: uv run lnt ui --root <путь>. Заметка хранится локально в браузере.",
  });
  // V6-форма поверх примитива (примитив не трогаем — он общий для разделов):
  // .field для раскладки, .field-label для подписи; .lnt-field остаётся e2e-хуком.
  rootNoteField.root.classList.add("field");
  rootNoteField.root.querySelector("label")?.classList.add("field-label");
  const rootValue = el("code", { className: "t-mono lnt-set-root-value", text: "…" });
  const savedNote = readNote();
  if (savedNote !== null) rootNoteInput.value = savedNote;

  const saveButton = el("button", {
    className: "btn",
    text: "Сохранить заметку",
    attrs: { type: "button", id: "lnt-set-root-save" },
  });
  saveButton.addEventListener("click", () => saveNote());
  const rootSection = panelSection(
    "Корень сессий",
    [
      el("p", { className: "t-body", text: "Фактический корень (GET /api/config):" }),
      rootValue,
      el("div", { className: "form-grid" }, [rootNoteField.root]),
      el("div", { className: "form-actions" }, [saveButton]),
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

  function readNote(): string | null {
    try {
      return window.localStorage.getItem(ROOT_NOTE_KEY);
    } catch {
      return null;
    }
  }

  function saveNote(): void {
    const validation = validateRootNote(rootNoteInput.value);
    rootNoteField.setError(validation.error);
    if (!validation.ok) return;
    try {
      if (rootNoteInput.value.trim() === "") window.localStorage.removeItem(ROOT_NOTE_KEY);
      else window.localStorage.setItem(ROOT_NOTE_KEY, rootNoteInput.value.trim());
    } catch {
      // приватный режим: заметка живёт только в поле ввода
    }
    announcePolite("Заметка о корне сохранена локально");
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
      const report = await device.preflight({
        kind: "capture",
        channels: 2,
        sample_rate_hz: 20_000_000,
        duration_s: 2.4,
        range_v: 5,
        label: "",
        self_noise: false,
        repeat: 1,
        interval_s: 0,
        baseline_session: null,
      });
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

  void client.ensureReady().then(async () => {
    try {
      const config = await client.bootstrap();
      rootValue.textContent = config.root;
    } catch {
      rootValue.textContent = "недоступно (сервер не отвечает)";
    }
    void refreshProfiles(client, profilesHost);
    void refreshRecipes(client, recipesHost);
    void refreshDevice();
  });

  return () => undefined;
}
