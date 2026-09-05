/** Менеджер профилей V6: панель .panel, виды — disclosure .disc-toggle/
 * .disc-body, предпросмотр — .frame, кнопки .btn/.btn-quiet, ошибка —
 * .banner.banner-inline. CRUD локаций, оборудования, фронтенда, трансформатора
 * и условий измерения + выбор комбинации для предпросмотра снимка захвата.
 * Мутации идут через api-клиент (nonce), состояния pending/success/failure
 * блокируют кнопки; ошибки — русские тексты, не console.
 * Поля форм — в profileFormFields, диалоги — в profileDialogs, список и
 * строки — в profileList (C2); здесь каркас, состояние комбинации,
 * mutate/notify и загрузчик. */

import type { LntApiClient } from "../../api/client";
import { normalizeThrown } from "../../api/errors";
import type { ProfileRevision } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { createResourceLoader } from "../../state/resource";
import type { ProfileDialogContext } from "./profileDialogs";
import { openCreateDialog, openEditDialog } from "./profileDialogs";
import type { ProfileListDeps } from "./profileList";
import { renderList } from "./profileList";
import type { ProfileCombination } from "./profilePreview";

export interface ProfileManagerOptions {
  client: LntApiClient;
  onCombinationChange: (combination: ProfileCombination) => void;
}

export interface ProfileManagerHandle {
  root: HTMLElement;
  reload(): Promise<void>;
}

export function createProfileManager(options: ProfileManagerOptions): ProfileManagerHandle {
  const { client, onCombinationChange } = options;
  const combination: ProfileCombination = {};
  const loader = createResourceLoader<{ items: ProfileRevision[] }>(() => client.profiles());

  const listHost = el("div", { className: "cat-profile-list" });
  const errorNote = el("div", { className: "banner banner-inline", attrs: { role: "alert" } });
  errorNote.hidden = true;
  const createButton = el("button", {
    className: "btn",
    text: "Создать профиль",
    attrs: { type: "button" },
  });

  function setError(message: string): void {
    errorNote.textContent = message;
    errorNote.hidden = message === "";
  }

  function notify(): void {
    onCombinationChange({ ...combination });
  }

  async function mutate(action: () => Promise<unknown>, busyHost: HTMLElement): Promise<void> {
    setError("");
    const buttons = busyHost.querySelectorAll<HTMLButtonElement>("button");
    for (const button of buttons) button.disabled = true;
    try {
      await client.ensureReady();
      await action();
      await loader.load("profiles");
      notify();
    } catch (error) {
      const apiError = normalizeThrown(error);
      setError(apiError.message);
    } finally {
      for (const button of buttons) button.disabled = false;
    }
  }

  const dialogContext: ProfileDialogContext = {
    client,
    combination,
    mutate,
    notify,
    setError,
  };

  function handleEdit(existing: ProfileRevision): void {
    openEditDialog(dialogContext, existing);
  }

  createButton.addEventListener("click", () => {
    openCreateDialog(dialogContext);
  });

  const listDeps: ProfileListDeps = {
    combination,
    notify,
    openEditDialog: handleEdit,
    mutate,
    client,
  };

  loader.subscribe((state) => {
    if (state.kind === "ready") renderList(listHost, state.value.items, listDeps);
    else if (state.kind === "error") setError(state.error.message);
  });

  const root = el("section", { className: "panel lnt-cat-profiles" }, [
    el("div", { className: "panel-hd" }, [el("h2", { className: "panel-title", text: "Профили" })]),
    el("div", { className: "panel-bd" }, [createButton, listHost, errorNote]),
  ]);

  return {
    root,
    reload: async () => {
      await loader.load("profiles");
      notify();
    },
  };
}
