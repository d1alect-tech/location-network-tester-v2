import { describe, expect, it, vi } from "vitest";
import type { CatalogSession, LegacySessionItem } from "../../api/types";
import { createCatalogColumn } from "./catalogColumn";
import { createPairState } from "./pairState";

/** Строка 13 (план ui-refactor-3, гейт F3-remedy): формат строки каталога
 * в рейле инспекции — вариант V1 «Мета под меткой» с инвариантом владельца:
 * НИКАКИЕ данные не обрезаются и элементы не наезжают. RED-контракты:
 * одна colspan-ячейка на строку, полный текст метки (без cell-ellipsis),
 * локализованный тип в мета-строке, время/дата, health/analyzed-пилюли
 * в мета-строке, год в заголовке дня. Машинночитаемое: атрибуты и тексты,
 * совпадающие со shipped-словарями. */

const LONG_LABEL =
  "Замер подъезда №2 — повторный прогон после замены кабеля на стенде-А (длинная метка)";
const LONGER_LABEL = `${LONG_LABEL}, вторая часть для полного переноса`;

function session(
  id: string,
  createdUtc: string,
  label: string,
  sessionType: string | null,
  health: CatalogSession["health"] = "ok",
): CatalogSession {
  return {
    id,
    health,
    created_utc: createdUtc,
    source: "hardware",
    session_type: sessionType,
    profile: "lab",
    label,
  };
}

const sMeas = session("meas-1", "2026-10-05T15:10:00Z", LONGER_LABEL, "measurement");
const sNoise = session(
  "noise-1",
  "2026-10-05T15:09:00Z",
  "Самошум, демпфирование пика №2",
  "self_noise",
);
const sNoType = session("nt-1", "2026-08-06T09:41:00Z", "12:39, 06.08 бпф", null);
const sDup = session(
  "dup-1",
  "2026-08-06T09:38:00Z",
  "syn-quiet-seed-042",
  "simulate",
  "duplicate_id",
);

function legacy(name: string, analyzed: boolean): LegacySessionItem {
  return { name, status: "ready", error: null, analyzed, summary: null };
}

function fakeClient(items: CatalogSession[], legacyItems: LegacySessionItem[] = []) {
  return {
    catalogSessions: async () => ({ items }),
    legacySessions: async () => ({ sessions: legacyItems }),
  };
}

async function mount(items: CatalogSession[], legacyItems: LegacySessionItem[] = []) {
  const column = createCatalogColumn({
    client: fakeClient(items, legacyItems),
    pair: createPairState(),
    onPick: vi.fn(),
  });
  await column.reload();
  document.body.replaceChildren(column.root);
  return column;
}

describe("строка 13: формат строки рейла — V1 «Мета под меткой»", () => {
  it("строка — одна colspan-ячейка с контуром .cat-row (линия метки + мета)", async () => {
    const column = await mount([sMeas, sNoise]);
    const row = column.root.querySelector('[data-session="meas-1"]');
    expect(row).toBeInstanceOf(HTMLTableRowElement);

    const cells = row?.querySelectorAll("td");
    expect(cells).toHaveLength(1);
    expect(cells?.[0]?.colSpan).toBe(4);
    expect(cells?.[0]?.querySelector(".cat-row .cat-line1")).not.toBeNull();
    expect(cells?.[0]?.querySelector(".cat-row .cat-meta")).not.toBeNull();
  });

  it("метка полностью видима: эллипсис-механика убрана, полный текст в DOM", async () => {
    const column = await mount([sMeas]);
    const row = column.root.querySelector('[data-session="meas-1"]');

    const label = row?.querySelector<HTMLElement>("[data-cat-label]");
    expect(label?.textContent).toBe(LONGER_LABEL);
    expect(label?.getAttribute("title")).toBe(LONGER_LABEL);
    expect(row?.querySelector(".cell-ellipsis")).toBeNull();
    expect(label?.className).not.toMatch(/cell-ellipsis/);
  });

  it("тип локализован в мета-строке: measurement/self_noise/null", async () => {
    const column = await mount([sMeas, sNoise, sNoType]);

    expect(column.root.querySelector('[data-session="meas-1"] .cat-meta-type')?.textContent).toBe(
      "Измерение",
    );
    expect(column.root.querySelector('[data-session="noise-1"] .cat-meta-type')?.textContent).toBe(
      "Самошум",
    );
    expect(column.root.querySelector('[data-session="nt-1"] .cat-meta-type')?.textContent).toBe(
      "—",
    );
  });

  it("время в мета-строке (группировка по дате), полная дата — при сортировке по метке", async () => {
    const column = await mount([sMeas]);
    expect(column.root.querySelector('[data-session="meas-1"] .cat-meta-time')?.textContent).toBe(
      "15:10",
    );

    column.root.querySelector<HTMLElement>('[data-cat-sort="label"]')?.click();
    const flat = column.root.querySelector('[data-session="meas-1"] .cat-meta-time');
    expect(flat?.textContent).toContain("05.10.2026");
    expect(flat?.textContent).toContain("15:10");
  });

  it("health- и analyzed-пилюли живут в мета-строке, тексты совпадают со словарём", async () => {
    const column = await mount([sMeas, sDup], [legacy("meas-1", true), legacy("dup-1", false)]);

    const measMeta = column.root.querySelector('[data-session="meas-1"] .cat-meta');
    expect(measMeta?.querySelector('[data-cat-health="ok"]')?.textContent).toContain("Исправна");
    expect(measMeta?.querySelector('[data-cat-analyzed="yes"]')?.textContent).toBe(
      "Проанализирована",
    );

    const dupMeta = column.root.querySelector('[data-session="dup-1"] .cat-meta');
    expect(dupMeta?.querySelector('[data-cat-health="duplicate_id"]')?.textContent).toContain(
      "Дубль идентификатора",
    );
    expect(dupMeta?.querySelector('[data-cat-analyzed="no"]')?.textContent).toBe(
      "Не проанализирована",
    );
  });

  it("заголовок дня группы содержит год", async () => {
    const column = await mount([sMeas, sNoType]);
    const groups = [...column.root.querySelectorAll("[data-cat-group]")];
    expect(groups).toHaveLength(2);
    expect(groups[0]?.textContent).toContain("5 октября 2026");
    expect(groups[1]?.textContent).toContain("6 августа 2026");
  });

  it("кнопки А/Б и чип роли сохранены на строке", async () => {
    const pair = createPairState();
    const column = createCatalogColumn({
      client: fakeClient([sMeas, sNoise]),
      pair,
      onPick: vi.fn(),
    });
    await column.reload();
    document.body.replaceChildren(column.root);

    const row = column.root.querySelector('[data-session="meas-1"]');
    expect(row?.querySelectorAll('[data-assign="a"]')).toHaveLength(1);
    expect(row?.querySelectorAll('[data-assign="b"]')).toHaveLength(1);

    pair.pick("meas-1");
    expect(column.root.querySelector('[data-session="meas-1"] [data-cat-role="a"]')).not.toBeNull();
  });
});
