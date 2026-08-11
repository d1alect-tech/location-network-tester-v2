import assert from "node:assert/strict";
import test from "node:test";

import {
  THEME_KEY,
  createThemeController,
  normalizePreference,
  resolveTheme,
} from "../../src/lnt/ui/static/theme.js";

class FakeRoot {
  constructor() {
    this.dataset = {};
  }
}

class FakeSelect {
  constructor() {
    this.value = "";
    this.listeners = new Set();
    this.addCalls = 0;
    this.removeCalls = 0;
  }

  addEventListener(type, listener) {
    assert.equal(type, "change");
    this.addCalls += 1;
    this.listeners.add(listener);
  }

  removeEventListener(type, listener) {
    assert.equal(type, "change");
    this.removeCalls += 1;
    this.listeners.delete(listener);
  }

  change(value) {
    this.value = value;
    for (const listener of this.listeners) {
      listener({ type: "change" });
    }
  }
}

class FakeStorage {
  constructor(value = null) {
    this.value = value;
    this.reads = [];
    this.writes = [];
    this.getError = null;
    this.setError = null;
  }

  getItem(key) {
    this.reads.push(key);
    if (this.getError) {
      throw this.getError;
    }
    return this.value;
  }

  setItem(key, value) {
    this.writes.push([key, value]);
    if (this.setError) {
      throw this.setError;
    }
    this.value = value;
  }
}

class FakeMedia {
  constructor(matches = false) {
    this.matches = matches;
    this.listeners = new Set();
    this.addCalls = 0;
    this.removeCalls = 0;
  }

  addEventListener(type, listener) {
    assert.equal(type, "change");
    this.addCalls += 1;
    this.listeners.add(listener);
  }

  removeEventListener(type, listener) {
    assert.equal(type, "change");
    this.removeCalls += 1;
    this.listeners.delete(listener);
  }

  change(matches) {
    this.matches = matches;
    for (const listener of this.listeners) {
      listener({ matches });
    }
  }
}

function setup({ stored = null, prefersDark = false } = {}) {
  const root = new FakeRoot();
  const select = new FakeSelect();
  const storage = new FakeStorage(stored);
  const media = new FakeMedia(prefersDark);
  const controller = createThemeController({ root, select, storage, media });
  return { controller, media, root, select, storage };
}

test("exports the stable storage key", () => {
  assert.equal(THEME_KEY, "lnt-theme");
});

test("normalizes unsupported preferences to system", () => {
  for (const value of ["system", "light", "dark"]) {
    assert.equal(normalizePreference(value), value);
  }
  for (const value of [null, undefined, "", "LIGHT", "sepia", 1]) {
    assert.equal(normalizePreference(value), "system");
  }
});

test("resolves system from media and preserves explicit themes", () => {
  assert.equal(resolveTheme("system", false), "light");
  assert.equal(resolveTheme("system", true), "dark");
  assert.equal(resolveTheme("light", true), "light");
  assert.equal(resolveTheme("dark", false), "dark");
  assert.equal(resolveTheme("invalid", true), "dark");
});

test("start reads, applies, syncs, and attaches each listener once", () => {
  const { controller, media, root, select, storage } = setup({ stored: "dark" });

  controller.start();
  controller.start();

  assert.equal(root.dataset.theme, "dark");
  assert.equal(select.value, "dark");
  assert.deepEqual(storage.reads, [THEME_KEY]);
  assert.equal(select.addCalls, 1);
  assert.equal(media.addCalls, 1);
  assert.equal(select.listeners.size, 1);
  assert.equal(media.listeners.size, 1);
});

test("select changes normalize, apply, sync, and persist", () => {
  const { controller, media, root, select, storage } = setup({ prefersDark: true });
  controller.start();

  select.change("light");
  assert.equal(root.dataset.theme, "light");
  assert.equal(select.value, "light");
  assert.deepEqual(storage.writes, [[THEME_KEY, "light"]]);

  select.change("sepia");
  assert.equal(root.dataset.theme, "dark");
  assert.equal(select.value, "system");
  assert.deepEqual(storage.writes.at(-1), [THEME_KEY, "system"]);
  assert.equal(media.matches, true);
});

test("media changes apply only to the system preference", () => {
  const { controller, media, root, select } = setup();
  controller.start();

  media.change(true);
  assert.equal(root.dataset.theme, "dark");

  select.change("dark");
  media.change(false);
  assert.equal(root.dataset.theme, "dark");
});

test("stop is idempotent, cleans up, and permits a fresh lifecycle", () => {
  const { controller, media, root, select, storage } = setup({ stored: "dark" });
  controller.start();
  controller.stop();
  controller.stop();

  assert.equal(select.removeCalls, 1);
  assert.equal(media.removeCalls, 1);
  assert.equal(select.listeners.size, 0);
  assert.equal(media.listeners.size, 0);

  select.change("light");
  media.change(true);
  assert.equal(root.dataset.theme, "dark");
  assert.deepEqual(storage.writes, []);

  storage.value = "light";
  controller.start();
  assert.equal(root.dataset.theme, "light");
  assert.equal(select.value, "light");
  assert.deepEqual(storage.reads, [THEME_KEY, THEME_KEY]);
  assert.equal(select.addCalls, 2);
  assert.equal(media.addCalls, 2);
});

test("DOMException reads fall back to system", () => {
  const { controller, media, root, select, storage } = setup({ prefersDark: true });
  storage.getError = new DOMException("blocked", "SecurityError");

  controller.start();

  assert.equal(root.dataset.theme, "dark");
  assert.equal(select.value, "system");
  assert.equal(select.listeners.size, 1);
  assert.equal(media.listeners.size, 1);
});

test("DOMException writes preserve in-memory behavior", () => {
  const { controller, media, root, select, storage } = setup();
  storage.setError = new DOMException("blocked", "SecurityError");
  controller.start();

  assert.doesNotThrow(() => select.change("light"));
  assert.equal(root.dataset.theme, "light");
  assert.equal(select.value, "light");
  media.change(true);
  assert.equal(root.dataset.theme, "light");
});

test("non-DOMException storage failures are rethrown", () => {
  const readFailure = new Error("read failed");
  const readCase = setup();
  readCase.storage.getError = readFailure;
  assert.throws(() => readCase.controller.start(), readFailure);
  assert.equal(readCase.select.listeners.size, 0);
  assert.equal(readCase.media.listeners.size, 0);

  const writeFailure = new Error("write failed");
  const writeCase = setup();
  writeCase.storage.setError = writeFailure;
  writeCase.controller.start();
  assert.throws(() => writeCase.select.change("dark"), writeFailure);
});
