import { beforeEach, describe, expect, it } from "vitest";
import { createMutation } from "../../state/resource";
import { createField, setFormPending } from "./forms";

describe("createField", () => {
  beforeEach(() => {
    document.body.textContent = "";
  });

  function makeField(): ReturnType<typeof createField> {
    const control = document.createElement("input");
    control.type = "text";
    return createField({ label: "Метка сессии", control });
  }

  it("associates label with control via for/id", () => {
    const field = makeField();
    const control = field.root.querySelector("input") as HTMLInputElement;
    expect(control.id).toBe(field.controlId);
    expect(field.root.querySelector(`label[for="${field.controlId}"]`)?.textContent).toContain(
      "Метка сессии",
    );
  });

  it("setError wires aria-describedby and role=alert with Russian text", () => {
    const field = makeField();
    field.setError("Значение не может быть пустым");
    const alert = field.root.querySelector('[role="alert"]');
    expect(alert?.textContent).toBe("Значение не может быть пустым");
    const control = field.root.querySelector("input") as HTMLInputElement;
    expect(control.getAttribute("aria-describedby")).toBe(alert?.id);
    expect(control.getAttribute("aria-invalid")).toBe("true");

    field.setError(null);
    expect(field.root.querySelector('[role="alert"]')).toBeNull();
    expect(control.getAttribute("aria-invalid")).toBe("false");
  });
});

describe("setFormPending", () => {
  beforeEach(() => {
    document.body.textContent = "";
  });

  it("disables submit controls and sets aria-busy while mutation is pending", async () => {
    let release!: (v: string) => void;
    const gate = new Promise<string>((res) => {
      release = res;
    });
    const mutation = createMutation<string, string>(() => gate);
    const form = document.createElement("form");
    const submit = document.createElement("button");
    submit.textContent = "Сохранить";
    form.append(submit);

    const run = mutation.run("x").catch(() => undefined);
    setFormPending(form, mutation);
    expect(submit.disabled).toBe(true);
    expect(form.getAttribute("aria-busy")).toBe("true");

    release("ok");
    await run;
    // Re-evaluating after completion re-enables controls.
    setFormPending(form, mutation);
    expect(submit.disabled).toBe(false);
    expect(form.getAttribute("aria-busy")).toBe("false");
  });
});
