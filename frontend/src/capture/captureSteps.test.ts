/** Визард «Захвата» (G4, вариант 3): машина шагов 1→2→3, гейт валидации на
 * «Далее» с шага 2, перенос секций формы в панели, эхо выбора чипами. */

import { describe, expect, it, vi } from "vitest";
import { el } from "../components/primitives/dom";
import { createCaptureSteps } from "./captureSteps";
import { CAPTURE_MODES } from "./modes";

function harness(validate = true) {
  const sections = {
    modes: el("div", { attrs: { "data-marker": "modes" } }),
    source: el("div", { attrs: { "data-marker": "source" } }),
    paramsTitle: el("h3", { text: "Параметры записи" }),
    settings: el("div", { attrs: { "data-marker": "settings" } }),
    series: el("div", { attrs: { "data-marker": "series" } }),
  };
  const form = el("form", {}, [
    sections.modes,
    sections.source,
    sections.paramsTitle,
    sections.settings,
    sections.series,
  ]) as HTMLFormElement;
  const launchNode = el("div", { attrs: { "data-marker": "launch" } });
  const validateStep2 = vi.fn(() => validate);
  const onStep = vi.fn();
  const handle = createCaptureSteps({
    form,
    sections,
    launch: [launchNode],
    validateStep2,
    onStep,
  });
  document.body.replaceChildren(form, handle.rail, handle.panel3);
  const panel = (step: number): HTMLElement => {
    const found = document.querySelector<HTMLElement>(`[data-capture-step="${step}"]`);
    if (found === null) throw new Error(`нет панели шага ${step}`);
    return found;
  };
  const clickButton = (label: string): void => {
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
      (node) => node.textContent === label,
    );
    if (button === undefined) throw new Error(`нет кнопки «${label}»`);
    button.click();
  };
  const railItem = (step: number): HTMLElement => {
    const found = handle.rail.querySelector<HTMLElement>(`[data-step="${step}"]`);
    if (found === null) throw new Error(`нет пункта рельса ${step}`);
    return found;
  };
  return { handle, form, sections, panel, clickButton, railItem, validateStep2, onStep };
}

describe("createCaptureSteps: раскладка секций по панелям", () => {
  it("секции шагов 1–2 живут внутри формы, прежний h3 заменён заголовком шага", () => {
    // Given / When
    const { form, sections, panel } = harness();

    // Then: панели 1–2 — дети формы (делегирование change/input сохранено)
    expect(panel(1).parentElement).toBe(form);
    expect(panel(2).parentElement).toBe(form);
    expect(panel(1).contains(sections.modes)).toBe(true);
    expect(panel(1).contains(sections.source)).toBe(true);
    expect(panel(2).contains(sections.settings)).toBe(true);
    expect(panel(2).contains(sections.series)).toBe(true);
    expect(form.querySelector("h3.capture-section-title")).toBeNull();
    expect(panel(2).querySelector(".capture-step-title")?.textContent).toBe(
      "Шаг 2 · Параметры записи",
    );
  });

  it("узел запуска владельца попадает в панель шага 3", () => {
    // Given / When
    const { panel } = harness();

    // Then
    expect(panel(3).querySelector('[data-marker="launch"]')).not.toBeNull();
  });
});

