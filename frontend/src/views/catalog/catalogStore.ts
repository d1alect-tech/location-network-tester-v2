/** Хранилище страниц каталога: курсорная догрузка поверх GET /api/catalog/sessions
 * с защитой от гонок — устаревший ответ не может перезаписать текущую выдачу
 * (поколение + AbortController, паттерн src/state/resource.ts). */

import type { CatalogPage, CatalogQuery, CatalogSession } from "../../api/types";

export type FetchPage = (query: CatalogQuery, signal: AbortSignal) => Promise<CatalogPage>;

export interface CatalogState {
  /** Накопленные строки текущего запроса (первая страница + догрузки). */
  items: CatalogSession[];
  nextCursor: string | null;
  query: CatalogQuery;
  status: "loading" | "ready" | "error";
  loadingMore: boolean;
  error: string | null;
}

export type CatalogListener = (state: CatalogState) => void;

export const DEFAULT_PAGE_SIZE = 200;

export class CatalogStore {
  private state: CatalogState = {
    items: [],
    nextCursor: null,
    query: {},
    status: "loading",
    loadingMore: false,
    error: null,
  };
  private readonly listeners = new Set<CatalogListener>();
  private generation = 0;
  private controller: AbortController | null = null;

  constructor(private readonly fetchPage: FetchPage) {}

  get(): CatalogState {
    return this.state;
  }

  subscribe(listener: CatalogListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private set(patch: Partial<CatalogState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener(this.state);
  }

  /** Новый запрос фильтров: сбрасывает накопление и обрывает предыдущий полёт. */
  applyQuery(query: CatalogQuery): Promise<void> {
    const gen = ++this.generation;
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    this.set({
      query,
      status: "loading",
      items: [],
      nextCursor: null,
      error: null,
      loadingMore: false,
    });
    return this.runPage(gen, controller, query, null, false);
  }

  /** Догружает следующую страницу текущего запроса (кнопка «Показать ещё»). */
  loadMore(): Promise<void> {
    if (this.state.nextCursor === null || this.state.loadingMore) return Promise.resolve();
    const gen = this.generation;
    const cursor = this.state.nextCursor;
    const controller = new AbortController();
    this.controller = controller;
    this.set({ loadingMore: true });
    return this.runPage(gen, controller, this.state.query, cursor, true);
  }

  private async runPage(
    gen: number,
    controller: AbortController,
    query: CatalogQuery,
    cursor: string | null,
    append: boolean,
  ): Promise<void> {
    try {
      const page = await this.fetchPage({ ...query, cursor }, controller.signal);
      if (gen !== this.generation) return; // устаревший ответ — игнорируем целиком
      this.set({
        items: append ? [...this.state.items, ...page.items] : page.items,
        nextCursor: page.next_cursor,
        status: "ready",
        loadingMore: false,
        error: null,
      });
    } catch (error) {
      if (gen !== this.generation || isAbort(error)) return;
      this.set({
        status: append ? "ready" : "error",
        loadingMore: false,
        error: "Не удалось загрузить каталог. Проверьте связь с сервером и повторите.",
      });
    }
  }

  /** Повторяет последний запрос фильтров (кнопка «Повторить»). */
  retry(): Promise<void> {
    return this.applyQuery(this.state.query);
  }
}

function isAbort(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { name?: unknown }).name === "AbortError"
  );
}
