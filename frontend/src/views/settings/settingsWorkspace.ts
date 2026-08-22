/** Рабочая область «Настройки» (#/settings): корень сессий (факт + локальная
 * заметка), диагностика устройства (T14: состояние + preflight), честная
 * инструкция сборника поддержки (HTTP-маршрута нет — только CLI), ссылки на
 * профили, сводка приватности (зеркало metadata_collector) и рецепты анализа.
 * Статическая разметка — в settingsSections.ts, здесь интерактив. */

import type { LntApiClient } from "../../api/client";
import { createDeviceApi } from "../../api/client-device";
import { clearElement, el } from "../../components/primitives/dom";
import { createField } from "../../components/primitives/forms";
import { announcePolite } from "../../components/primitives/status";
import { ROOT_NOTE_MAX_LENGTH, validateRootNote } from "./settingsModel";
import {
  buildBundleSection,
  buildPrivacySection,
  errorBlock,
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
  const profilesHost = el("p", { className: "lnt-helper-text", text: "Загрузка профилей…" });

  const rootNoteInput = el("input", {
    className: "lnt-input",
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
  const rootValue = el("code", { className: "lnt-rep-mono lnt-set-root-value", text: "…" });
  const savedNote = readNote();
  if (savedNote !== null) rootNoteInput.value = savedNote;

  const rootSection = el("section", { className: "lnt-set-section" }, [
    el("h3", { className: "lnt-exp-subtitle", text: "Корень сессий" }),
    el("p", { className: "lnt-helper-text", text: "Фактический корень (GET /api/config):" }),
    rootValue,
    rootNoteField.root,
  ]);
  const saveButton = el("button", {
    className: "lnt-btn",
    text: "Сохранить заметку",
    attrs: { type: "button", id: "lnt-set-root-save" },
  });
  saveButton.addEventListener("click", () => saveNote());
  rootSection.append(saveButton);

  const deviceSection = el("section", { className: "lnt-set-section" }, [
    el("h3", { className: "lnt-exp-subtitle", text: "Диагностика устройства" }),
    el("p", {
      className: "lnt-helper-text",
      text: "Состояние цепочки драйвер → устройство → прошивка (без изменения устройства). Отсутствие прибора — штатное типизированное состояние, а не ошибка.",
    }),
    deviceHost,
    el("div", { className: "lnt-exp-actions" }, [
      el("button", {
        className: "lnt-btn",
        text: "Проверить устройство",
        attrs: { type: "button", id: "lnt-set-device-check" },
      }),
      el("button", {
        className: "lnt-btn",
        text: "Проверить готовность захвата",
        attrs: { type: "button", id: "lnt-set-preflight" },
      }),
    ]),
    preflightHost,
  ]);
  deviceSection
    .querySelector("#lnt-set-device-check")
    ?.addEventListener("click", () => void refreshDevice());
  deviceSection
    .querySelector("#lnt-set-preflight")
    ?.addEventListener("click", () => void runPreflight());

  const profilesSection = el("section", { className: "lnt-set-section" }, [
    el("h3", { className: "lnt-exp-subtitle", text: "Профили" }),
    profilesHost,
    el("a", {
      className: "lnt-btn",
      text: "Открыть управление профилями в каталоге",
      attrs: { href: "#/catalog", id: "lnt-set-profiles-link" },
    }),
  ]);

  const recipesSection = el("section", { className: "lnt-set-section" }, [
    el("h3", { className: "lnt-exp-subtitle", text: "Рецепты анализа (только чтение)" }),
    el("p", {
      className: "lnt-helper-text",
      text: "Рецепты неизменяемы; удаление бэкенд отклоняет (409), потому что на рецепты могут ссылаться опубликованные артефакты.",
    }),
    recipesHost,
  ]);

  const root = el(
    "div",
    { className: "lnt-set-workspace", attrs: { role: "region", "aria-label": "Настройки" } },
    [
      el("h2", { className: "placeholder-title", text: "Настройки" }),
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
    deviceHost.append(el("p", { className: "lnt-helper-text", text: "Проверка устройства…" }));
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
    preflightHost.append(
      el("p", { className: "lnt-helper-text", text: "Проверка готовности захвата…" }),
    );
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

  async function refreshProfiles(): Promise<void> {
    try {
      const list = await client.profiles();
      profilesHost.textContent = `Зарегистрированных профилей: ${String(list.items.length)}.`;
    } catch {
      profilesHost.textContent = "Список профилей недоступен (сервер не отвечает).";
    }
  }

  async function refreshRecipes(): Promise<void> {
    clearElement(recipesHost);
    recipesHost.append(el("p", { className: "lnt-helper-text", text: "Загрузка рецептов…" }));
    try {
      const items = await client.analysis.recipes();
      clearElement(recipesHost);
      if (items.length === 0) {
        recipesHost.append(
          el("p", { className: "lnt-helper-text", text: "Рецепты не зарегистрированы." }),
        );
        return;
      }
      const list = el("ul", {
        className: "lnt-set-recipes",
        attrs: { "aria-label": "Рецепты анализа" },
      });
      for (const recipe of items) {
        list.append(
          el("li", {}, [
            el("span", { text: `${recipe.name} ` }),
            el("code", {
              className: "lnt-rep-mono",
              text: `${recipe.recipe_id} · sha256 ${recipe.sha256}`,
            }),
          ]),
        );
      }
      recipesHost.append(list);
    } catch (error) {
      clearElement(recipesHost);
      recipesHost.append(
        errorBlock(
          `Список рецептов недоступен: ${error instanceof Error ? error.message : String(error)}`,
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
    void refreshProfiles();
    void refreshRecipes();
    void refreshDevice();
  });

  return () => undefined;
}
