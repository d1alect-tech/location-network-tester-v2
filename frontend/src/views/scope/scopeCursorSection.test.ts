/** Todo 10 RED: секция «Курсоры» — ползунки + readout Δt/ΔV и uPlot-плагин
 * линий курсоров (паттерн annotations.createPeaksPlugin). Плагин
 * тестируется на фальшивом инстансе uPlot (valToPos/bbox/ctx/scales) —
 * jsdom не поднимает ни canvas, ни uPlot. Окно X без графика берётся из
 * кадра; «до кадра» Δt — «—», никогда NaN. */

import type uPlot from "uplot";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LiveChannelSeries, LiveFramePayload } from "../../api/types-live";
import { buildScopeCursorSection, findScopeCursorView } from "./scopeCursorSection";

function sine(
  points: number,
  cycles: number,
  windowS: number,
  amplitudeV: number,
): LiveChannelSeries {
  const time_s: number[] = [];
  const voltage_v: number[] = [];
  // Замкнутый интервал [0, windowS]: окно кадра ровно windowS,
  // фаза достигает 2π·cycles на последнем отсчёте.
  for (let i = 0; i < points; i += 1) {
    time_s.push((i / (points - 1)) * windowS);
    voltage_v.push(amplitudeV * Math.sin((2 * Math.PI * cycles * i) / (points - 1)));
  }
  return { time_s, voltage_v, point_count: points };
}

function frame(): LiveFramePayload {
  return {
    frame_index: 1,
    triggered: true,
    emitted_at_s: 0,
    dropped_samples: 0,
    skipped_frames: 0,
    sample_rate_hz: 8_000_000,
    frame_samples: 4096,
    decimated: true,
    calibration_used: false,
    ch1: sine(200, 2.5, 0.002, 1.7),
    ch2: sine(200, 2.5, 0.002, 0.85),
  };
}

function setSlider(section: HTMLElement, id: string, value: string): void {
  const slider = section.querySelector<HTMLInputElement>(`#${id}`);
  if (slider === null) throw new Error(`нет ползунка #${id}`);
  slider.value = value;
  slider.dispatchEvent(new Event("input", { bubbles: true }));
}

/** Фальшивый 2D-контекст: запоминает стили stroke и тексты fillText. */
function fakeContext() {
  const strokes: string[] = [];
  const texts: string[] = [];
  let strokeStyle = "";
  let fillStyle = "";
  const ctx = {
    save: () => undefined,
    restore: () => undefined,
    beginPath: () => undefined,
    moveTo: () => undefined,
    lineTo: () => undefined,
    stroke: () => {
      strokes.push(strokeStyle);
    },
    setLineDash: () => undefined,
    fillText: (text: string) => {
      texts.push(text);
    },
    fillRect: () => undefined,
    clearRect: () => undefined,
    setTransform: () => undefined,
    get font(): string {
      return "";
    },
    set font(_value: string) {},
    get lineWidth(): number {
      return 1;
    },
    set lineWidth(_value: number) {},
    get strokeStyle(): string {
      return strokeStyle;
    },
    set strokeStyle(value: string) {
      strokeStyle = value;
    },
    get fillStyle(): string {
      return fillStyle;
    },
    set fillStyle(value: string) {
      fillStyle = value;
    },
  };
  return { ctx: ctx as unknown as CanvasRenderingContext2D, strokes, texts };
}

/** Фальшивый uPlot: окно X 0..2 мс, домен Y ±5 В, bbox 40/10/360/240. */
function fakeUplot(ctx: CanvasRenderingContext2D, xMin: number, xMax: number): uPlot {
  const root = document.createElement("div");
  // Значения токенов инлайн: jsdom не каскадирует custom properties.
  root.style.setProperty("--lnt-delta", "#b7a6ff");
  root.style.setProperty("--lnt-ok", "#3dbd8a");
  root.style.setProperty("--lnt-text-sec", "#aeb6bf");
  const self = {
    ctx,
    root,
    bbox: { left: 40, top: 10, width: 360, height: 240 },
    scales: { x: { key: "x", min: xMin, max: xMax } },
    valToPos: (value: number, scale: string) => {
      if (scale === "x") return 40 + ((value - xMin) / (xMax - xMin)) * 360;
      return 10 + 240 * (0.5 - value / 10);
    },
    redraw: () => undefined,
  };
  return self as unknown as uPlot;
}

