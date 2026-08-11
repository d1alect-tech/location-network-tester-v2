import assert from "node:assert/strict";
import { test } from "node:test";

function makeOption() {
  const option = { value: "", textContent: "" };
  Object.defineProperty(option, "innerHTML", {
    set() {
      throw new Error("innerHTML запрещён");
    },
  });
  return option;
}

globalThis.document = {
  createElement: () => makeOption(),
};

const { fillBaselineSelect, syncCaptureBaselineState } = await import(
  "../../src/lnt/ui/static/app-dom.js"
);

function makeSelect(initialValue = "") {
  const select = {
    value: initialValue,
    disabled: false,
    options: [],
    replaceChildren(...items) {
      select.options = items;
      select.value = items[0]?.value ?? "";
    },
  };
  return select;
}

function makeCaptureForm({ checked, withSelect = true }) {
  const checkbox = { checked };
  const select = makeSelect();
  return {
    select,
    form: {
      elements: {
        namedItem(name) {
          if (name === "self_noise") return checkbox;
          if (name === "baseline_session" && withSelect) return select;
          return null;
        },
      },
    },
  };
}

const CATALOG = [
  {
    name: "meas-1",
    status: "valid",
    analyzed: true,
    summary: { session_id: "meas-1", session_type: "measurement" },
  },
  {
    name: "noise-a",
    status: "valid",
    analyzed: false,
    summary: { session_id: "noise-a", session_type: "self_noise" },
  },
  {
    name: "broken-noise",
    status: "invalid",
    analyzed: false,
    summary: { session_id: "broken-noise", session_type: "self_noise" },
  },
];

test("fillBaselineSelect lists only valid self_noise sessions", () => {
  const select = makeSelect();

  fillBaselineSelect(select, CATALOG);

  assert.deepEqual(select.options.map((option) => option.value), ["", "noise-a"]);
  assert.equal(select.options[0].textContent, "Без базовой сессии");
});

test("fillBaselineSelect preserves current selection when still present", () => {
  const select = makeSelect("noise-a");

  fillBaselineSelect(select, CATALOG);

  assert.equal(select.value, "noise-a");
});

test("fillBaselineSelect resets selection when baseline disappears", () => {
  const select = makeSelect("gone");

  fillBaselineSelect(select, CATALOG);

  assert.equal(select.value, "");
});

test("syncCaptureBaselineState disables and clears when self_noise checked", () => {
  const { form, select } = makeCaptureForm({ checked: true });
  select.value = "noise-a";

  syncCaptureBaselineState(form);

  assert.equal(select.disabled, true);
  assert.equal(select.value, "");
});

test("syncCaptureBaselineState re-enables when unchecked", () => {
  const { form, select } = makeCaptureForm({ checked: false });
  select.disabled = true;
  select.value = "noise-a";

  syncCaptureBaselineState(form);

  assert.equal(select.disabled, false);
  assert.equal(select.value, "noise-a");
});

test("syncCaptureBaselineState is null-safe without the select", () => {
  const { form } = makeCaptureForm({ checked: true, withSelect: false });

  assert.doesNotThrow(() => syncCaptureBaselineState(form));
});

test("fillBaselineSelect: без кандидатов — поясняющий плейсхолдер", () => {
  const select = makeSelect();

  fillBaselineSelect(select, [CATALOG[0], CATALOG[2]]);

  assert.equal(select.options.length, 1);
  assert.match(select.options[0].textContent, /Нет самошумных сессий/);
});
