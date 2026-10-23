/** Preflight «Настроек» читает живую форму захвата: четыре поля декларации
 * адаптера должны попадать в capture-запрос с их настоящими типами (галка —
 * boolean, базис — литерал с radio-пары), а отсутствующие в DOM поля
 * откатываются к DEFAULT_FORM_VALUES. */

import { describe, expect, it } from "vitest";
import { createModeForm } from "../../capture/modeForm";
import { readCapturePreflightRequest } from "./settingsPreflight";

function mountForm(): HTMLFormElement {
  const form = createModeForm();
  document.body.replaceChildren(form.root);
  return form.root;
}

describe("readCapturePreflightRequest: декларация адаптера из живой формы", () => {
  it("ripple-режим несёт adapter_declaration с полями формы", () => {
    const root = mountForm();
    const ripple = root.querySelector<HTMLInputElement>(
      'input[name="capture-mode"][value="ripple_measurement"]',
    );
    const device = root.querySelector<HTMLInputElement>(
      'input[name="capture-source"][value="device"]',
    );
    const cap = root.querySelector<HTMLInputElement>('input[name="adapter_cap_nf"]');
    const confirm = root.querySelector<HTMLInputElement>('input[name="adapter_preconnected"]');
    const measured = root.querySelector<HTMLInputElement>(
      'input[name="adapter_component_values_basis"][value="operator_measured"]',
    );
    if (!ripple || !device || !cap || !confirm || !measured) throw new Error("нет полей");
    ripple.checked = true;
    device.checked = true;
    cap.value = "220";
    confirm.checked = true;
    measured.checked = true;

    const request = readCapturePreflightRequest();
    expect(request.kind).toBe("capture");
    expect(request.adapter_declaration).toEqual({
      preconnected: true,
      cap_nf: 220,
      series_r_ohm: 0,
      component_values_basis: "operator_measured",
    });
  });

  it("прочий режим не несёт декларации; формы нет — откат к дефолтам", () => {
    const root = mountForm();
    const request = readCapturePreflightRequest(root);
    expect(request.kind).toBe("capture");
    expect(request.adapter_declaration).toBeUndefined();

    const withoutForm = readCapturePreflightRequest(
      document.implementation.createDocument("http://www.w3.org/1999/xhtml", "html", null),
    );
    expect(withoutForm.kind).toBe("capture");
  });
});
