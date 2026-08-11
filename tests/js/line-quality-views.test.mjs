import assert from "node:assert/strict";
import { test } from "node:test";

function makeNode(tagName) {
  const node = {
    tagName,
    className: "",
    textContent: "",
    hidden: false,
    id: "",
    type: "",
    title: "",
    href: "",
    scope: "",
    colSpan: 0,
    dataset: {},
    children: [],
    classes: new Set(),
    append(...items) {
      node.children.push(...items);
    },
    appendChild(item) {
      node.children.push(item);
      return item;
    },
    replaceChildren(...items) {
      node.children = [...items];
    },
    setAttribute() {},
    addEventListener() {},
    classList: {
      add(...names) {
        for (const name of names) node.classes.add(name);
      },
      remove(...names) {
        for (const name of names) node.classes.delete(name);
      },
      contains(name) {
        return node.classes.has(name);
      },
    },
  };
  Object.defineProperty(node, "innerHTML", {
    set() {
      throw new Error("innerHTML запрещён");
    },
  });
  return node;
}

globalThis.document = {
  createElement: (tagName) => makeNode(tagName),
  createTextNode: (text) => ({ textContent: String(text) }),
  createDocumentFragment: () => makeNode("#fragment"),
};

const { renderSessions, renderSessionDetail } = await import(
  "../../src/lnt/ui/static/session-views.js"
);
const { syncCaptureInputState } = await import("../../src/lnt/ui/static/app-dom.js");

function collect(node, matches, found = []) {
  if (node && typeof node === "object") {
    if (matches(node)) found.push(node);
    for (const child of node.children ?? []) collect(child, matches, found);
  }
  return found;
}

const LINE_QUALITY = {
  fundamental_hz: 49.98,
  fundamental_rms_v: 10.78,
  total_rms_v: 10.8,
  thd_ratio: 0.0603,
  crest_factor: 1.46,
  envelope_cv: 0.004,
  cycles_analyzed: 119,
  harmonics: [
    { order: 2, frequency_hz: 99.96, amplitude_v: 0.05, ratio: 0.0033 },
    { order: 3, frequency_hz: 149.9, amplitude_v: 0.85, ratio: 0.0559 },
    { order: 5, frequency_hz: 249.9, amplitude_v: 0.21, ratio: 0.0138 },
  ],
};

function makeLineDetail() {
  return {
    name: "line-1",
    manifest: { session_id: "line-1", session_type: "line_quality" },
    analysis: {
      needle: null,
      spectrum: null,
      line_quality: LINE_QUALITY,
    },
    spectrum_available: false,
    waveform_available: true,
    ch2_available: false,
  };
}

test("список сессий помечает line_quality бейджем «Сеть 50 Гц»", () => {
  const list = makeNode("div");
  const sessions = [
    {
      name: "line",
      status: "valid",
      analyzed: true,
      summary: { session_id: "line", session_type: "line_quality", channels: "ch1_only" },
    },
  ];
  renderSessions(list, sessions, {});
  const badges = collect(list, (node) => String(node.className).includes("badge-line-quality"));
  assert.equal(badges.length, 1);
  assert.equal(badges[0].textContent, "Сеть 50 Гц");
});

test("детали line_quality показывают THD и таблицу гармоник вместо иголок", () => {
  const el = makeNode("section");
  renderSessionDetail(el, makeLineDetail());

  const thd = collect(el, (node) => String(node.textContent).includes("THD"));
  assert.ok(thd.length >= 1, "ожидалась строка THD");

  const percent = collect(el, (node) => String(node.textContent).includes("6.03"));
  assert.ok(percent.length >= 1, "THD должен отображаться в процентах (6.03)");

  const h3 = collect(el, (node) => String(node.textContent) === "H3");
  assert.equal(h3.length, 1, "ожидалась строка гармоники H3");

  const needles = collect(el, (node) => String(node.textContent).includes("μ_pk"));
  assert.equal(needles.length, 0, "иголочные метрики не должны отображаться");

  const frequency = collect(el, (node) => String(node.textContent).includes("49.98"));
  assert.ok(frequency.length >= 1, "ожидалась частота сети");
});

test("детали line_quality не строят панель спектра иголок", () => {
  const el = makeNode("section");
  renderSessionDetail(el, makeLineDetail());
  const shells = collect(el, (node) => String(node.className).includes("plot-spectrum"));
  assert.equal(shells.length, 0);
});

function makeCaptureForm(initial = {}) {
  const inputSelect = { value: initial.input ?? "rc", disabled: false };
  const channelsSelect = { value: initial.channels ?? "2", disabled: false };
  const selfNoise = { checked: initial.selfNoise ?? false, disabled: false };
  const baseline = { value: initial.baseline ?? "", disabled: false };
  const form = {
    elements: {
      namedItem(name) {
        if (name === "input") return inputSelect;
        if (name === "channels") return channelsSelect;
        if (name === "self_noise") return selfNoise;
        if (name === "baseline_session") return baseline;
        return null;
      },
    },
  };
  return { form, inputSelect, channelsSelect, selfNoise, baseline };
}

test("syncCaptureInputState: трансформатор — 1 канал, самошум и базовая недоступны", () => {
  const { form, channelsSelect, selfNoise, baseline } = makeCaptureForm({
    input: "transformer",
    channels: "2",
    selfNoise: true,
    baseline: "noise-a",
  });

  syncCaptureInputState(form);

  assert.equal(channelsSelect.value, "1");
  assert.equal(channelsSelect.disabled, true);
  assert.equal(selfNoise.checked, false);
  assert.equal(selfNoise.disabled, true);
  assert.equal(baseline.disabled, true);
  assert.equal(baseline.value, "");
});

test("syncCaptureInputState: возврат к RC снимает блокировки", () => {
  const { form, channelsSelect, selfNoise, baseline } = makeCaptureForm({ input: "transformer" });
  syncCaptureInputState(form);

  form.elements.namedItem("input").value = "rc";
  syncCaptureInputState(form);

  assert.equal(channelsSelect.disabled, false);
  assert.equal(selfNoise.disabled, false);
  assert.equal(baseline.disabled, false);
});

test("syncCaptureInputState null-безопасен без селекта входа", () => {
  const form = { elements: { namedItem: () => null } };
  assert.doesNotThrow(() => syncCaptureInputState(form));
});
