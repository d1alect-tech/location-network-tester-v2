/** Секция декларации адаптера (N7): поля, значения, ошибки и динамика
 * подсказки/пола длительности. Пол — консультативное зеркало
 * analysisFloorSeconds; движение — объявленный контракт H12: подсказка и
 * предупреждение живут в слотах с зарезервированной высотой. */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { createAdapterDeclarationSection } from "./adapterDeclarationForm";
import { ADAPTER_PRESET, analysisFloorSeconds } from "./adapterPreset";
import { createModeForm } from "./modeForm";
import { DEFAULT_FORM_VALUES, validateCaptureForm } from "./modes";
import type { CaptureFormValues } from "./modes";

function values(overrides: Partial<CaptureFormValues> = {}): CaptureFormValues {
  return { ...DEFAULT_FORM_VALUES, ...overrides };
}

describe("createAdapterDeclarationSection: разметка и дефолты", () => {
  it("строит fieldset.capture-adapter-group с legend и дефолтами пресета", () => {
    const section = createAdapterDeclarationSection();
    document.body.replaceChildren(section.root);

    expect(section.root.tagName).toBe("FIELDSET");
    expect(section.root.className).toContain("capture-adapter-group");
    expect(section.root.querySelector("legend")?.textContent).toBe("Декларация адаптера");

    // Пресет импортирован из N4, а не захардкожен числами.
    const cap = document.querySelector<HTMLInputElement>('input[name="adapter_cap_nf"]');
    const series = document.querySelector<HTMLInputElement>('input[name="adapter_series_r_ohm"]');
    expect(cap?.value).toBe(String(ADAPTER_PRESET.capNfNominal));
    expect(series?.value).toBe(String(ADAPTER_PRESET.seriesROhmNominal));

    const confirm = document.querySelector<HTMLInputElement>('input[name="adapter_preconnected"]');
    expect(confirm?.type).toBe("checkbox");
    expect(confirm?.checked).toBe(false);

    const basis = document.querySelectorAll<HTMLInputElement>(
      'input[name="adapter_component_values_basis"]',
    );
    expect([...basis].map((input) => input.value).sort()).toEqual(["nominal", "operator_measured"]);
    expect(basis[0]?.checked).toBe(true);
  });

  it("подписи полей и статическая строка тракта записи дословны", () => {
    const section = createAdapterDeclarationSection();
    document.body.replaceChildren(section.root);

    expect(section.root.textContent).toContain(
      "Адаптер подключён до старта, переподключений в эпохе записи не было",
    );
    expect(section.root.textContent).toContain(
      "Без этого подтверждения публичные числа ripple будут недоступны (settling_unknown)",
    );
    expect(section.root.textContent).toContain("Ёмкость C, нФ");
    expect(section.root.textContent).toContain("Последовательный R, Ом");
    expect(section.root.textContent).toContain("номинал");
    expect(section.root.textContent).toContain("измерено оператором");
    expect(section.root.textContent).toContain(
      "Вход осциллографа: 1 МОм (номинал) · пробник x1 — фиксируются трактом записи",
    );
  });

  it("НЕТ поля пробника и поля 1 МОм — ровно пять input в секции (H7)", () => {
    const section = createAdapterDeclarationSection();
    document.body.replaceChildren(section.root);

    const inputs = section.root.querySelectorAll("input");
    expect(inputs).toHaveLength(5); // чекбокс + C + Rs + два радио базиса
    expect(section.root.querySelector('input[name*="probe"]')).toBeNull();
    expect(section.root.querySelector('input[name*="rin"]')).toBeNull();
  });
});

