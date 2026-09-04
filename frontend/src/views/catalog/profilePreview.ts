/** Предпросмотр снимка профиля V6: контейнер .frame, типографика .t-*.
 * Показывает ТОЧНО те данные выбранных профилей (id, revision, время, поля),
 * которые сохранит захват при этой комбинации. Никаких вычислений «от себя» —
 * только контракт ProfileRevision. Сигнатура без изменений. */

import type { ProfileKind, ProfileRevision } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { PROFILE_KIND_LABELS } from "./profileForms";

export type ProfileCombination = Partial<Record<ProfileKind, ProfileRevision>>;

const KIND_ORDER: ProfileKind[] = [
  "location",
  "equipment",
  "front_end",
  "transformer",
  "conditions",
];

export function formatSnapshotLine(profile: ProfileRevision): string[] {
  return [
    `вид: ${PROFILE_KIND_LABELS[profile.kind]}`,
    `идентификатор профиля: ${profile.profile_id}`,
    `revision: ${String(profile.revision)}`,
    `зафиксировано: ${profile.captured_at}`,
  ];
}

export function createProfilePreview(): {
  root: HTMLElement;
  setCombination(combination: ProfileCombination): void;
} {
  const host = el("div", {});
  const root = el("section", { className: "frame" }, [
    el("h4", {
      className: "t-sub",
      text: "Снимок, который сохранит захват при текущей комбинации профилей",
    }),
    host,
  ]);

  function renderProfile(profile: ProfileRevision): HTMLElement {
    const box = el("div", {});
    const lines = formatSnapshotLine(profile);
    box.append(el("p", { className: "t-mono", text: `[${lines[0] ?? ""}]` }));
    for (const line of lines.slice(1)) {
      box.append(el("p", { className: "t-mono", text: line }));
    }
    // Данные профиля — дословно, как их хранит захват.
    const pre = el("pre", { className: "t-mono cat-preview-json" });
    pre.textContent = JSON.stringify(profile.data, null, 2);
    box.append(pre);
    return box;
  }

  return {
    root,
    setCombination: (combination) => {
      while (host.firstChild) host.removeChild(host.firstChild);
      const chosen = KIND_ORDER.map((kind) => combination[kind]).filter(
        (profile): profile is ProfileRevision => profile !== undefined,
      );
      if (chosen.length === 0) {
        host.append(
          el("p", {
            className: "t-compact",
            text: "Профили не выбраны — снимок будет пустым. Выберите по одному профилю каждого вида.",
          }),
        );
        return;
      }
      for (const profile of chosen) host.append(renderProfile(profile));
    },
  };
}
