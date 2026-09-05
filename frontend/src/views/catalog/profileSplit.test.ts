/** C2-разбиение profileManager: поля формы и список живут в отдельных
 * листьях, менеджер держит только createProfileManager + mutate/notify/loader. */

import { describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import type { ProfileRevision } from "../../api/types";
import { fillExisting, formFieldsFor } from "./profileFormFields";
import { KINDS, renderList, renderProfileRow } from "./profileList";
import type { ProfileCombination } from "./profilePreview";

function revision(
  profile_id: string,
  kind: ProfileRevision["kind"],
  data: ProfileRevision["data"],
): ProfileRevision {
  return { profile_id, kind, revision: 1, captured_at: "2026-08-01T00:00:00Z", data };
}

describe("profileFormFields", () => {
  it("строит поля локации с именами контракта data", () => {
    const fields = formFieldsFor("location");
    const names = fields.flatMap((field) =>
      [...field.querySelectorAll("[name]")].map(
        (node) => (node as HTMLInputElement | HTMLSelectElement).name,
      ),
    );
    expect(names).toEqual(["alias", "outlet", "circuit"]);
  });

  it("строит условия с селектом демпфера и полем нагрузок", () => {
    const fields = formFieldsFor("conditions");
    const names = fields.flatMap((field) =>
      [...field.querySelectorAll("[name]")].map(
        (node) => (node as HTMLInputElement | HTMLSelectElement).name,
      ),
    );
    expect(names).toEqual(["damper_state", "nearby_load_states"]);
  });

  it("fillExisting раскладывает строки, величины и список нагрузок", () => {
    const host = document.createElement("div");
    host.append(...formFieldsFor("front_end"));
    fillExisting(host, {
      resistance: { value: 10, unit: "кОм" },
      c1: { value: 1, unit: "нФ" },
      c2: { value: 2, unit: "нФ" },
    });
    const read = (name: string): string =>
      host.querySelector<HTMLInputElement>(`[name="${name}"]`)?.value ?? "";
    expect(read("resistance_value")).toBe("10");
    expect(read("resistance_unit")).toBe("кОм");

    const condHost = document.createElement("div");
    condHost.append(...formFieldsFor("conditions"));
    fillExisting(condHost, { damper_state: "on", nearby_load_states: ["a", "b"] });
    expect(condHost.querySelector<HTMLSelectElement>('[name="damper_state"]')?.value).toBe("on");
    expect(condHost.querySelector<HTMLInputElement>('[name="nearby_load_states"]')?.value).toBe(
      "a, b",
    );
  });
});

describe("profileList", () => {
  it("KINDS покрывает все пять видов профилей", () => {
    expect([...KINDS]).toEqual(["location", "equipment", "front_end", "transformer", "conditions"]);
  });

  it("renderList группирует по видам и отмечает пустые группы", () => {
    const host = document.createElement("div");
    const combination: ProfileCombination = {};
    const deps = {
      combination,
      notify: vi.fn(),
      openEditDialog: vi.fn(),
      mutate: vi.fn(async () => undefined),
      client: { profilesApi: { remove: vi.fn(async () => undefined) } } as unknown as LntApiClient,
    };
    renderList(
      host,
      [revision("loc-1", "location", { alias: "a", outlet: "b", circuit: "c" })],
      deps,
    );
    expect(host.querySelectorAll(".lnt-cat-profile-group").length).toBe(5);
    expect(host.textContent).toContain("loc-1");
    expect(host.textContent).toContain("Профилей этого вида нет.");
  });

  it("renderProfileRow выбирает комбинацию и уведомляет", () => {
    const combination: ProfileCombination = {};
    const notify = vi.fn();
    const item = revision("loc-1", "location", {
      alias: "a",
      outlet: "b",
      circuit: "c",
    });
    const deps = {
      combination,
      notify,
      openEditDialog: vi.fn(),
      mutate: vi.fn(async () => undefined),
      client: { profilesApi: { remove: vi.fn(async () => undefined) } } as unknown as LntApiClient,
    };
    const row = renderProfileRow(item, deps);
    const radio = row.querySelector<HTMLInputElement>('input[type="radio"]');
    expect(radio).not.toBeNull();
    if (radio) {
      radio.checked = true;
      radio.dispatchEvent(new Event("change", { bubbles: true }));
    }
    expect(combination.location?.profile_id).toBe("loc-1");
    expect(notify).toHaveBeenCalledTimes(1);
  });

  it("renderProfileRow открывает диалог правки и удаляет через mutate", async () => {
    const combination: ProfileCombination = {};
    const openEditDialog = vi.fn();
    const remove = vi.fn(async () => undefined);
    const mutate = vi.fn(async (action: () => Promise<unknown>) => {
      await action();
    });
    const item = revision("loc-1", "location", {
      alias: "a",
      outlet: "b",
      circuit: "c",
    });
    const deps = {
      combination,
      notify: vi.fn(),
      openEditDialog,
      mutate,
      client: { profilesApi: { remove } } as unknown as LntApiClient,
    };
    const row = renderProfileRow(item, deps);
    const buttons = [...row.querySelectorAll("button")];
    buttons.find((button) => button.textContent === "Изменить")?.click();
    expect(openEditDialog).toHaveBeenCalledWith(item);
    buttons.find((button) => button.textContent === "Удалить")?.click();
    await Promise.resolve();
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledWith("loc-1");
  });
});