describe("createAdapterDeclarationSection: значения и ошибки", () => {
  it("values() читает галку, числа и базис с radio-пары", () => {
    const section = createAdapterDeclarationSection();
    document.body.replaceChildren(section.root);
    const cap = document.querySelector<HTMLInputElement>('input[name="adapter_cap_nf"]');
    const series = document.querySelector<HTMLInputElement>('input[name="adapter_series_r_ohm"]');
    const confirm = document.querySelector<HTMLInputElement>('input[name="adapter_preconnected"]');
    const measured = document.querySelector<HTMLInputElement>(
      'input[name="adapter_component_values_basis"][value="operator_measured"]',
    );
    if (!cap || !series || !confirm || !measured) throw new Error("нет полей секции");

    expect(section.values()).toEqual({
      adapterCapNf: "100",
      adapterSeriesROhm: "0",
      adapterPreconnected: false,
      adapterBasis: "nominal",
    });

    cap.value = "220";
    series.value = "4.7";
    confirm.checked = true;
    measured.checked = true;
    expect(section.values()).toEqual({
      adapterCapNf: "220",
      adapterSeriesROhm: "4.7",
      adapterPreconnected: true,
      adapterBasis: "operator_measured",
    });
  });

  it("setErrors помечает поля C и Rs, clearErrors снимает", () => {
    const section = createAdapterDeclarationSection();
    document.body.replaceChildren(section.root);

    section.setErrors({
      adapterCapNf: "Ёмкость C должна быть положительным числом нанофарад.",
      adapterSeriesROhm: "Последовательный R должен быть неотрицательным числом ом.",
    });
    const cap = document.querySelector<HTMLInputElement>('input[name="adapter_cap_nf"]');
    const series = document.querySelector<HTMLInputElement>('input[name="adapter_series_r_ohm"]');
    expect(cap?.getAttribute("aria-invalid")).toBe("true");
    expect(series?.getAttribute("aria-invalid")).toBe("true");
    expect(section.root.textContent).toContain("положительным числом нанофарад");
    expect(section.root.textContent).toContain("неотрицательным числом ом");

    section.clearErrors();
    expect(cap?.getAttribute("aria-invalid")).toBe("false");
    expect(series?.getAttribute("aria-invalid")).toBe("false");
  });
});

