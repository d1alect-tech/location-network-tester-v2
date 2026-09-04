/** Менеджер профилей V6: панель .panel, виды — disclosure .disc-toggle/
 * .disc-body, предпросмотр — .frame, кнопки .btn/.btn-quiet, ошибка —
 * .banner.banner-inline. CRUD локаций, оборудования, фронтенда, трансформатора
 * и условий измерения + выбор комбинации для предпросмотра снимка захвата.
 * Мутации идут через api-клиент (nonce), состояния pending/success/failure
 * блокируют кнопки; ошибки — русские тексты, не console.
 * T11: поля форм — в profileFormView, диалоги — в profileDialogs; здесь
 * каркас, состояние комбинации и список. */

import type { LntApiClient } from "../../api/client";
import { normalizeThrown } from "../../api/errors";
import type { ProfileRevision } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { createResourceLoader } from "../../state/resource";
import type { ProfileDialogContext } from "./profileDialogs";
import { openCreateDialog, openEditDialog } from "./profileDialogs";
import { KINDS } from "./profileFormView";
import { PROFILE_KIND_LABELS } from "./profileForms";
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

  function renderList(items: ProfileRevision[]): void {
    while (listHost.firstChild) listHost.removeChild(listHost.firstChild);
    for (const kind of KINDS) {
      const groupItems = items.filter((item) => item.kind === kind);
      const bodyId = `cat-profile-${kind}`;
      const toggle = el("button", {
        className: "disc-toggle",
        text: PROFILE_KIND_LABELS[kind],
        attrs: { type: "button", "aria-expanded": "true", "aria-controls": bodyId },
      });
      const body = el("div", { className: "disc-body", attrs: { id: bodyId } });
      toggle.addEventListener("click", () => {
        const open = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", String(!open));
        body.hidden = open;
      });
      if (groupItems.length === 0) {
        body.append(el("p", { className: "t-compact", text: "Профилей этого вида нет." }));
      }
      for (const item of groupItems) {
        body.append(renderProfileRow(item));
      }
      listHost.append(toggle, body);
    }
  }

  function renderProfileRow(item: ProfileRevision): HTMLElement {
    const row = el("div", { className: "cat-profile-row" });
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = `combo-${item.kind}`;
    radio.value = item.profile_id;
    radio.id = `profile-radio-${item.profile_id}`;
    radio.checked = combination[item.kind]?.profile_id === item.profile_id;
    radio.addEventListener("change", () => {
      combination[item.kind] = item;
      notify();
    });
    const label = el("label", {
      className: "cat-profile-name",
      text: item.profile_id,
    });
    label.htmlFor = radio.id;
    const editButton = el("button", {
      className: "btn-quiet",
      text: "Изменить",
      attrs: { type: "button" },
    });
    editButton.addEventListener("click", () => handleEdit(item));
    const deleteButton = el("button", {
      className: "btn-quiet",
      text: "Удалить",
      attrs: { type: "button" },
    });
    deleteButton.addEventListener("click", () => {
      void mutate(() => client.profilesApi.remove(item.profile_id), row).then(() => {
        if (combination[item.kind]?.profile_id === item.profile_id) {
          delete combination[item.kind];
          notify();
        }
      });
    });
    row.append(radio, label, editButton, deleteButton);
    return row;
  }

  loader.subscribe((state) => {
    if (state.kind === "ready") renderList(state.value.items);
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
