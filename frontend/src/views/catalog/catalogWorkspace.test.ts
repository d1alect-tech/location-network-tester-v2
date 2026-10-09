/** Текст пустого каталога: фильтровый и «по-настоящему пустой» различаются.
 * Мок-бэкенд e2e не умеет по-настоящему пустой каталог (/api/catalog/sessions
 * при пустом сиде отдаёт research-сессии), поэтому выбор формулировки
 * проверяется напрямую на чистой функции (ограничение харнеса — в комментарии). */

import { describe, expect, it } from "vitest";
import { EMPTY_MESSAGE, NO_FILTERS_EMPTY_MESSAGE, emptyCatalogMessage } from "./catalogWorkspace";

describe("emptyCatalogMessage", () => {
  it("с активным фильтром — фильтровая формулировка с подсказкой про сброс", () => {
    expect(emptyCatalogMessage({ label: "нет-такой-метки" })).toBe(EMPTY_MESSAGE);
    expect(emptyCatalogMessage({ health: "ok", session: "cap-1" })).toBe(EMPTY_MESSAGE);
  });

  it("без фильтров — своя формулировка; выбор сессии фильтром не считается", () => {
    expect(emptyCatalogMessage({})).toBe(NO_FILTERS_EMPTY_MESSAGE);
    expect(emptyCatalogMessage({ session: "cap-1" })).toBe(NO_FILTERS_EMPTY_MESSAGE);
    expect(NO_FILTERS_EMPTY_MESSAGE).not.toContain("Сбросить");
  });
});
