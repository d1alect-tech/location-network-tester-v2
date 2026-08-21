/** Runtime-стражи контрактов: неизвестный JSON не попадает в состояние UI. */

import {
  type CatalogPage,
  type CatalogSession,
  type ConfigPayload,
  type ContextField,
  type ContextResponse,
  type HealthPayload,
  type ProfileData,
  type ProfileList,
  type ProfileRevision,
  SESSION_HEALTH_VALUES,
} from "./types";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function hasString(record: Record<string, unknown>, key: string): boolean {
  return isString(record[key]);
}

function optString(record: Record<string, unknown>, key: string): boolean {
  const value = record[key];
  return value === undefined || value === null || isString(value);
}

export function isHealthPayload(value: unknown): value is HealthPayload {
  return isRecord(value) && hasString(value, "status") && hasString(value, "build_id");
}

function isOperationDefaults(value: unknown): boolean {
  if (!isRecord(value)) return false;
  const sim = value.simulate;
  const cap = value.capture;
  return (
    isRecord(sim) &&
    isRecord(cap) &&
    ["duration_s", "sample_rate_hz", "seed", "repeat", "interval_s"].every((k) =>
      isNumber(sim[k]),
    ) &&
    ["duration_s", "sample_rate_hz", "range_v", "repeat", "interval_s"].every((k) =>
      isNumber(cap[k]),
    ) &&
    Array.isArray(value.ranges) &&
    value.ranges.every(isNumber)
  );
}

export function isConfigPayload(value: unknown): value is ConfigPayload {
  return (
    isRecord(value) &&
    hasString(value, "root") &&
    isStringArray(value.profiles) &&
    isOperationDefaults(value.defaults) &&
    hasString(value, "build_id") &&
    hasString(value, "mutation_nonce") &&
    hasString(value, "static_asset_hash") &&
    isRecord(value.static_assets) &&
    Object.values(value.static_assets).every(isString)
  );
}

function isCatalogSession(value: unknown): value is CatalogSession {
  if (!isRecord(value)) return false;
  return (
    hasString(value, "id") &&
    isString(SESSION_HEALTH_VALUES.find((h) => h === value.health)) &&
    optString(value, "created_utc") &&
    optString(value, "source") &&
    optString(value, "session_type") &&
    optString(value, "profile") &&
    optString(value, "label")
  );
}

export function isCatalogPage(value: unknown): value is CatalogPage {
  return (
    isRecord(value) &&
    Array.isArray(value.items) &&
    value.items.every(isCatalogSession) &&
    (value.next_cursor === null || value.next_cursor === undefined || isString(value.next_cursor))
  );
}

function isContextField(value: unknown): value is ContextField {
  if (!isRecord(value)) return false;
  const scalar = isString(value.value) || isNumber(value.value) || typeof value.value === "boolean";
  return scalar && hasString(value, "kind") && hasString(value, "captured_at");
}

export function isContextResponse(value: unknown): value is ContextResponse {
  return (
    isRecord(value) &&
    hasString(value, "session_id") &&
    isNumber(value.revision) &&
    hasString(value, "health") &&
    isStringArray(value.reason_codes) &&
    isRecord(value.fields) &&
    Object.values(value.fields).every(isContextField) &&
    isStringArray(value.tags) &&
    (value.notes === null || value.notes === undefined || isString(value.notes))
  );
}

const PROFILE_KINDS = new Set(["location", "equipment", "front_end", "transformer", "conditions"]);

function isProfileData(kind: string, value: unknown): value is ProfileData {
  if (!isRecord(value)) return false;
  switch (kind) {
    case "location":
      return ["alias", "outlet", "circuit"].every((k) => isString(value[k]));
    case "equipment":
      return ["alias", "model"].every((k) => isString(value[k]));
    case "front_end":
      return ["resistance", "c1", "c2"].every(
        (k) => isRecord(value[k]) && isNumber(value[k].value) && isString(value[k].unit),
      );
    case "transformer":
      return ["nominal_primary", "nominal_secondary"].every(
        (k) => isRecord(value[k]) && isNumber(value[k].value) && isString(value[k].unit),
      );
    case "conditions":
      return (
        ["on", "off", "unknown"].includes(String(value.damper_state)) &&
        isStringArray(value.nearby_load_states)
      );
    default:
      return false;
  }
}

function isProfileRevision(value: unknown): value is ProfileRevision {
  return (
    isRecord(value) &&
    hasString(value, "profile_id") &&
    isString(value.kind) &&
    PROFILE_KINDS.has(value.kind) &&
    isNumber(value.revision) &&
    hasString(value, "captured_at") &&
    isProfileData(value.kind, value.data)
  );
}

export function isProfileList(value: unknown): value is ProfileList {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(isProfileRevision);
}
