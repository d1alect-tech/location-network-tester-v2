/** V6 RED-контракты раздела «Захват» (TDD RED, T2) — test-side зеркало
 * capture.spec.ts (vitest-конфиг исключает *.spec.ts, поэтому контракты здесь).
 * Эталон: showcase-round2/kit.css + variantV6.css (только чтение).
 * Падение — только по missing V6 class. Селекторы input[name=capture-mode]
 * ПИНЯТСЯ как есть: D1=A radio-card их сохраняет, зелёный пин ниже. */

import { describe, expect, it } from "vitest";
import type { LntApiClient } from "./api/client";
import { createCaptureView } from "./capture/captureView";
import { createDisclosure } from "./capture/disclosure";
import { createModeForm } from "./capture/modeForm";

function stubClient(): LntApiClient {
  return {
    bootstrap: async () => undefined,
    currentNonce: null,
    jobs: { list: async () => ({ items: [] }) },
  } as unknown as LntApiClient;
}

describe("захват V6: radio-card D1=A (пин, уже зелёный)", () => {
  it("input[name=capture-mode] остаются как есть: 4 режима, RC по умолчанию", () => {
    // Given / When
    const form = createModeForm();

    // Then: контракт D1=A radio-card — селекторы пинятся, портирование их хранит
    const radios = form.root.querySelectorAll('input[name="capture-mode"]');
    expect(radios).toHaveLength(4);
    const checked = form.root.querySelector<HTMLInputElement>(
      'input[name="capture-mode"]:checked',
    );
    expect(checked?.value).toBe("rc_measurement");
  });
});

describe("захват V6: кнопки .btn/.btn-secondary/.btn-quiet", () => {
  it("старт — .btn, вторичные действия — .btn-secondary/.btn-quiet", () => {
    // Given: смонтированное представление захвата
    const view = createCaptureView(stubClient());
    try {
      // Then: V6-кнопки kit.css (§2.3)
      const start = [...view.root.querySelectorAll("button")].find(
        (button) => button.textContent === "Запустить запись",
      );
      expect(start, "должна быть кнопка «Запустить запись»").not.toBeNull();
      expect(
        start?.classList.contains("btn"),
        "V6-разрыв: старт без .btn (сейчас lnt-btn lnt-btn-primary)",
      ).toBe(true);
      expect(
        view.root.querySelector(".btn-secondary"),
        "V6-разрыв: нет .btn-secondary (вторичное действие)",
      ).not.toBeNull();
      expect(
        view.root.querySelector(".btn-quiet"),
        "V6-разрыв: нет .btn-quiet (тихая кнопка 28px)",
      ).not.toBeNull();
    } finally {
      view.dispose();
      view.root.remove();
    }
  });
});

describe("захват V6: форма .field/.ctl", () => {
  it("поля — .field с подписью, контролы — .ctl 32px", () => {
    // Given / When
    const form = createModeForm();

    // Then: V6-формы kit.css (§2.3: инпут/селект 32px, рамка, фон ступенью темнее)
    expect(
      form.root.querySelector(".field"),
      "V6-разрыв: нет .field (сейчас lnt-* обёртки)",
    ).not.toBeNull();
    const controls = form.root.querySelectorAll("input.ctl, select.ctl");
    expect(
      controls.length > 0,
      "V6-разрыв: нет input.ctl/select.ctl (сейчас lnt-input)",
    ).toBe(true);
  });
});

describe("захват V6: раскрытие .disc-toggle", () => {
  it("«Серия и протокол» — кнопка .disc-toggle с aria-expanded", () => {
    // Given / When
    const { root } = createDisclosure("Серия и протокол");

    // Then: V6-disclosure kit.css (стрелка ▸, поворот при expanded)
    const toggle = root.querySelector("button.disc-toggle");
    expect(
      toggle,
      "V6-разрыв: нет button.disc-toggle (сейчас lnt-btn lnt-disclosure-toggle)",
    ).not.toBeNull();
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    expect(toggle?.getAttribute("aria-controls")).not.toBeNull();
  });
});

describe("захват V6: глифы и сетка показаний", () => {
  it("превью профиля — .readout-grid, состояния — .glyph", () => {
    // Given
    const view = createCaptureView(stubClient());
    try {
      // Then: показания V6 (readout-grid) + глифы состояний (§6: не только цвет)
      expect(
        view.root.querySelector(".readout-grid"),
        "V6-разрыв: нет .readout-grid в превью профиля",
      ).not.toBeNull();
      expect(
        view.root.querySelector(".glyph"),
        "V6-разрыв: нет .glyph для кодирования состояния",
      ).not.toBeNull();
    } finally {
      view.dispose();
      view.root.remove();
    }
  });
});

describe("захват V6: страница .t-page и 375px", () => {
  it("корень — .t-page, заголовок — .panel-title, без фиксированной ширины", () => {
    // Given
    const view = createCaptureView(stubClient());
    try {
      // Then: V6-страница — fluid-контракт включает персону 375px без обрезки
      // контролов (проверено e2e capture.spec.ts «375px mobile»)
      expect(
        view.root.classList.contains("t-page"),
        "V6-разрыв: корень захвата без .t-page (сейчас .capture-view)",
      ).toBe(true);
      expect(
        view.root.querySelector(".panel-title"),
        "V6-разрыв: заголовок без .panel-title (сейчас .view-title)",
      ).not.toBeNull();
      expect(view.root.getAttribute("style") ?? "").not.toContain("min-width");
    } finally {
      view.dispose();
      view.root.remove();
    }
  });
});
