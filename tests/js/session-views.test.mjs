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

function collect(node, matches, found = []) {
  if (node && typeof node === "object") {
    if (matches(node)) found.push(node);
    for (const child of node.children ?? []) collect(child, matches, found);
  }
  return found;
}

function makeSession(name, sessionType) {
  return {
    name,
    status: "valid",
    error: null,
    analyzed: true,
    summary: {
      session_id: name,
      created_utc: "2026-08-05T10:00:00Z",
      source: "device",
      session_type: sessionType,
      profile: null,
      label: null,
    },
  };
}

test("renderSessions adds a Самошум badge only for self_noise sessions", () => {
  const listEl = makeNode("div");

  renderSessions(listEl, [makeSession("noise-a", "self_noise"), makeSession("meas-1", "measurement")]);

  const rows = collect(listEl, (node) => String(node.className).includes("session-row"));
  assert.equal(rows.length, 2);
  const badgesInNoise = collect(rows[0], (node) => node.className === "badge badge-selfnoise");
  const badgesInMeasurement = collect(rows[1], (node) => node.className === "badge badge-selfnoise");
  assert.equal(badgesInNoise.length, 1);
  assert.equal(badgesInNoise[0].textContent, "Самошум");
  assert.equal(badgesInMeasurement.length, 0);
});

function makeDetail(waveformAvailable) {
  return {
    name: "meas-1",
    manifest: { session_id: "meas-1", source: "device" },
    analysis: null,
    spectrum_available: false,
    waveform_available: waveformAvailable,
  };
}

test("renderSessionDetail exposes CH2 button when waveform available", () => {
  const el = makeNode("section");

  renderSessionDetail(el, makeDetail(true));

  const ch2 = collect(el, (node) => node.id === "waveform-ch2-btn");
  assert.equal(ch2.length, 1);
  assert.equal(ch2[0].type, "button");
  assert.equal(ch2[0].textContent, "Осциллограмма CH2");
});

test("renderSessionDetail hides both waveform buttons when unavailable", () => {
  const el = makeNode("section");

  renderSessionDetail(el, makeDetail(false));

  assert.equal(collect(el, (node) => node.id === "waveform-load-btn").length, 0);
  assert.equal(collect(el, (node) => node.id === "waveform-ch2-btn").length, 0);
});

test("renderSessionDetail labels the CH1 waveform button explicitly", () => {
  const el = makeNode("section");

  renderSessionDetail(el, makeDetail(true));

  const ch1 = collect(el, (node) => node.id === "waveform-load-btn");
  assert.equal(ch1.length, 1);
  assert.equal(ch1[0].textContent, "Осциллограмма CH1");
});
