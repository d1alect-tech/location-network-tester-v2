/** Строки плотной таблицы: worst-case данные не ломают разметку —
 * длинный идентификатор режется title-ом, отсутствующая дата даёт «—»,
 * пилюля всегда текстовая, выбор помечен data-selected + aria-current. */

import { describe, expect, it } from "vitest";
import type { CatalogSession } from "../../api/types";
import { worstCaseSessions } from "../../testkit/catalogFixture";
import {
  type RowRenderContext,
  formatDay,
  formatTime,
  orderSessions,
  renderEmpty,
  renderGroup,
  renderRow,
} from "./catalogListRows";
import { HEALTH_LABELS } from "./catalogModel";

function ctx(overrides: Partial<RowRenderContext> = {}): RowRenderContext {
  return {
    activeIndex: 0,
    selectedId: null,
    grouped: true,
    roleOf: () => null,
    onActivate: () => undefined,
    onRowKeys: () => undefined,
    ...overrides,
  };
}

const [longId, invalid, missing, plain] = worstCaseSessions();

describe("catalogListRows: строка", () => {
  it("длинный идентификатор остаётся в title и data-атрибуте целиком", () => {
    if (!longId) throw new Error("fixture pуста");
    const row = renderRow(longId, 0, ctx());
    expect(row.getAttribute("data-session-id")).toBe(longId.id);
    expect(row.getAttribute("title")).toBe(longId.id);
    expect(row.querySelector("[data-cat-label]")?.textContent).toBe(longId.label);
    expect(row.textContent).not.toContain("NaN");
  });

  it("сессия без даты: время «—», группа unknown, без NaN", () => {
    if (!missing) throw new Error("fixture пуста");
    const row = renderRow(missing, 0, ctx());
    expect(row.getAttribute("data-cat-date")).toBe("unknown");
    expect(row.querySelector(".num")?.textContent).toBe("—");
    expect(row.querySelector(".lnt-status-pill")?.textContent).toContain(
      HEALTH_LABELS[missing.health].label,
    );
  });

  it("пилюля здоровья текстовая для каждого кода", () => {
    for (const session of worstCaseSessions()) {
      const row = renderRow(session, 0, ctx());
      const pill = row.querySelector(".lnt-status-pill");
      expect(pill?.textContent).toContain(HEALTH_LABELS[session.health].label);
    }
  });

  it("выбранная строка помечена data-selected и aria-current", () => {
    if (!plain) throw new Error("fixture пуста");
    const row = renderRow(plain, 0, ctx({ selectedId: plain.id }));
    expect(row.hasAttribute("data-selected")).toBe(true);
    expect(row.getAttribute("aria-current")).toBe("true");
    const other = renderRow(plain, 1, ctx());
    expect(other.hasAttribute("data-selected")).toBe(false);
  });

  it("без групп колонка даты показывает день, с группами — время", () => {
    if (!plain) throw new Error("fixture пуста");
    const grouped = renderRow(plain, 0, ctx());
    expect(grouped.querySelector(".num")?.textContent).toBe("17:43");
    const flat = renderRow(plain, 0, ctx({ grouped: false }));
    expect(flat.querySelector(".num")?.textContent).toBe("2026-08-05");
  });
});

describe("catalogListRows: группы дней и пусто", () => {
  it("заголовок дня несёт имя дня и счётчик строк", () => {
    const group = renderGroup("2026-08-05", 4);
    expect(group.getAttribute("data-cat-group")).toBe("2026-08-05");
    expect(group.textContent).toContain("5 августа");
    expect(group.querySelector("[data-cat-count]")?.textContent).toBe("4");
  });

  it("unknown-день подписан «Без даты», пустая выдача — одной ячейкой", () => {
    expect(formatDay("unknown")).toBe("Без даты");
    expect(formatTime(null)).toBe("—");
    const empty = renderEmpty("По запросу ничего не найдено");
    expect(empty.querySelector("[data-cat-empty]")?.textContent).toBe(
      "По запросу ничего не найдено",
    );
  });

  it("повреждённый контекст виден в выдаче со своей пилюлей", () => {
    if (!invalid) throw new Error("fixture пуста");
    const row = renderRow(invalid, 0, ctx());
    expect(row.querySelector(".lnt-status-pill")?.textContent).toContain("Контекст повреждён");
  });
});

describe("catalogListRows: порядок детерминирован", () => {
  it("сортировка по дате убирает сессию без даты в конец выдачи", () => {
    const sessions: CatalogSession[] = worstCaseSessions();
    const ordered = orderSessions(sessions, "date", "descending");
    expect(ordered[ordered.length - 1]?.created_utc).toBeNull();
    expect(ordered[0]?.created_utc).toBe("2026-08-05T17:43:11Z");
  });
});
