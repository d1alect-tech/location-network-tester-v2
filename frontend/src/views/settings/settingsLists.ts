/** Асинхронные списки рабочей области «Настройки» (T11: выделено из
 * settingsWorkspace — было 252 чистых LOC). Профили (счётчик + ссылка на
 * каталог уже в workspace) и рецепты анализа (только чтение); сюда приходят
 * клиент и хост, интерактив остаётся в workspace. Без смены текстов. */

import type { LntApiClient } from "../../api/client";
import { clearElement, el } from "../../components/primitives/dom";
import { errorBlock } from "./settingsSections";

export async function refreshProfiles(
  client: LntApiClient,
  profilesHost: HTMLElement,
): Promise<void> {
  try {
    const list = await client.profiles();
    profilesHost.textContent = `Зарегистрированных профилей: ${String(list.items.length)}.`;
  } catch {
    profilesHost.textContent = "Список профилей недоступен (сервер не отвечает).";
  }
}

export async function refreshRecipes(
  client: LntApiClient,
  recipesHost: HTMLElement,
): Promise<void> {
  clearElement(recipesHost);
  recipesHost.append(el("p", { className: "t-compact", text: "Загрузка рецептов…" }));
  try {
    const items = await client.analysis.recipes();
    clearElement(recipesHost);
    if (items.length === 0) {
      recipesHost.append(el("p", { className: "t-body", text: "Рецепты не зарегистрированы." }));
      return;
    }
    const list = el("ul", {
      className: "lnt-set-recipes",
      attrs: { "aria-label": "Рецепты анализа" },
    });
    for (const recipe of items) {
      list.append(
        el("li", { className: "t-body" }, [
          el("span", { text: `${recipe.name} ` }),
          el("code", {
            className: "t-mono",
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
