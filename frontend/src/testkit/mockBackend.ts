/** ТЕСТОВЫЙ in-memory бэкенд (только e2e/spec): повторяет контракты
 * routes_catalog.py / routes_context.py / routes_profiles.py — включая
 * keyset-пейджинг, casefold-подстроку метки, оптимистичную блокировку
 * revision (409) и nonce-заголовок мутаций. Используется через page.route. */

import type {
  CatalogPage,
  CatalogSession,
  ContextResponse,
  ContextUpdateRequest,
  ProfileRevision,
} from "../api/types";
import { contextFor, defaultProfiles, generateSessions } from "./catalogFixture";

const NONCE = "test-nonce-t39";

export interface CatalogFilters {
  health?: string;
  session_type?: string;
  profile?: string;
  label?: string;
  tag?: string;
  created_from?: string;
  created_to?: string;
}

export class MockLntBackend {
  readonly sessions: CatalogSession[];
  private readonly storagePaths = new Map<string, string>();
  private contexts = new Map<string, ContextResponse>();
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

  configPayload(): Record<string, unknown> {
    return {
      root: "C:\\lnt-sessions-test",
      profiles: ["loft-main"],
      defaults: {
        simulate: {
          duration_s: 2.4,
          sample_rate_hz: 20_000_000,
          seed: 1,
          repeat: 3,
          interval_s: 5,
        },
        capture: {
          duration_s: 2.4,
          sample_rate_hz: 20_000_000,
          range_v: 5,
          repeat: 3,
          interval_s: 5,
        },
        ranges: [0.5, 1, 5],
      },
      build_id: "t39-build",
      mutation_nonce: NONCE,
      static_asset_hash: "test",
      static_assets: {},
    };
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
      const created: ProfileRevision = {
        profile_id: profileId,
        kind: kind as ProfileRevision["kind"],
        revision: 1,
        captured_at: "2026-08-01T00:00:00Z",
        data: data as ProfileRevision["data"],
      };
      this.profilesStore.push(created);
      return { status: 201, body: created };
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

/** Подключает бэкенд к Playwright page: перехват ТОЛЬКО настоящих API-путей
 * (pathname начинается с /api/), чтобы не задеть модули сборки вида
 * /static/v2/src/api/client.ts. */
export async function attachMockBackend(
  page: import("@playwright/test").Page,
  backend: MockLntBackend,
): Promise<void> {
  await page.route(
    (url) => url.pathname.startsWith("/api/") || url.pathname.includes("!/api/"),
    async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname.replace(/^\/static\/v2/, "");
      const method = route.request().method();
      const json = (status: number, body?: unknown): Promise<void> =>
        route.fulfill({
          status,
          contentType: "application/json",
          body: body === undefined ? "" : JSON.stringify(body),
        });

      if (path === "/api/config" && method === "GET") return json(200, backend.configPayload());
      if (path === "/api/health" && method === "GET") {
        return json(200, { status: "ok", build_id: "t39-build" });
      }
      if (path === "/api/catalog/sessions" && method === "GET") {
        return json(200, backend.catalog(url.searchParams));
      }
      const contextMatch = /^\/api\/context\/(.+)$/.exec(path);
      if (contextMatch) {
        const sessionId = decodeURIComponent(contextMatch[1] ?? "");
        if (method === "GET") {
          const payload = backend.getContext(sessionId);
          return payload ? json(200, payload) : json(404, { detail: "сессия не найдена" });
        }
        if (method === "PUT") {
          if (route.request().headers()["x-lnt-mutation-nonce"] !== NONCE) {
            return json(403, { code: "mutation_nonce_invalid", detail: "нет nonce" });
          }
          const result = backend.updateContext(
            sessionId,
            route.request().postDataJSON() as ContextUpdateRequest,
          );
          return result.body === undefined ? json(result.status) : json(result.status, result.body);
        }
      }
      if (path === "/api/profiles" && method === "GET") {
        return json(200, { items: backend.profiles() });
      }
      const profileMatch = /^\/api\/profiles\/(.+)$/.exec(path);
      if (profileMatch) {
        const profileId = decodeURIComponent(profileMatch[1] ?? "");
        if (method === "DELETE") {
          if (route.request().headers()["x-lnt-mutation-nonce"] !== NONCE) {
            return json(403, { code: "mutation_nonce_invalid", detail: "нет nonce" });
          }
          return json(backend.deleteProfile(profileId));
        }
        if (method === "POST" || method === "PUT") {
          if (route.request().headers()["x-lnt-mutation-nonce"] !== NONCE) {
            return json(403, { code: "mutation_nonce_invalid", detail: "нет nonce" });
          }
          const payload = route.request().postDataJSON() as { kind: string; data: unknown };
          const result = backend.upsertProfile(profileId, payload.kind, payload.data);
          return json(result.status, result.body);
        }
      }
      return json(404, { detail: `нет мока: ${method} ${path}` });
    },
  );
}
