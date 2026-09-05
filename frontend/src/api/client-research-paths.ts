// Путевые helpers исследовательского контура v2 (выделено из client-research.ts):
// курсорная страница, пути экспериментов/запусков, nonce-подпись мутаций.
import type { LntApiClient, RequestOptions } from "./client";
import { requireCursorPage } from "./client-research-guards";
import type { ItemAssert } from "./client-research-guards";
import type { CursorPage } from "./types-research";

export const V2 = "/api/v2";

export async function fetchPage<T>(
  client: LntApiClient,
  path: string,
  pageSize: number | undefined,
  cursor: string | null | undefined,
  options: RequestOptions,
  assertItem: ItemAssert<T>,
): Promise<CursorPage<T>> {
  const params = new URLSearchParams();
  if (pageSize !== undefined) params.set("page_size", String(pageSize));
  if (cursor) params.set("cursor", cursor);
  const qs = params.toString();
  const payload = await client.requestJson(
    "GET",
    `${path}${qs ? `?${qs}` : ""}`,
    undefined,
    options,
  );
  return requireCursorPage(payload, assertItem);
}

export const experimentPath = (id: string, suffix = "") =>
  `${V2}/experiments/${encodeURIComponent(id)}${suffix}`;

export const runPath = (runId: string, suffix = "") =>
  `${V2}/protocol-runs/${encodeURIComponent(runId)}${suffix}`;

export const mutation = (options: RequestOptions): RequestOptions & { mutation: boolean } => ({
  ...options,
  mutation: true,
});
