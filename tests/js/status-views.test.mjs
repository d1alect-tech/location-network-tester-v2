import assert from "node:assert/strict";
import { test } from "node:test";

function makeNode(tagName) {
  const node = {
    tagName,
    className: "",
    textContent: "",
    hidden: false,
    id: "",
    dataset: {},
    children: [],
    classes: new Set(),
    append(...items) {
      node.children.push(...items);
    },
    replaceChildren(...items) {
      node.children = [...items];
    },
    setAttribute() {},
    closest() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    querySelector() {
      return null;
    },
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

const { renderError, renderJobProgress } = await import(
  "../../src/lnt/ui/static/status-views.js"
);

function snapshotWith(status, stage = "capturing") {
  return {
    schema_version: 1,
    version: 2,
    job_id: "a".repeat(32),
    kind: "capture",
    status,
    stage,
    series_index: 1,
    series_total: 2,
    written_sessions: [],
    result: null,
    error_code: null,
    error_message: null,
  };
}

function makeJobElements() {
  const section = makeNode("section");
  const progress = makeNode("progress");
  progress.closest = (selector) => (selector === "section" ? section : null);
  return {
    section,
    els: {
      progress,
      stage: makeNode("span"),
      series: makeNode("span"),
      status: makeNode("div"),
    },
  };
}

test("renderError renders advice as trailing paragraph with class error-hint", () => {
  const banner = makeNode("div");

  renderError(banner, "сообщение", "подсказка");

  const last = banner.children.at(-1);
  assert.equal(last.className, "error-hint");
  assert.equal(last.textContent, "подсказка");
  assert.equal(banner.hidden, false);
});

test("renderError without advice adds no hint paragraph", () => {
  const banner = makeNode("div");

  renderError(banner, "сообщение");

  assert.ok(banner.children.every((child) => !String(child.className).includes("error-hint")));
});

test("renderError with empty message hides and clears the banner", () => {
  const banner = makeNode("div");
  banner.children = [makeNode("p")];

  renderError(banner, "");

  assert.equal(banner.hidden, true);
  assert.equal(banner.children.length, 0);
});

test("renderJobProgress sets rail-running while running", () => {
  const { section, els } = makeJobElements();

  renderJobProgress(els, snapshotWith("running"));

  assert.deepEqual([...section.classes], ["rail-running"]);
});

test("renderJobProgress sets terminal rail classes", () => {
  const cases = [
    ["succeeded", "rail-ok"],
    ["failed", "rail-error"],
    ["cancelled", "rail-warn"],
  ];
  for (const [status, expected] of cases) {
    const { section, els } = makeJobElements();

    renderJobProgress(els, snapshotWith(status, "done"));

    assert.deepEqual([...section.classes], [expected], `статус ${status}`);
  }
});

test("renderJobProgress swaps rail class on transition", () => {
  const { section, els } = makeJobElements();

  renderJobProgress(els, snapshotWith("running"));
  renderJobProgress(els, snapshotWith("failed", "done"));

  assert.deepEqual([...section.classes], ["rail-error"]);
});

test("renderJobProgress tolerates missing section", () => {
  const { els } = makeJobElements();
  els.progress.closest = () => null;

  assert.doesNotThrow(() => renderJobProgress(els, snapshotWith("running")));
});
