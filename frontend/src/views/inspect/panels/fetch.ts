/** Artifact GET: JSON or text. 404 is absence, never a fake 0. */

import type { LntApiClient } from "../../../api/client";
import { ApiError, isAbortError, normalizeThrown } from "../../../api/errors";

export type ArtifactClient = {
  readonly requestJson: LntApiClient["requestJson"];
  readonly rawFetch: LntApiClient["rawFetch"];
};

export async function getArtifactJson(
  client: ArtifactClient,
  path: string,
  signal: AbortSignal,
): Promise<unknown | null> {
  try {
    return await client.requestJson("GET", path, undefined, { signal });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function getArtifactText(
  client: ArtifactClient,
  path: string,
  signal: AbortSignal,
): Promise<string | null> {
  let response: Response;
  try {
    response = await client.rawFetch(path, { method: "GET", signal });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw normalizeThrown(error);
  }
  if (response.status === 404) return null;
  if (!response.ok) throw new ApiError("http", { status: response.status });
  return await response.text();
}
