/** Задача 14 RED: оболочка полосы liveStrip — zone-манифест per-tab порождает
 * DOM (2 линии виджетов, pzone/pzone-cont, гравировки, notes, статус-зона),
 * автокарта [data-zone]/[data-ctl] не может разойтись с DOM, токены
 * --lnt-run/--lnt-run-bg объявлены внутри .app-v6-скоупа (никогда :root). */

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { mountLiveStrip } from "./liveStrip";
import type { LiveStripZoneDesc } from "./liveStrip";

const MANIFEST: readonly LiveStripZoneDesc[] = [
  {
    zone: "vert",
    label: "ВЕРТ",
    aria: "Вертикаль",
    rows: [{ line: 1, groups: [{ ctl: "vdiv", label: "В/дел" }, { ctl: "probe" }] }],
  },
  {
    zone: "trig",
    label: "ТРИГГ",
    aria: "Триггер",
    rows: [
      { line: 1, groups: [{ ctl: "trigmode" }] },
      { line: 2, groups: [{ ctl: "level" }, { slot: "trigState" }], note: "заметка зоны" },
    ],
  },
  {
    zone: "measure",
    label: "ИЗМЕР",
    aria: "Измерения",
    rows: [{ line: 2, groups: [{ local: "history" }] }],
  },
];

describe("mountLiveStrip: полоса из дескрипторов зон", () => {
  it("рендерит зоны манифеста: части [data-zone], 2 линии, статус-зона", () => {
    const strip = mountLiveStrip(MANIFEST);
    document.body.append(strip.root);

    const zones = [...strip.root.querySelectorAll("[data-zone]")].map(
      (node) => (node as HTMLElement).dataset.zone,
    );
    // ТРИГГ занимает обе линии — частей больше, чем зон.
    expect(zones).toEqual(["vert", "trig", "trig", "measure"]);
    const line1 = strip.root.querySelector('[data-band-line="1"]');
    const line2 = strip.root.querySelector('[data-band-line="2"]');
    expect(line1).toBeInstanceOf(HTMLElement);
    expect(line2).toBeInstanceOf(HTMLElement);
    expect(line1?.querySelector('[data-zone="vert"]')).toBeInstanceOf(HTMLElement);
    // Продолжение зоны во 2-ю линию — класс pzone-cont, подпись только на первой части.
    const cont = line2?.querySelector('[data-zone="trig"]');
    expect(cont?.classList.contains("lnt-live-pzone-cont")).toBe(true);
    expect(cont?.querySelector(".lnt-live-pzone-label")).toBeNull();
    expect(line1?.querySelector('[data-zone="trig"] .lnt-live-pzone-label')?.textContent).toBe(
      "ТРИГГ",
    );
    // Статус-зона полосы — отдельная строка [data-band-status].
    expect(strip.root.querySelector("[data-band-status]")).toBeInstanceOf(HTMLElement);
    expect(strip.root.querySelector(".lnt-live-zone-note")?.textContent).toBe("заметка зоны");
    strip.destroy();
  });

  it("группы несут контекстные атрибуты: data-ctl / data-local / data-slot; groupHost находит обёртку", () => {
    const strip = mountLiveStrip(MANIFEST);
    document.body.append(strip.root);

    expect(strip.groupHost("vdiv").getAttribute("data-ctl")).toBe("vdiv");
    expect(strip.groupHost("history").getAttribute("data-local")).toBe("history");
    expect(strip.groupHost("trigState").getAttribute("data-slot")).toBe("trigState");
    // Микроподписи групп линии 1 и гравировки линии 2.
    expect(strip.groupHost("vdiv").querySelector(".lnt-live-ctl-label")?.textContent).toBe("В/дел");
    strip.destroy();
  });

  it("автокарта зон читает живой DOM: зоны и контролы совпадают с манифестом", () => {
    const strip = mountLiveStrip(MANIFEST);
    document.body.append(strip.root);
    // Виджеты ре-парентятся в обёртки после монтирования — карта обязана
    // видеть их атрибуты (здесь: собственные data-ctl обёрток).
    const map = strip.zoneMap();
    expect(map.map((entry) => entry.zone)).toEqual(["vert", "trig", "measure"]);
    const trig = map.find((entry) => entry.zone === "trig");
    expect(trig?.parts).toHaveLength(2);
    expect(trig?.controls).toContain("trigmode");
    expect(trig?.controls).toContain("level");
    strip.destroy();
  });
});

describe("liveStrip.css: токены полосы (AC5)", () => {
  // jsdom-окружение даёт import.meta.url не-file-схемы: путь от cwd вит-раннера.
  const css = readFileSync(`${process.cwd()}/src/components/liveStrip/liveStrip.css`, "utf8");

  it("токены --lnt-run/--lnt-run-bg объявлены внутри .app-v6-скоупа", () => {
    expect(css).toMatch(/\.app-v6[^{}]*\{[^}]*--lnt-run\s*:/);
    expect(css).toMatch(/\.app-v6[^{}]*\{[^}]*--lnt-run-bg\s*:/);
  });

  it("токены не на :root", () => {
    // Комментарии из проверки исключаем: :root упомянут в доке правила.
    const rules = css.replace(/\/\*[\s\S]*?\*\//g, "");
    expect(rules).not.toMatch(/:root[^{}]*\{[^}]*--lnt-run/);
  });
});
