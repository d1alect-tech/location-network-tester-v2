/** Виртуализованный список каталога: рендерится только видимое окно строк,
 * поэтому 10 000 строк прокручиваются без деградации. Клавиатура: стрелки,
 * Home/End, Enter открывает инспектор; бейджи health текстовые (не только цвет).
 * Повреждённые сессии остаются в списке и помечаются кодом причины. */

import type { CatalogSession } from "../../api/types";
import { clearElement, el } from "../../components/primitives/dom";
import { HEALTH_LABELS, sessionTypeLabel } from "./catalogModel";

const ROW_HEIGHT = 44;
const OVERSCAN = 4;

export interface CatalogListOptions {
  onActivate: (session: CatalogSession) => void;
  onLoadMore: () => void;
  onRetry: () => void;
}

export interface CatalogListHandle {
  root: HTMLElement;
  setItems(items: CatalogSession[], options?: { resetScroll?: boolean }): void;
  setNotice(kind: "loading" | "empty" | "error", message: string): void;
  clearNotice(): void;
  setHasMore(hasMore: boolean): void;
  setSelected(id: string | null): void;
}

export function createCatalogListView(options: CatalogListOptions): CatalogListHandle {
  let items: CatalogSession[] = [];
  let selectedId: string | null = null;
  let activeIndex = 0;
  let firstRender = true;

  const viewport = el("div", {
    className: "lnt-cat-viewport",
    attrs: { role: "listbox", "aria-label": "Список сессий каталога" },
  });
  const sizer = el("div", { className: "lnt-cat-sizer", attrs: { role: "presentation" } });
  const windowEl = el("div", { className: "lnt-cat-window", attrs: { role: "presentation" } });
  viewport.append(sizer, windowEl);

  // Состояния (загрузка/пусто/ошибка) живут ВНЕ listbox: его содержимое —
  // только опции и presentation-обёртки (aria-required-children).
  const noticeHost = el("div", { className: "lnt-cat-notice-host" });

  const moreButton = el("button", {
    className: "lnt-btn lnt-cat-more",
    text: "Показать ещё",
    attrs: { type: "button" },
  });
  moreButton.hidden = true;
  moreButton.addEventListener("click", () => options.onLoadMore());

  const root = el("div", { className: "lnt-cat-list" }, [viewport, noticeHost, moreButton]);

  viewport.addEventListener("scroll", () => renderWindow(), { passive: true });

  function visibleCount(): number {
    return Math.ceil(viewport.clientHeight / ROW_HEIGHT) + OVERSCAN * 2 + 1;
  }

  function renderWindow(): void {
    if (items.length === 0) {
      sizer.style.height = "0px";
      clearElement(windowEl);
      return;
    }
    const start = Math.max(0, Math.floor(viewport.scrollTop / ROW_HEIGHT) - OVERSCAN);
    const end = Math.min(items.length, start + visibleCount());
    sizer.style.height = `${items.length * ROW_HEIGHT}px`;
    windowEl.style.transform = `translateY(${start * ROW_HEIGHT}px)`;
    clearElement(windowEl);
    for (let index = start; index < end; index += 1) {
      const session = items[index];
      if (!session) continue;
      windowEl.append(renderRow(session, index));
    }
  }

  function renderRow(session: CatalogSession, index: number): HTMLElement {
    const health = HEALTH_LABELS[session.health];
    const row = el("div", {
      className: `lnt-cat-row${session.id === selectedId ? " lnt-cat-row-selected" : ""}`,
      attrs: {
        role: "option",
        "aria-selected": session.id === selectedId ? "true" : "false",
        "aria-posinset": String(index + 1),
        "aria-setsize": String(items.length),
        "data-session-id": session.id,
      },
    });
    row.tabIndex = index === activeIndex ? 0 : -1;

    const idCell = el("span", {
      className: "lnt-cat-cell lnt-cat-id lnt-mono",
      text: session.id,
      attrs: { title: `Идентификатор сессии: ${session.id}` },
    });
    const labelCell = el("span", {
      className: "lnt-cat-cell",
      text: session.label ?? "",
      attrs: { title: session.label ? `Метка: ${session.label}` : "" },
    });
    const pill = el("span", { className: `lnt-status-pill lnt-tone-${health.tone}` });
    const glyph = el("span", { className: "lnt-status-glyph", attrs: { "aria-hidden": "true" } });
    glyph.textContent = health.tone === "ok" ? "●" : health.tone === "warn" ? "▲" : "✕";
    pill.append(glyph, document.createTextNode(health.label));
    const healthCell = el("span", { className: "lnt-cat-cell lnt-cat-health" }, [pill]);
    const metaCell = el("span", {
      className: "lnt-cat-cell lnt-cat-meta",
      text: formatMeta(session),
    });
    row.append(idCell, labelCell, healthCell, metaCell);

    row.addEventListener("click", () => activate(index));
    row.addEventListener("keydown", (event) => handleRowKeys(event, index));
    return row;
  }

  function formatMeta(session: CatalogSession): string {
    const type = session.session_type ? sessionTypeLabel(session.session_type) : "";
    const date = session.created_utc ? session.created_utc.slice(0, 10) : "";
    return [type, date].filter(Boolean).join(" · ");
  }

  function activate(index: number): void {
    const session = items[index];
    if (!session) return;
    activeIndex = index;
    syncTabindex();
    options.onActivate(session);
  }

  function syncTabindex(): void {
    for (const node of windowEl.querySelectorAll<HTMLElement>(".lnt-cat-row")) {
      const index = Number(node.getAttribute("aria-posinset")) - 1;
      node.tabIndex = index === activeIndex ? 0 : -1;
    }
  }

  function ensureVisible(index: number): void {
    const top = index * ROW_HEIGHT;
    if (top < viewport.scrollTop) viewport.scrollTop = top;
    else if (top + ROW_HEIGHT > viewport.scrollTop + viewport.clientHeight) {
      viewport.scrollTop = top + ROW_HEIGHT - viewport.clientHeight;
    }
  }

  function handleRowKeys(event: KeyboardEvent, index: number): void {
    const next =
      event.key === "ArrowDown"
        ? Math.min(items.length - 1, index + 1)
        : event.key === "ArrowUp"
          ? Math.max(0, index - 1)
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? items.length - 1
              : null;
    if (next !== null) {
      event.preventDefault();
      activeIndex = next;
      ensureVisible(next);
      renderWindow();
      focusedRow()?.focus();
      // Близко к концу списка — заранее запросим следующую страницу.
      if (items.length - next <= OVERSCAN * 2 && !moreButton.hidden) options.onLoadMore();
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      activate(index);
    }
  }

  function focusedRow(): HTMLElement | null {
    return windowEl.querySelector<HTMLElement>(`[aria-posinset="${activeIndex + 1}"]`);
  }

  return {
    root,
    setItems: (next, opts = {}) => {
      items = next;
      if (opts.resetScroll || firstRender) {
        viewport.scrollTop = 0;
        activeIndex = 0;
        firstRender = false;
      }
      if (activeIndex >= items.length) activeIndex = Math.max(0, items.length - 1);
      renderWindow();
    },
    setNotice: (kind, message) => {
      viewport.hidden = true;
      moreButton.hidden = true;
      while (noticeHost.firstChild) noticeHost.removeChild(noticeHost.firstChild);
      const note = el("p", {
        className:
          kind === "error" ? "lnt-table-note lnt-cat-error" : "lnt-table-note lnt-cat-empty",
        text: message,
        attrs: kind === "error" ? { role: "alert" } : {},
      });
      noticeHost.append(note);
      if (kind === "error") {
        const retry = el("button", {
          className: "lnt-btn",
          text: "Повторить",
          attrs: { type: "button" },
        });
        retry.addEventListener("click", () => options.onRetry());
        noticeHost.append(retry);
      }
    },
    clearNotice: () => {
      while (noticeHost.firstChild) noticeHost.removeChild(noticeHost.firstChild);
      viewport.hidden = false;
      renderWindow();
    },
    setHasMore: (hasMore) => {
      moreButton.hidden = !hasMore || items.length === 0;
    },
    setSelected: (id) => {
      selectedId = id;
      for (const node of windowEl.querySelectorAll<HTMLElement>(".lnt-cat-row")) {
        const isSelected = node.getAttribute("data-session-id") === id;
        node.classList.toggle("lnt-cat-row-selected", isSelected);
        node.setAttribute("aria-selected", isSelected ? "true" : "false");
      }
    },
  };
}