describe("createAdapterDeclarationSection: динамика слотов (H12/D5)", () => {
  it("подсказка «стартуйте сразу» видна без галки и скрыта с галкой", () => {
    const section = createAdapterDeclarationSection();
    document.body.replaceChildren(section.root);
    const hint = section.root.querySelector<HTMLElement>(".capture-adapter-hint");

    section.sync(values({ adapterPreconnected: false }));
    expect(hint?.hidden).toBe(false);
    expect(hint?.textContent).toBe(
      "подключите и стартуйте сразу — первые 10τ будут отброшены движком",
    );

    section.sync(values({ adapterPreconnected: true }));
    expect(hint?.hidden).toBe(true);
  });

  it("пол длительности скрыт на дефолте (2.4 ≥ 2.0) и появляется под полом", () => {
    const section = createAdapterDeclarationSection();
    document.body.replaceChildren(section.root);
    const floor = section.root.querySelector<HTMLElement>(".capture-adapter-floor");

    section.sync(values());
    expect(floor?.hidden).toBe(true);

    section.sync(values({ adapterCapNf: "1000" }));
    expect(floor?.hidden).toBe(false);
    expect(floor?.textContent).toBe(
      "При C=1000 нФ и fs=8000000 Гц окну анализа нужно ≥11 с записи — увеличьте длительность.",
    );

    section.sync(values({ adapterCapNf: "100" }));
    expect(floor?.hidden).toBe(true);
  });

  it("пол пересчитывается от длительности и гаснет на невалидных числах", () => {
    const section = createAdapterDeclarationSection();
    document.body.replaceChildren(section.root);
    const floor = section.root.querySelector<HTMLElement>(".capture-adapter-floor");

    section.sync(values({ durationS: "0.5" }));
    expect(floor?.hidden).toBe(false);
    expect(floor?.textContent).toContain("нужно ≥2 с записи");

    section.sync(values({ adapterCapNf: "не-число" }));
    expect(floor?.hidden).toBe(true);
  });

  it("текст пола согласован с analysisFloorSeconds на больших C", () => {
    const section = createAdapterDeclarationSection();
    document.body.replaceChildren(section.root);
    const floor = section.root.querySelector<HTMLElement>(".capture-adapter-floor");

    const capNf = 4700;
    const expected = analysisFloorSeconds(capNf, 0, 8_000_000);
    if (expected === null) throw new Error("floor не должен быть null");
    section.sync(values({ adapterCapNf: "4700" }));
    expect(floor?.textContent).toContain(`≥${expected} с записи`);
  });

  it("слоты подсказки и пола держат зарезервированную минимальную высоту", () => {
    // jsdom не считает каскад: резерв проверяется по реальному CSS-файлу
    // (идиома captureLayout.test.ts — реальные селекторы реальных таблиц).
    const roots = [
      resolve(process.cwd(), "src/capture"),
      resolve(process.cwd(), "frontend/src/capture"),
    ];
    const cssPath = roots.map((root) => `${root}/captureForms.css`).find(existsSync);
    if (cssPath === undefined) throw new Error("не найден captureForms.css");
    const css = readFileSync(cssPath, "utf8");
    expect(css).toMatch(/\.capture-view \.capture-adapter-slot\s*\{[^}]*min-height:\s*\d+px/s);
    expect(css).toMatch(/\.capture-view \.capture-adapter-notices\s*\{/);
  });
});

describe("createModeForm: интеграция секции декларации", () => {
  it("секция скрыта для прочих режимов и для симулятора, видна для ripple+device", () => {
    const form = createModeForm();
    document.body.replaceChildren(form.root);
    const section = form.sections.adapter;

    // Дефолт: rc_measurement + симулятор — скрыта.
    expect(section.hidden).toBe(true);

    const ripple = document.querySelector<HTMLInputElement>(
      'input[name="capture-mode"][value="ripple_measurement"]',
    );
    const device = document.querySelector<HTMLInputElement>(
      'input[name="capture-source"][value="device"]',
    );
    if (!ripple || !device) throw new Error("нет радио режима/источника");

    // ripple + симулятор — всё ещё скрыта.
    ripple.checked = true;
    ripple.dispatchEvent(new Event("change", { bubbles: true }));
    expect(section.hidden).toBe(true);

    // ripple + осциллограф — видна.
    device.checked = true;
    device.dispatchEvent(new Event("change", { bubbles: true }));
    expect(section.hidden).toBe(false);

    // Возврат к прочему режиму — снова скрыта.
    const rc = document.querySelector<HTMLInputElement>(
      'input[name="capture-mode"][value="rc_measurement"]',
    );
    if (!rc) throw new Error("нет радио rc");
    rc.checked = true;
    rc.dispatchEvent(new Event("change", { bubbles: true }));
    expect(section.hidden).toBe(true);
  });

  it("values() формы объединяет настройки и декларацию адаптера", () => {
    const form = createModeForm();
    document.body.replaceChildren(form.root);

    expect(form.values().adapterCapNf).toBe("100");
    expect(form.values().adapterSeriesROhm).toBe("0");
    expect(form.values().adapterPreconnected).toBe(false);
    expect(form.values().adapterBasis).toBe("nominal");

    const confirm = form.root.querySelector<HTMLInputElement>('input[name="adapter_preconnected"]');
    if (!confirm) throw new Error("нет чекбокса");
    confirm.checked = true;
    confirm.dispatchEvent(new Event("change", { bubbles: true }));
    expect(form.values().adapterPreconnected).toBe(true);
  });

  it("ввод длительности на шаге 2 пересчитывает пол через sync", () => {
    const form = createModeForm();
    document.body.replaceChildren(form.root);
    const ripple = form.root.querySelector<HTMLInputElement>(
      'input[name="capture-mode"][value="ripple_measurement"]',
    );
    const device = form.root.querySelector<HTMLInputElement>(
      'input[name="capture-source"][value="device"]',
    );
    const duration = form.root.querySelector<HTMLInputElement>('input[name="duration_s"]');
    if (!ripple || !device || !duration) throw new Error("нет полей");
    ripple.checked = true;
    device.checked = true;
    ripple.dispatchEvent(new Event("change", { bubbles: true }));

    const floor = form.sections.adapter.querySelector<HTMLElement>(".capture-adapter-floor");
    expect(floor?.hidden).toBe(true);

    duration.value = "0.5";
    duration.dispatchEvent(new Event("input", { bubbles: true }));
    expect(floor?.hidden).toBe(false);
    expect(floor?.textContent).toContain("увеличьте длительность");
  });

  it("дефолтные значения формы проходят валидацию вместе с декларацией", () => {
    const form = createModeForm();
    const { valid, errors } = validateCaptureForm(form.values());
    expect(errors).toEqual({});
    expect(valid?.adapterCapNf).toBe(100);
    expect(valid?.adapterSeriesROhm).toBe(0);
    expect(valid?.adapterPreconnected).toBe(false);
    expect(valid?.adapterBasis).toBe("nominal");
  });
});
