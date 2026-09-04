/** Навигация строк каталога (T11-доб): roving tabindex, прокрутка
 * к активной строке и клавиатура (стрелки/Home/End/Enter).
 * Состояние выдачи остаётся в catalogListView, здесь только механика. */

export interface RowNav {
  body: HTMLElement;
  table: HTMLElement;
  count: () => number;
  getActive: () => number;
  setActive: (index: number) => void;
  onActivate: (index: number) => void;
  onNearEnd: () => void;
  nearEndArmed: () => boolean;
}

export function syncRowTabindex(body: HTMLElement, activeIndex: number): void {
  for (const node of body.querySelectorAll<HTMLElement>(".lnt-cat-row")) {
    const index = Number(node.getAttribute("data-pos"));
    node.tabIndex = index === activeIndex ? 0 : -1;
  }
}

export function ensureRowVisible(table: HTMLElement, body: HTMLElement, index: number): void {
  const wrap = table.closest(".tbl-wrap");
  const row = body.querySelector(`[data-pos="${index}"]`);
  if (!(wrap instanceof HTMLElement) || !(row instanceof HTMLElement)) return;
  const top = row.offsetTop;
  if (top < wrap.scrollTop) wrap.scrollTop = top;
  else if (top + row.offsetHeight > wrap.scrollTop + wrap.clientHeight) {
    wrap.scrollTop = top + row.offsetHeight - wrap.clientHeight;
  }
}

export function handleRowKeys(event: KeyboardEvent, index: number, nav: RowNav): void {
  const next =
    event.key === "ArrowDown"
      ? Math.min(nav.count() - 1, index + 1)
      : event.key === "ArrowUp"
        ? Math.max(0, index - 1)
        : event.key === "Home"
          ? 0
          : event.key === "End"
            ? nav.count() - 1
            : null;
  if (next !== null) {
    event.preventDefault();
    nav.setActive(next);
    ensureRowVisible(nav.table, nav.body, next);
    syncRowTabindex(nav.body, next);
    nav.body.querySelector<HTMLElement>(`[data-pos="${next}"]`)?.focus();
    if (nav.count() - next <= 8 && nav.nearEndArmed()) nav.onNearEnd();
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    nav.onActivate(index);
  }
}
