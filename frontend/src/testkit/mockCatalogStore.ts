/** Каталог/контекст/профили единого мок-бэкенда (только e2e/spec).
 * Повторяет контракты routes_catalog.py / routes_context.py /
 * routes_profiles.py: keyset-пейджинг, casefold-подстрока метки,
 * оптимистичная блокировка revision (409), CRUD профилей. */

import type {
  CatalogPage,
  CatalogSession,
  ContextResponse,
  ContextUpdateRequest,
  ProfileRevision,
} from "../api/types";
import { contextFor, defaultProfiles, generateSessions } from "./catalogFixture";
import { type MockHttpReply, type MockHttpRequest, nonceRejected, notFound, ok } from "./mockHttp";

export interface CatalogFilters {
  health?: string;
  session_type?: string;
  profile?: string;
  label?: string;
  tag?: string;
  created_from?: string;
  created_to?: string;
}

export class CatalogStore {
  readonly sessions: CatalogSession[];
  private readonly storagePaths = new Map<string, string>();
  private readonly contexts = new Map<string, ContextResponse>();
  private profilesStore: ProfileRevision[];
  /** Сессии, для которых следующий PUT вернёт 409 (конкурентная правка). */
  readonly conflictQueue = new Set<string>();

  constructor(size: number, seed = 39) {
    this.sessions = generateSessions({ size, seed });
    for (const session of this.sessions) {
      this.storagePaths.set(session.id, `/sessions/${session.id}`);
      this.contexts.set(session.id, contextFor(session));
    }
    this.profilesStore = defaultProfiles();
  }

  /** Заменяет выдачу каталога (inspect-фикстуры спек). */
  seedCatalog(items: CatalogSession[]): void {
    this.sessions.length = 0;
    this.storagePaths.clear();
    for (const session of items) {
      this.sessions.push(session);
      this.storagePaths.set(session.id, `/sessions/${session.id}`);
      if (!this.contexts.has(session.id)) this.contexts.set(session.id, contextFor(session));
    }
  }

  /** Имитирует чужую правку: меняет заметки и инкрементирует revision. */
  concurrentEdit(sessionId: string): void {
    const context = this.contexts.get(sessionId);
    if (!context) return;
    this.contexts.set(sessionId, {
      ...context,
      revision: context.revision + 1,
      notes: `Чужая правка в ${sessionId}`,
      tags: [...context.tags, "конкурент"],
    });
    this.conflictQueue.add(sessionId);
  }

  catalog(searchParams: URLSearchParams): CatalogPage {
    const pageSize = Math.min(Number(searchParams.get("page_size") ?? "50") || 50, 200);
    const filters: CatalogFilters = {
      health: searchParams.get("health") ?? undefined,
      session_type: searchParams.get("session_type") ?? undefined,
      profile: searchParams.get("profile") ?? undefined,
      label: searchParams.get("label") ?? undefined,
      tag: searchParams.get("tag") ?? undefined,
      created_from: searchParams.get("created_from") ?? undefined,
      created_to: searchParams.get("created_to") ?? undefined,
    };
    const matched = this.sessions.filter((session) => {
      if (filters.health && session.health !== filters.health) return false;
      if (filters.session_type && session.session_type !== filters.session_type) return false;
      if (filters.profile && session.profile !== filters.profile) return false;
      if (
        filters.label &&
        !(session.label ?? "").toLowerCase().includes(filters.label.toLowerCase())
      ) {
        return false;
      }
      if (filters.tag) {
        const tags = this.contexts.get(session.id)?.tags ?? [];
        if (!tags.includes(filters.tag)) return false;
      }
      if (filters.created_from && (session.created_utc ?? "") < filters.created_from) return false;
      if (filters.created_to && (session.created_utc ?? "") > `${filters.created_to}T23:59:59Z`) {
        return false;
      }
      return true;
    });

    // Keyset: created_utc DESC, session_id ASC; cursor после последней строки страницы.
    let start = 0;
    const cursorRaw = searchParams.get("cursor");
    if (cursorRaw) {
      const [createdUtc, sessionId, storagePath] = decodeCursor(cursorRaw);
      start = matched.findIndex((session) => {
        const path = this.storagePaths.get(session.id) ?? "";
        const afterCursor =
          (session.created_utc ?? "") < (createdUtc || "") ||
          ((session.created_utc ?? "") === (createdUtc || "") &&
            (session.id > sessionId || (session.id === sessionId && path > storagePath)));
        return afterCursor;
      });
      if (start === -1) start = 0;
    }
    const items = matched.slice(start, start + pageSize);
    const last = items.at(-1);
    const hasMore = start + pageSize < matched.length;
    return {
      items,
      next_cursor:
        hasMore && last
          ? encodeCursor(last.created_utc, last.id, this.storagePaths.get(last.id) ?? "/")
          : null,
    };
  }

