import assert from "node:assert/strict";
import { test } from "node:test";

import { renderCh1Section } from "../../src/lnt/ui/static/ch1-input-reference.js";

// Minimal DOM double: records text assignments and throws if any node is ever
// populated through innerHTML, so hostile payloads can only survive as text.
function makeDoc() {
  function createElement(tag) {
    return {
      tagName: String(tag).toUpperCase(),
      className: "",
      children: [],
      _text: null,
      append(...kids) {
        this.children.push(...kids);
      },
      set textContent(value) {
        this._text = String(value);
        this.children = [];
      },
      get textContent() {
        if (this._text !== null) return this._text;
        return this.children.map((child) => child.textContent).join("");
      },
      set innerHTML(_value) {
        throw new Error("innerHTML must never be used for untrusted content");
      },
    };
  }
  return { createElement };
}

function collectByClass(node, className, found = []) {
  if (String(node.className ?? "").split(" ").includes(className)) found.push(node);
  for (const child of node.children ?? []) collectByClass(child, className, found);
  return found;
}

test("available reference surfaces status, model kind and qualified counts", () => {
  const section = renderCh1Section(
    {
      ch1_input_reference: {
        status: "available",
        model_kind: "floating_differential_rc_shunt_v1",
        qualified_bin_count: 42,
        total_bin_count: 100,
      },
    },
    makeDoc(),
  );
  const text = section.textContent;
  assert.match(text, /scope-plane/);
  assert.match(text, /не приведён ко входу/);
  assert.equal(collectByClass(section, "ch1-input-reference").length, 1);
  assert.match(text, /Доступно/);
  assert.match(text, /floating_differential_rc_shunt_v1/);
  assert.match(text, /42\/100/);
});

test("unavailable reference surfaces the machine-readable reason code", () => {
  const section = renderCh1Section(
    { ch1_input_reference: { status: "unavailable", reason_code: "manifest_schema_v1" } },
    makeDoc(),
  );
  assert.match(section.textContent, /Недоступно/);
  assert.match(section.textContent, /manifest_schema_v1/);
});

test("legacy analysis without input reference keeps only the scope-plane note", () => {
  const section = renderCh1Section({}, makeDoc());
  assert.match(section.textContent, /scope-plane/);
  assert.equal(collectByClass(section, "ch1-input-reference").length, 0);
});

test("unknown status renders its raw value without throwing", () => {
  const section = renderCh1Section(
    { ch1_input_reference: { status: "partial", reason_code: "experimental_path" } },
    makeDoc(),
  );
  assert.match(section.textContent, /partial/);
  assert.equal(collectByClass(section, "ch1-input-reference").length, 1);
});

test("zero counts render as 0/0 instead of being hidden", () => {
  const section = renderCh1Section(
    {
      ch1_input_reference: {
        status: "available",
        model_kind: "scope_input_terminated_v1",
        qualified_bin_count: 0,
        total_bin_count: 0,
      },
    },
    makeDoc(),
  );
  assert.match(section.textContent, /0\/0/);
});

test("hostile reason text is rendered as text, never as HTML", () => {
  const hostile = "<img src=x onerror=alert(1)>";
  const section = renderCh1Section(
    { ch1_input_reference: { status: "unavailable", reason_code: hostile } },
    makeDoc(),
  );
  assert.ok(section.textContent.includes(hostile));
});
