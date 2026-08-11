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
const { renderCompare } = await import("../../src/lnt/ui/static/status-views.js");

function collect(node, matches, found = []) {
  if (node && typeof node === "object") {
    if (matches(node)) found.push(node);
    for (const child of node.children ?? []) collect(child, matches, found);
  }
  return found;
}

function makeSummary(channels) {
  return {
    session_id: "sess",
    created_utc: "2026-08-05T10:00:00Z",
    source: "synthetic",
    session_type: "measurement",
    profile: "baseline",
    sample_rate_hz: 100000,
    duration_s: 2.4,
    sample_count: 240000,
    label: null,
    channels,
  };
}

function makeDetail({ ch2Available, needle }) {
  return {
    name: "sess-1",
    manifest: { session_id: "sess-1" },
    analysis: {
      needle,
      spectrum: { peaks: [] },
    },
    spectrum_available: true,
    waveform_available: true,
    ch2_available: ch2Available,
  };
}

const dualNeedle = {
  needle_mean_v: 0.5,
  needle_sigma_ratio: 0.1,
  async_sync_ratio: 0.2,
  lf_envelope_cv: 0.05,
  line_frequency_hz: 50.01,
  cycles_analyzed: 120,
  sync_source: "ch2",
};

const singleNeedle = {
  needle_mean_v: 0.5,
  needle_sigma_ratio: 0.1,
  async_sync_ratio: null,
  lf_envelope_cv: null,
  line_frequency_hz: null,
  cycles_analyzed: 120,
  sync_source: "nominal",
};

test("список сессий помечает однокональные бейджем «1 канал»", () => {
  const list = makeNode("div");
  const sessions = [
    { name: "dual", status: "valid", analyzed: true, summary: makeSummary("dual") },
    { name: "single", status: "valid", analyzed: true, summary: makeSummary("ch1_only") },
  ];
  renderSessions(list, sessions, {});
  const badges = collect(list, (node) => String(node.className).includes("badge-single-channel"));
  assert.equal(badges.length, 1);
  assert.equal(badges[0].textContent, "1 канал");
});

test("детали без ch2.npy не показывают кнопку осциллограммы CH2", () => {
  const el = makeNode("section");
  renderSessionDetail(el, makeDetail({ ch2Available: false, needle: singleNeedle }));
  const ch2Buttons = collect(el, (node) => node.id === "waveform-ch2-btn");
  assert.equal(ch2Buttons.length, 0);
  const ch1Buttons = collect(el, (node) => node.id === "waveform-load-btn");
  assert.equal(ch1Buttons.length, 1);
});

test("детали с ch2.npy показывают кнопку осциллограммы CH2", () => {
  const el = makeNode("section");
  renderSessionDetail(el, makeDetail({ ch2Available: true, needle: dualNeedle }));
  const ch2Buttons = collect(el, (node) => node.id === "waveform-ch2-btn");
  assert.equal(ch2Buttons.length, 1);
});

test("недоступные синхронные метрики отображаются как «н/д (1 канал)»", () => {
  const el = makeNode("section");
  renderSessionDetail(el, makeDetail({ ch2Available: false, needle: singleNeedle }));
  const cells = collect(el, (node) => node.textContent === "н/д (1 канал)");
  assert.ok(cells.length >= 2, `ожидались ячейки «н/д (1 канал)», найдено: ${cells.length}`);
});

test("сравнение с null-метрикой не выдаёт ложный процент от нуля", () => {
  const el = makeNode("section");
  renderCompare(el, {
    session_a_id: "a",
    session_b_id: "b",
    peak_deltas: [],
    metric_deltas: [
      { name: "async_sync_ratio", value_a: 0.468, value_b: null },
      { name: "needle_mean_v", value_a: 0.184, value_b: 0.203 },
    ],
  });
  const cells = collect(el, (node) => String(node.textContent).includes("-100.0%"));
  assert.equal(cells.length, 0, "null не должен трактоваться как 0 в процентах");
  const na = collect(el, (node) => String(node.textContent).includes("н/д"));
  assert.ok(na.length >= 1, "ожидался «н/д» для недоступной метрики");
  const percent = collect(el, (node) => String(node.textContent).includes("+10.3%"));
  assert.ok(percent.length >= 1, "процент для полной пары должен считаться");
});

test("строка «Синхронизация» отражает источник фазовой привязки", () => {
  const single = makeNode("section");
  renderSessionDetail(single, makeDetail({ ch2Available: false, needle: singleNeedle }));
  const nominal = collect(single, (node) => String(node.textContent).includes("номинал 20 мс"));
  assert.ok(nominal.length >= 1);

  const dual = makeNode("section");
  renderSessionDetail(dual, makeDetail({ ch2Available: true, needle: dualNeedle }));
  const ch2 = collect(dual, (node) => String(node.textContent).includes("CH2 (сеть 50 Гц)"));
  assert.ok(ch2.length >= 1);
});