/** uPlot-хуки могут быть массивом; тесту нужен первый. */
function hookOf<T>(hook: T | T[] | undefined): T | undefined {
  return Array.isArray(hook) ? hook[0] : hook;
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("scopeCursorSection: показания курсоров", () => {
  it("панель с ползунками монтируется; до кадра Δt «—», ΔV уже есть", () => {
    const section = buildScopeCursorSection();
    document.body.append(section.root);

    expect(section.root.classList.contains("lnt-scope-cursors")).toBe(true);
    expect(section.root.querySelector("#lnt-scope-cursor-t1")).toBeInstanceOf(HTMLInputElement);
    expect(section.root.querySelector("#lnt-scope-cursor-v2")).toBeInstanceOf(HTMLInputElement);
    expect(section.root.querySelector(".lnt-scope-cursor-dt")?.textContent).toBe("—");
    expect(section.root.querySelector(".lnt-scope-cursor-dv")?.textContent).toBe("2.000 В");
    expect(section.root.querySelector(".lnt-scope-cursor-v1")?.textContent).toBe("-1.000 В");
  });

  it("кадр задаёт окно: Δt по окну 2 мс, позиции T1/T2 в секундах окна", () => {
    const section = buildScopeCursorSection();
    section.applyFrame(frame());

    // Дефолтные позиции курсоров T1=0.25, T2=0.75 окна.
    expect(section.root.querySelector(".lnt-scope-cursor-t1")?.textContent).toBe("500.000 мкс");
    expect(section.root.querySelector(".lnt-scope-cursor-t2")?.textContent).toBe("1.500 мс");
    expect(section.root.querySelector(".lnt-scope-cursor-dt")?.textContent).toBe("1.000 мс");
  });

  it("ползунки двигают курсоры: Δt и ΔV пересчитываются, порядок неважен", () => {
    const section = buildScopeCursorSection();
    section.applyFrame(frame());

    // T1 → 100‰ (0.1 окна), T2 остаётся 750‰: Δt = 0.65 · 2 мс = 1.3 мс.
    setSlider(section.root, "lnt-scope-cursor-t1", "100");
    expect(section.root.querySelector(".lnt-scope-cursor-dt")?.textContent).toBe("1.300 мс");

    // V1 → −2.0 В (−200), V2 → 1.0 В: ΔV = 3.000 В.
    setSlider(section.root, "lnt-scope-cursor-v1", "-200");
    expect(section.root.querySelector(".lnt-scope-cursor-dv")?.textContent).toBe("3.000 В");
    expect(section.root.querySelector(".lnt-scope-cursor-v1")?.textContent).toBe("-2.000 В");
  });

  it("доля окна за пределами [0..1] зажимается (T1=0 при −50‰)", () => {
    const section = buildScopeCursorSection();
    section.applyFrame(frame());

    setSlider(section.root, "lnt-scope-cursor-t1", "-50");
    // T1 зажат в 0 → Δt = 0.75 окна = 1.5 мс; позиция T1 — ноль времени.
    expect(section.root.querySelector(".lnt-scope-cursor-dt")?.textContent).toBe("1.500 мс");
    expect(section.root.querySelector(".lnt-scope-cursor-t1")?.textContent).toBe("0.0 нс");
  });
});

describe("scopeCursorSection: плагин линий на uPlot", () => {
  it("draw рисует четыре линии курсоров (стили — токены v2-tokens)", () => {
    const section = buildScopeCursorSection();
    const fake = fakeContext();
    const self = fakeUplot(fake.ctx, 0, 0.002);

    const draw = section.plugin.hooks?.draw;
    expect(typeof draw).toBe("function");
    if (typeof draw === "function") draw(self);

    // Только курсоры: 2× фиолет (T), 2× зелёный (V); подписи у линий.
    expect(fake.strokes.filter((style) => style === "#b7a6ff")).toHaveLength(2);
    expect(fake.strokes.filter((style) => style === "#3dbd8a")).toHaveLength(2);
    expect(fake.texts).toContain("T1");
    expect(fake.texts).toContain("T2");
    expect(fake.texts).toContain("V1");
    expect(fake.texts).toContain("V2");
  });

  it("draw сообщает окно X графика в readout (зум честно в Δt)", () => {
    const section = buildScopeCursorSection();
    const fake = fakeContext();
    const self = fakeUplot(fake.ctx, 0.0005, 0.0025);

    const draw = section.plugin.hooks?.draw;
    if (typeof draw === "function") draw(self);

    // Окно графика 0.5..2.5 мс: T1 = 1.0 мс, Δt = 1 мс.
    expect(section.root.querySelector(".lnt-scope-cursor-t1")?.textContent).toBe("1.000 мс");
    expect(section.root.querySelector(".lnt-scope-cursor-dt")?.textContent).toBe("1.000 мс");
  });

  it("после init ползунок перерисовывает график (uPlot.redraw)", () => {
    const section = buildScopeCursorSection();
    const fake = fakeContext();
    const self = fakeUplot(fake.ctx, 0, 0.002);
    const redraw = vi.fn();
    (self as unknown as { redraw: () => void }).redraw = redraw;

    const initHook = hookOf(section.plugin.hooks?.init);
    expect(typeof initHook).toBe("function");
    initHook?.(self, {} as uPlot.Options, [] as unknown as uPlot.AlignedData);

    setSlider(section.root, "lnt-scope-cursor-t1", "100");
    expect(redraw).toHaveBeenCalled();
  });

  it("при живом графике applyFrame не затирает окно осей (истина — график)", () => {
    const section = buildScopeCursorSection();
    const fake = fakeContext();
    const self = fakeUplot(fake.ctx, 0, 0.002);
    const drawHook = hookOf(section.plugin.hooks?.draw);
    const initHook = hookOf(section.plugin.hooks?.init);
    initHook?.(self, {} as uPlot.Options, [] as unknown as uPlot.AlignedData);
    drawHook?.(self);

    // Кадр с другим окном приходит, но окно осей графика остаётся истиной.
    section.applyFrame(frame());
    expect(section.root.querySelector(".lnt-scope-cursor-dt")?.textContent).toBe("1.000 мс");
  });
});

describe("scopeCursorSection: тумблер Выкл|Вкл и поиск хэндла (задача 15)", () => {
  it("тумблер Выкл|Вкл — local-контроль: линии гаснут, включение возвращает", () => {
    const section = buildScopeCursorSection();
    document.body.append(section.root);

    const seg = section.root.querySelector<HTMLElement>('[data-local="cursors"]');
    expect(seg).toBeInstanceOf(HTMLElement);
    const off = seg?.querySelector<HTMLButtonElement>('[data-value="off"]');
    if (off === null || off === undefined) throw new Error("нет кнопки Выкл");

    expect(section.cursorsOn()).toBe(true);
    off.click();
    expect(section.cursorsOn()).toBe(false);

    // Выкл: draw больше не рисует линии курсоров.
    const fake = fakeContext();
    const self = fakeUplot(fake.ctx, 0, 0.002);
    const draw = section.plugin.hooks?.draw;
    if (typeof draw === "function") draw(self);
    expect(fake.strokes).toHaveLength(0);

    const on = seg?.querySelector<HTMLButtonElement>('[data-value="on"]');
    if (on === null || on === undefined) throw new Error("нет кнопки Вкл");
    on.click();
    expect(section.cursorsOn()).toBe(true);
    if (typeof draw === "function") draw(self);
    expect(fake.strokes).toHaveLength(4);
  });

  it("findScopeCursorView находит хэндл по корню секции; chart — после init", () => {
    const section = buildScopeCursorSection();
    document.body.append(section.root);

    expect(findScopeCursorView(section.root)).toBe(section);
    expect(section.chart()).toBeNull();

    const fake = fakeContext();
    const self = fakeUplot(fake.ctx, 0, 0.002);
    const initHook = hookOf(section.plugin.hooks?.init);
    initHook?.(self, {} as uPlot.Options, [] as unknown as uPlot.AlignedData);
    expect(section.chart()).toBe(self);
  });
});

describe("scopeCursorSection: инлайн-ридаут Δt·ΔV (задача r5-9 W3, r4-грамматика)", () => {
  it("инлайн-строка «Δt … · ΔV …» живёт в секции и обновляется вместе с сеткой", () => {
    const section = buildScopeCursorSection();
    document.body.append(section.root);

    // До окна кадра Δt — «—», ΔV — номинальная шкала (та же истина, что в сетке).
    expect(section.inlineReadout.textContent).toBe("Δt — · ΔV 2.000 В");
    expect(section.root.contains(section.inlineReadout)).toBe(true);

    // Окно из кадра (графика нет) честно попадает в Δt.
    section.applyFrame(frame());
    expect(section.inlineReadout.textContent).toBe("Δt 1.000 мс · ΔV 2.000 В");

    // Слайдер двигает пару: инлайн и сетка говорят одно и то же.
    setSlider(section.root, "lnt-scope-cursor-t1", "100");
    expect(section.inlineReadout.textContent).toBe("Δt 1.300 мс · ΔV 2.000 В");
    expect(section.root.querySelector(".lnt-scope-cursor-dt")?.textContent).toBe("1.300 мс");

    setSlider(section.root, "lnt-scope-cursor-v2", "200");
    expect(section.inlineReadout.textContent).toBe("Δt 1.300 мс · ΔV 3.000 В");
  });
});
