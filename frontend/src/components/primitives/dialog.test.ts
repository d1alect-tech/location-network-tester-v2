import { beforeEach, describe, expect, it } from "vitest";
import { type DialogAction, openDialog } from "./dialog";

function button(label: string): HTMLButtonElement {
  const b = document.createElement("button");
  b.textContent = label;
  document.body.append(b);
  return b;
}

describe("openDialog", () => {
  beforeEach(() => {
    document.body.textContent = "";
  });

  it("renders role=dialog with aria-modal and Russian title", () => {
    const invoker = button("Открыть");
    invoker.focus();
    const handle = openDialog({ title: "Подтверждение", content: document.createElement("p") });
    const dialog = handle.root.querySelector<HTMLElement>('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(dialog?.getAttribute("aria-modal")).toBe("true");
    const labelledby = dialog?.getAttribute("aria-labelledby");
    expect(labelledby).toBeTruthy();
    expect(handle.root.querySelector(`#${labelledby}`)?.textContent).toBe("Подтверждение");
  });

  it("provides a default Закрыть action that closes", () => {
    openDialog({ title: "Т", content: document.createElement("p") });
    const close = [...document.querySelectorAll("button")].find((b) => b.textContent === "Закрыть");
    expect(close).toBeDefined();
    close?.click();
    expect(document.querySelector(".lnt-dialog-overlay")).toBeNull();
  });

  it("Esc closes the dialog", () => {
    openDialog({ title: "Т", content: document.createElement("p") });
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(document.querySelector(".lnt-dialog-overlay")).toBeNull();
  });

  it("restores focus to the invoker on close", () => {
    const invoker = button("Открыть");
    invoker.focus();
    const handle = openDialog({ title: "Т", content: document.createElement("p") });
    handle.close();
    expect(document.activeElement).toBe(invoker);
  });

  it("traps Tab focus inside the dialog", () => {
    openDialog({
      title: "Т",
      content: document.createElement("p"),
      actions: [{ label: "Ок", onClick: () => undefined }],
    });
    const buttons = [...handle_all_buttons()];
    expect(buttons.length).toBeGreaterThanOrEqual(2);
    buttons[buttons.length - 1]?.focus();
    document.activeElement?.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Tab", bubbles: true }),
    );
    const focusedIndex = buttons.indexOf(document.activeElement as HTMLButtonElement);
    expect(focusedIndex).toBe(0);
  });

  it("action callbacks receive close and custom actions render in Russian", () => {
    let closedByAction = false;
    const actions: DialogAction[] = [
      {
        label: "Удалить",
        kind: "primary",
        onClick: (close) => {
          closedByAction = true;
          close();
        },
      },
      { label: "Отмена", onClick: () => undefined },
    ];
    openDialog({ title: "Удаление", content: document.createElement("p"), actions });
    const del = [...document.querySelectorAll("button")].find((b) => b.textContent === "Удалить");
    del?.click();
    expect(closedByAction).toBe(true);
    expect(document.querySelector(".lnt-dialog-overlay")).toBeNull();
  });
});

function handle_all_buttons(): HTMLButtonElement[] {
  return [...document.querySelectorAll<HTMLElement>(".lnt-dialog button")].filter(
    (b): b is HTMLButtonElement => b instanceof HTMLButtonElement,
  );
}
