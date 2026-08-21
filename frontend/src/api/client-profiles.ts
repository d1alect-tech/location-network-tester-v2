/** Доменный под-клиент CRUD профилей (Todo 39): создание, новая revision
 * и скрытие профиля. Маршруты: routes_profiles.py. Все мутации подписываются
 * nonce запуска (X-LNT-Mutation-Nonce), конверты проверяются guard'ами. */

import type { LntApiClient, RequestOptions } from "./client";
import { ApiError } from "./errors";
import { isProfileRevision, isRecord } from "./guards";
import type { ProfileData, ProfileKind, ProfileRevision } from "./types";

/** Тело POST/PUT /api/profiles/{profile_id} — дискриминатор kind + data. */
export interface ProfileWriteRequest {
  kind: ProfileKind;
  data: ProfileData;
}

export interface ProfilesApi {
  create(
    profileId: string,
    request: ProfileWriteRequest,
    options?: RequestOptions,
  ): Promise<ProfileRevision>;
  update(
    profileId: string,
    request: ProfileWriteRequest,
    options?: RequestOptions,
  ): Promise<ProfileRevision>;
  remove(profileId: string, options?: RequestOptions): Promise<void>;
}

function requireRevision(payload: unknown): ProfileRevision {
  if (!isRecord(payload) || !isProfileRevision(payload)) throw new ApiError("parse");
  return payload;
}

const mutation = (options: RequestOptions): RequestOptions & { mutation: boolean } => ({
  ...options,
  mutation: true,
});

export function createProfilesApi(client: LntApiClient): ProfilesApi {
  const path = (profileId: string) => `/api/profiles/${encodeURIComponent(profileId)}`;
  return {
    create: async (profileId, request, options = {}) =>
      requireRevision(
        await client.requestJson("POST", path(profileId), request, mutation(options)),
      ),
    update: async (profileId, request, options = {}) =>
      requireRevision(await client.requestJson("PUT", path(profileId), request, mutation(options))),
    remove: async (profileId, options = {}) => {
      // 204 No Content — пустое тело валидно, иное означает повреждённый ответ.
      const payload = await client.requestJson("DELETE", path(profileId), undefined, {
        ...mutation(options),
      });
      if (payload !== undefined && payload !== null && payload !== "") {
        throw new ApiError("parse");
      }
    },
  };
}
