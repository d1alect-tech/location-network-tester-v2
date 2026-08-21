/** Менеджер профилей: CRUD локаций, оборудования, фронтенда, трансформатора
 * и условий измерения + выбор комбинации для предпросмотра снимка захвата.
 * Мутации идут через api-клиент (nonce), состояния pending/success/failure
 * блокируют кнопки; ошибки — русские тексты, не console. */

import type { LntApiClient } from "../../api/client";
import { normalizeThrown } from "../../api/errors";
import type { ProfileData, ProfileKind, ProfileRevision } from "../../api/types";
import { openDialog } from "../../components/primitives/dialog";
import { el } from "../../components/primitives/dom";
import { createField } from "../../components/primitives/forms";
import { createResourceLoader } from "../../state/resource";
import { PROFILE_KIND_LABELS, collectProfileData } from "./profileForms";
import type { ProfileCombination } from "./profilePreview";

const KINDS: ProfileKind[] = ["location", "equipment", "front_end", "transformer", "conditions"];

export interface ProfileManagerOptions {
  client: LntApiClient;
  onCombinationChange: (combination: ProfileCombination) => void;
}

export interface ProfileManagerHandle {
  root: HTMLElement;
  reload(): Promise<void>;
}

function input(name: string, label: string, value = ""): HTMLElement {
  const control = document.createElement("input");
  control.type = "text";
  control.name = name;
  control.className = "lnt-input";
  if (value !== "") control.value = value;
  return createField({ label, control }).root;
}

function quantityInputs(prefix: string, label: string): HTMLElement {
  const wrap = el("div", { className: "lnt-cat-quantity" });
  wrap.append(
    input(`${prefix}_value`, `${label} — значение`),
    input(`${prefix}_unit`, `${label} — единица`),
  );
  return wrap;
}

/** Динамические поля формы под вид профиля (контракт data каждого вида). */
function formFieldsFor(kind: ProfileKind): HTMLElement[] {
  switch (kind) {
    case "location":
      return [
        input("alias", "Псевдоним локации"),
        input("outlet", "Розетка"),
        input("circuit", "Автомат/цепь"),
      ];
    case "equipment":
      return [input("alias", "Псевдоним оборудования"), input("model", "Модель")];
    case "front_end":
      return [
        quantityInputs("resistance", "Сопротивление"),
        quantityInputs("c1", "C1"),
        quantityInputs("c2", "C2"),
      ];
    case "transformer":
      return [
        quantityInputs("primary", "Первичная обмотка"),
        quantityInputs("secondary", "Вторичная обмотка"),
      ];
    case "conditions": {
      const select = document.createElement("select");
      select.name = "damper_state";
      select.className = "lnt-select";
      for (const [value, labelText] of [
        ["unknown", "Неизвестно"],
        ["on", "Включён"],
        ["off", "Выключен"],
      ] as const) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = labelText;
        select.append(option);
      }
      const damper = createField({ label: "Демпфер", control: select }).root;
      const loads = input("nearby_load_states", "Нагрузки рядом (через запятую)");
      return [damper, loads];
    }
  }
}

export function createProfileManager(options: ProfileManagerOptions): ProfileManagerHandle {
  const { client, onCombinationChange } = options;
  const combination: ProfileCombination = {};
  const loader = createResourceLoader<{ items: ProfileRevision[] }>(() => client.profiles());

  const listHost = el("div", { className: "lnt-cat-profile-list" });
  const errorNote = el("p", { className: "lnt-error-text", attrs: { role: "alert" } });
  const createButton = el("button", {
    className: "lnt-btn lnt-btn-primary",
    text: "Создать профиль",
    attrs: { type: "button" },
  });

  function notify(): void {
    onCombinationChange({ ...combination });
  }

  async function mutate(action: () => Promise<unknown>, busyHost: HTMLElement): Promise<void> {
    errorNote.textContent = "";
    const buttons = busyHost.querySelectorAll<HTMLButtonElement>("button");
    for (const button of buttons) button.disabled = true;
    try {
      await client.ensureReady();
      await action();
      await loader.load("profiles");
      notify();
    } catch (error) {
      const apiError = normalizeThrown(error);
      errorNote.textContent = apiError.message;
    } finally {
      for (const button of buttons) button.disabled = false;
    }
  }

  function openEditDialog(existing: ProfileRevision): void {
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
                  () =>
                    client.profilesApi.update(existing.profile_id, { kind: existing.kind, data }),
                  dialog.root,
                );
                close();
              } catch (validationError) {
                errorNote.textContent =
                  validationError instanceof Error ? validationError.message : "";
              }
            })();
          },
        },
      ],
    });
  }

  function fillExisting(host: HTMLElement, data: ProfileData): void {
    const flat: Record<string, string> = {};
    for (const [key, value] of Object.entries(data)) {
      if (typeof value === "string") flat[key] = value;
      else if (value && typeof value === "object" && "value" in value && "unit" in value) {
        flat[`${key}_value`] = String(value.value);
        flat[`${key}_unit`] = String(value.unit);
      }
    }
    for (const [name, value] of Object.entries(flat)) {
      const node = host.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`);
      if (node) node.value = value;
    }
    if ("nearby_load_states" in data && Array.isArray(data.nearby_load_states)) {
      const node = host.querySelector<HTMLInputElement>('[name="nearby_load_states"]');
      if (node) node.value = data.nearby_load_states.join(", ");
    }
  }

  createButton.addEventListener("click", () => {
    openCreateDialog();
  });

  function openCreateDialog(): void {
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
                await mutate(
                  () => client.profilesApi.create(profileId, { kind, data }),
                  dialog.root,
                );
                combination[kind] = undefined;
                close();
              } catch (validationError) {
                errorNote.textContent =
                  validationError instanceof Error ? validationError.message : "";
              }
            })();
          },
        },
      ],
    });
  }

  function renderList(items: ProfileRevision[]): void {
    while (listHost.firstChild) listHost.removeChild(listHost.firstChild);
    for (const kind of KINDS) {
      const groupItems = items.filter((item) => item.kind === kind);
      const group = el("fieldset", { className: "lnt-cat-profile-group" });
      group.append(el("legend", { text: PROFILE_KIND_LABELS[kind] }));
      if (groupItems.length === 0) {
        group.append(el("p", { className: "lnt-table-note", text: "Профилей этого вида нет." }));
      }
      for (const item of groupItems) {
        group.append(renderProfileRow(item));
      }
      listHost.append(group);
    }
  }

  function renderProfileRow(item: ProfileRevision): HTMLElement {
    const row = el("div", { className: "lnt-cat-profile-row" });
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
      className: "lnt-mono lnt-cat-profile-name",
      text: item.profile_id,
    });
    label.htmlFor = radio.id;
    const editButton = el("button", {
      className: "lnt-btn",
      text: "Изменить",
      attrs: { type: "button" },
    });
    editButton.addEventListener("click", () => openEditDialog(item));
    const deleteButton = el("button", {
      className: "lnt-btn",
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
    else if (state.kind === "error") errorNote.textContent = state.error.message;
  });

  const root = el("section", { className: "lnt-cat-profiles" }, [
    el("h3", { className: "lnt-cat-inspector-title", text: "Профили" }),
    createButton,
    listHost,
    errorNote,
  ]);

  return {
    root,
    reload: async () => {
      await loader.load("profiles");
      notify();
    },
  };
}
