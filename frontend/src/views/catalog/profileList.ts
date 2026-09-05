/** Список профилей (C2-лист, выделен из profileManager): группировка revision
 * по видам и строки с выбором комбинации, правкой и удалением.
 * Мутация и диалог правки приходят колбэками менеджера.
 * V6-разметка зафиксированной волны сохранена: disclosure .disc-toggle/
 * .disc-body, строки .cat-profile-row, кнопки .btn-quiet. */

import type { LntApiClient } from "../../api/client";
import type { ProfileKind, ProfileRevision } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { PROFILE_KIND_LABELS } from "./profileForms";
import type { ProfileCombination } from "./profilePreview";

export const KINDS: ProfileKind[] = [
  "location",
  "equipment",
  "front_end",
  "transformer",
  "conditions",
];

export interface ProfileListDeps {
  combination: ProfileCombination;
  notify(): void;
  openEditDialog(item: ProfileRevision): void;
  mutate(action: () => Promise<unknown>, busyHost: HTMLElement): Promise<void>;
  client: LntApiClient;
}

function kindDisclosure(kind: ProfileKind): { toggle: HTMLElement; body: HTMLElement } {
  const bodyId = `cat-profile-${kind}`;
  const toggle = el("button", {
    className: "disc-toggle",
    text: PROFILE_KIND_LABELS[kind],
    attrs: { type: "button", "aria-expanded": "true", "aria-controls": bodyId },
  });
  const body = el("div", {
    className: "disc-body lnt-cat-profile-group",
    attrs: { id: bodyId },
  });
  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!open));
    body.hidden = open;
  });
  return { toggle, body };
}

export function renderList(
  host: HTMLElement,
  items: ProfileRevision[],
  deps: ProfileListDeps,
): void {
  while (host.firstChild) host.removeChild(host.firstChild);
  for (const kind of KINDS) {
    const groupItems = items.filter((item) => item.kind === kind);
    const { toggle, body } = kindDisclosure(kind);
    if (groupItems.length === 0) {
      body.append(el("p", { className: "t-compact", text: "Профилей этого вида нет." }));
    }
    for (const item of groupItems) {
      body.append(renderProfileRow(item, deps));
    }
    host.append(toggle, body);
  }
}

function comboRadio(item: ProfileRevision, deps: ProfileListDeps): HTMLInputElement {
  const radio = document.createElement("input");
  radio.type = "radio";
  radio.name = `combo-${item.kind}`;
  radio.value = item.profile_id;
  radio.id = `profile-radio-${item.profile_id}`;
  radio.checked = deps.combination[item.kind]?.profile_id === item.profile_id;
  radio.addEventListener("change", () => {
    deps.combination[item.kind] = item;
    deps.notify();
  });
  return radio;
}

export function renderProfileRow(item: ProfileRevision, deps: ProfileListDeps): HTMLElement {
  const row = el("div", { className: "cat-profile-row" });
  const radio = comboRadio(item, deps);
  const label = el("label", { className: "cat-profile-name", text: item.profile_id });
  label.htmlFor = radio.id;
  const editButton = el("button", {
    className: "btn-quiet",
    text: "Изменить",
    attrs: { type: "button" },
  });
  editButton.addEventListener("click", () => deps.openEditDialog(item));
  const deleteButton = el("button", {
    className: "btn-quiet",
    text: "Удалить",
    attrs: { type: "button" },
  });
  deleteButton.addEventListener("click", () => {
    void deps
      .mutate(() => deps.client.profilesApi.remove(item.profile_id), row)
      .then(() => {
        if (deps.combination[item.kind]?.profile_id === item.profile_id) {
          delete deps.combination[item.kind];
          deps.notify();
        }
      });
  });
  row.append(radio, label, editButton, deleteButton);
  return row;
}
