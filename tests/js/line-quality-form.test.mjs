import assert from "node:assert/strict";
import { test } from "node:test";

globalThis.document = {
  createElement: () => ({ value: "", textContent: "" }),
};

globalThis.FormData = class {
  constructor(form) {
    this.entriesList = form.entriesList;
  }

  entries() {
    return this.entriesList[Symbol.iterator]();
  }

  has(name) {
    return this.entriesList.some(([key]) => key === name);
  }
};

const { fillSessionSelect, requestFromForm } = await import("../../src/lnt/ui/static/app-dom.js");

test("requestFromForm: transformer форсирует channels=1 (disabled-селект выпадает из FormData)", () => {
  const form = {
    entriesList: [
      ["duration_s", "4"],
      ["input", "transformer"],
    ],
  };

  const request = requestFromForm(form, "capture");

  assert.equal(request.input, "transformer");
  assert.equal(request.channels, 1);
  assert.equal(request.self_noise, false);
});

test("requestFromForm: rc сохраняет channels из формы", () => {
  const form = {
    entriesList: [
      ["duration_s", "4"],
      ["input", "rc"],
      ["channels", "2"],
    ],
  };

  const request = requestFromForm(form, "capture");

  assert.equal(request.input, "rc");
  assert.equal(request.channels, 2);
});

test("requestFromForm: не-capture запрос не получает channels-принуждения", () => {
  const form = {
    entriesList: [["profile", "baseline"]],
  };

  const request = requestFromForm(form, "simulate");

  assert.equal("channels" in request, false);
  assert.equal("self_noise" in request, false);
});

test("fillSessionSelect: line_quality сессии исключены из A/B сравнения", () => {
  const select = {
    value: "",
    options: [],
    replaceChildren(...items) {
      select.options = items;
      select.value = items[0]?.value ?? "";
    },
  };
  const sessions = [
    {
      name: "meas-1",
      status: "valid",
      analyzed: true,
      summary: { session_type: "measurement" },
    },
    {
      name: "line-1",
      status: "valid",
      analyzed: true,
      summary: { session_type: "line_quality" },
    },
  ];

  fillSessionSelect(select, sessions, "Выберите сессию");

  assert.deepEqual(
    select.options.map((option) => option.value),
    ["", "meas-1"],
  );
});