  getContext(sessionId: string): ContextResponse | null {
    return this.contexts.get(sessionId) ?? null;
  }

  updateContext(
    sessionId: string,
    request: ContextUpdateRequest,
  ): { status: number; body?: ContextResponse | Record<string, unknown> } {
    const current = this.contexts.get(sessionId);
    if (!current) return { status: 404, body: { detail: "сессия не найдена" } };
    if (request.expected_revision !== current.revision || this.conflictQueue.has(sessionId)) {
      this.conflictQueue.delete(sessionId);
      return {
        status: 409,
        body: {
          detail: {
            detail: `конфликт revision контекста: ожидалась ${request.expected_revision}, текущая ${current.revision}`,
            current_revision: current.revision,
          },
        },
      };
    }
    const updated: ContextResponse = {
      ...current,
      revision: current.revision + 1,
      fields: request.fields ?? current.fields,
      tags: request.tags ?? current.tags,
      notes: request.notes ?? current.notes,
    };
    this.contexts.set(sessionId, updated);
    return { status: 200, body: updated };
  }

  profiles(): ProfileRevision[] {
    return [...this.profilesStore];
  }

  upsertProfile(profileId: string, kind: string, data: unknown): { status: number; body: unknown } {
    const existingIndex = this.profilesStore.findIndex((item) => item.profile_id === profileId);
    if (existingIndex === -1) {
      const createdItem: ProfileRevision = {
        profile_id: profileId,
        kind: kind as ProfileRevision["kind"],
        revision: 1,
        captured_at: "2026-08-01T00:00:00Z",
        data: data as ProfileRevision["data"],
      };
      this.profilesStore.push(createdItem);
      return { status: 201, body: createdItem };
    }
    const previous = this.profilesStore[existingIndex];
    if (!previous) return { status: 404, body: { detail: "профиль не найден" } };
    const updated: ProfileRevision = {
      ...previous,
      revision: previous.revision + 1,
      captured_at: "2026-08-02T00:00:00Z",
      data: data as ProfileRevision["data"],
    };
    this.profilesStore[existingIndex] = updated;
    return { status: 200, body: updated };
  }

  deleteProfile(profileId: string): number {
    const existingIndex = this.profilesStore.findIndex((item) => item.profile_id === profileId);
    if (existingIndex === -1) return 404;
    this.profilesStore.splice(existingIndex, 1);
    return 204;
  }
}

export function encodeCursor(
  createdUtc: string | null,
  sessionId: string,
  storagePath: string,
): string {
  const raw = JSON.stringify([createdUtc, sessionId, storagePath]);
  return btoa(raw).replace(/=+$/, "");
}

function decodeCursor(raw: string): [string | null, string, string] {
  const padded = raw + "=".repeat((4 - (raw.length % 4)) % 4);
  const values = JSON.parse(atob(padded)) as unknown[];
  return [(values[0] as string | null) ?? null, String(values[1]), String(values[2])];
}

/** Маршруты каталога/контекста/профилей; null — не наш путь. */
export function handleCatalog(store: CatalogStore, request: MockHttpRequest): MockHttpReply | null {
  const { method, path } = request;
  if (path === "/api/catalog/sessions" && method === "GET") {
    return ok(store.catalog(request.searchParams));
  }
  const contextMatch = /^\/api\/context\/(.+)$/.exec(path);
  if (contextMatch) {
    const sessionId = decodeURIComponent(contextMatch[1] ?? "");
    if (method === "GET") {
      const payload = store.getContext(sessionId);
      return payload ? ok(payload) : notFound("сессия не найдена");
    }
    if (method === "PUT") {
      if (!request.nonceOk) return nonceRejected();
      const result = store.updateContext(sessionId, request.bodyJson<ContextUpdateRequest>());
      return result.body === undefined
        ? { status: result.status }
        : { status: result.status, body: result.body };
    }
    return null;
  }
  if (path === "/api/profiles" && method === "GET") {
    return ok({ items: store.profiles() });
  }
  const profileMatch = /^\/api\/profiles\/(.+)$/.exec(path);
  if (profileMatch) {
    const profileId = decodeURIComponent(profileMatch[1] ?? "");
    if (method === "DELETE") {
      if (!request.nonceOk) return nonceRejected();
      return { status: store.deleteProfile(profileId) };
    }
    if (method === "POST" || method === "PUT") {
      if (!request.nonceOk) return nonceRejected();
      const payload = request.bodyJson<{ kind: string; data: unknown }>();
      const result = store.upsertProfile(profileId, payload.kind, payload.data);
      return { status: result.status, body: result.body };
    }
  }
  if (path === "/api/analysis/recipes" && method === "GET") {
    return ok({
      items: [
        {
          recipe_id: "rec-default-spectrum",
          name: "Базовый спектр",
          sha256: "c".repeat(64),
          recipe: { window: "welch", bands: 512 },
        },
      ],
    });
  }
  return null;
}