describe("createCaptureSteps: переходы 1→2→3 и назад", () => {
  it("старт на шаге 1: панели 2–3 скрыты, рельс помечен aria-current", () => {
    // Given / When
    const { handle, panel, railItem } = harness();

    // Then
    expect(handle.current()).toBe(1);
    expect(panel(1).hidden).toBe(false);
    expect(panel(2).hidden).toBe(true);
    expect(handle.panel3.hidden).toBe(true);
    expect(railItem(1).dataset.state).toBe("current");
    expect(railItem(1).getAttribute("aria-current")).toBe("step");
    expect(railItem(2).dataset.state).toBe("todo");
    expect(railItem(2).getAttribute("aria-current")).toBe("false");
  });

  it("«Далее» открывает шаг 2, «Назад» возвращает на шаг 1", () => {
    // Given
    const { handle, panel, clickButton, railItem, onStep } = harness();

    // When
    clickButton("Далее: параметры");

    // Then
    expect(handle.current()).toBe(2);
    expect(panel(1).hidden).toBe(true);
    expect(panel(2).hidden).toBe(false);
    expect(railItem(1).dataset.state).toBe("done");
    expect(railItem(1).querySelector(".capture-stepnum")?.textContent).toBe("✓");
    expect(railItem(2).getAttribute("aria-current")).toBe("step");
    expect(onStep).toHaveBeenCalledWith(2);

    // When
    clickButton("Назад: режим");

    // Then
    expect(handle.current()).toBe(1);
    expect(panel(1).hidden).toBe(false);
    expect(panel(2).hidden).toBe(true);
  });

  it("«Далее: запуск» с валидной формой открывает шаг 3", () => {
    // Given
    const { handle, panel, clickButton, validateStep2 } = harness(true);
    clickButton("Далее: параметры");

    // When
    clickButton("Далее: запуск");

    // Then
    expect(validateStep2).toHaveBeenCalled();
    expect(handle.current()).toBe(3);
    expect(panel(2).hidden).toBe(true);
    expect(handle.panel3.hidden).toBe(false);
  });

  it("невалидная форма держит оператора на шаге 2 (гейт не пройден)", () => {
    // Given
    const { handle, panel, clickButton, validateStep2 } = harness(false);
    clickButton("Далее: параметры");

    // When
    clickButton("Далее: запуск");

    // Then
    expect(validateStep2).toHaveBeenCalled();
    expect(handle.current()).toBe(2);
    expect(panel(2).hidden).toBe(false);
    expect(handle.panel3.hidden).toBe(true);
  });

  it("клик по рельсу прыгает на шаг напрямую; show() — программный переход", () => {
    // Given
    const { handle, panel, railItem } = harness();

    // When: рельс — свободный прыжок (стартовая строка всё равно валидирует)
    railItem(3).click();

    // Then
    expect(handle.current()).toBe(3);
    expect(panel(1).hidden).toBe(true);
    expect(panel(3).hidden).toBe(false);
    expect(railItem(1).dataset.state).toBe("done");
    expect(railItem(3).dataset.state).toBe("current");

    // When: восстановление задачи зовёт show() без клика
    handle.show(1);

    // Then
    expect(handle.current()).toBe(1);
    expect(panel(1).hidden).toBe(false);
  });

  it("подсказка «Шаг N из 3» есть в действиях каждой панели", () => {
    // Given / When
    const { panel } = harness();

    // Then
    expect(panel(1).textContent).toContain("Шаг 1 из 3");
    expect(panel(2).textContent).toContain("Шаг 2 из 3");
    expect(panel(3).textContent).toContain("Шаг 3 из 3");
  });
});

describe("createCaptureSteps: эхо выбора чипами", () => {
  it("renderEcho рисует режим, источник, каналы и тип сессии", () => {
    // Given
    const { handle, panel } = harness();

    // When
    handle.renderEcho(CAPTURE_MODES.line_quality, "device");

    // Then
    const echo = panel(2).querySelector(".capture-echo");
    expect(echo?.textContent).toContain("Качество сети (трансформатор 230:6)");
    expect(echo?.textContent).toContain("осциллограф");
    expect(echo?.textContent).toContain("каналы: 1");
    expect(echo?.textContent).toContain("Качество сети (line_quality)");
    expect(echo?.querySelector('.capture-chip[data-tone="accent"]')).not.toBeNull();
  });

  it("повторный renderEcho заменяет чипы, а не копит их", () => {
    // Given
    const { handle, panel } = harness();
    handle.renderEcho(CAPTURE_MODES.rc_measurement, "simulator");

    // When
    handle.renderEcho(CAPTURE_MODES.self_noise, "simulator");

    // Then
    const chips = panel(2).querySelectorAll(".capture-chip");
    expect(chips).toHaveLength(4);
    expect(panel(2).querySelector(".capture-echo")?.textContent).toContain(
      "Терминированный самошум",
    );
  });
});
