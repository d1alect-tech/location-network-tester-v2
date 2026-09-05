/** Диалоги создания/правки профилей (T11: выделено из profileManager).
 * Состояние (combination) и инфраструктура (mutate/notify/setError) приходят
 * контекстом из createProfileManager; здесь только построение форм и вызовы
 * profilesApi. Без смены поведения, текстов и разметки. */

import type { LntApiClient } from "../../api/client";
import type { ProfileKind, ProfileRevision } from "../../api/types";
import { openDialog } from "../../components/primitives/dialog";
import { el } from "../../components/primitives/dom";
import { createField } from "../../components/primitives/forms";
import { fillExisting, formFieldsFor } from "./profileFormFields";
import { PROFILE_KIND_LABELS, collectProfileData } from "./profileForms";
import { KINDS } from "./profileList";
import type { ProfileCombination } from "./profilePreview";

export interface ProfileDialogContext {
  client: LntApiClient;
  combination: ProfileCombination;
  mutate(action: () => Promise<unknown>, busyHost: HTMLElement): Promise<void>;
  notify(): void;
  setError(message: string): void;
}

export function openCreateDialog(ctx: ProfileDialogContext): void {
  const { client, combination, mutate, setError } = ctx;
  const idInput = document.createElement("input");
  idInput.type = "text";
  idInput.className = "lnt-input";
  const kindSelect = document.createElement("select");
  kindSelect.name = "__kind";
  kindSelect.className = "lnt-select";
  for (const kind of KINDS) {
    const option = document.createElement("option");
    option.value = kind;
    option.textContent = PROFILE_KIND_LABELS[kind];
    kindSelect.append(option);
  }
  const fieldsHost = el("div", {});
  fieldsHost.append(...formFieldsFor(kindSelect.value as ProfileKind));
  kindSelect.addEventListener("change", () => {
    while (fieldsHost.firstChild) fieldsHost.removeChild(fieldsHost.firstChild);
    fieldsHost.append(...formFieldsFor(kindSelect.value as ProfileKind));
  });

  const form = document.createElement("form");
  form.append(
    createField({ label: "Идентификатор профиля", control: idInput }).root,
    createField({ label: "Вид профиля", control: kindSelect }).root,
    fieldsHost,
  );
  form.addEventListener("submit", (event) => event.preventDefault());

  const dialog = openDialog({
    title: "Новый профиль",
    content: form,
    actions: [
      {
        label: "Создать",
        kind: "primary",
        onClick: (close) => {
          void (async () => {
            const profileId = idInput.value.trim();
            if (profileId === "") {
              idInput.setAttribute("aria-invalid", "true");
              return;
            }
            try {
              const kind = kindSelect.value as ProfileKind;
              const { data } = collectProfileData(kind, form);
              await mutate(() => client.profilesApi.create(profileId, { kind, data }), dialog.root);
              combination[kind] = undefined;
              close();
            } catch (validationError) {
              setError(validationError instanceof Error ? validationError.message : "");
            }
          })();
        },
      },
    ],
  });
}

export function openEditDialog(ctx: ProfileDialogContext, existing: ProfileRevision): void {
  const { client, mutate, setError } = ctx;
  const kindSelect = document.createElement("select");
  kindSelect.name = "__kind";
  kindSelect.className = "lnt-select";
  kindSelect.disabled = true;
  const option = document.createElement("option");
  option.value = existing.kind;
  option.textContent = PROFILE_KIND_LABELS[existing.kind];
  kindSelect.append(option);
  kindSelect.value = existing.kind;

  const fieldsHost = el("div", {});
  fieldsHost.append(...formFieldsFor(existing.kind));
  fillExisting(fieldsHost, existing.data);

  const form = document.createElement("form");
  form.append(createField({ label: "Вид профиля", control: kindSelect }).root, fieldsHost);
  form.addEventListener("submit", (event) => event.preventDefault());

  const dialog = openDialog({
    title: `Новая revision: ${existing.profile_id}`,
    content: form,
    actions: [
      {
        label: "Сохранить revision",
        kind: "primary",
        onClick: (close) => {
          void (async () => {
            try {
              const { data } = collectProfileData(existing.kind, form);
              await mutate(
                () => client.profilesApi.update(existing.profile_id, { kind: existing.kind, data }),
                dialog.root,
              );
              close();
            } catch (validationError) {
              setError(validationError instanceof Error ? validationError.message : "");
            }
          })();
        },
      },
    ],
  });
}
