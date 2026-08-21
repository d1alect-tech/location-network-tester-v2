/** Доменные типы стабильных контрактов бэкенда LNT.
 *
 * Источники: src/lnt/ui/routes_sessions.py (health/config/sessions),
 * models_catalog.py, models_context.py, models_profiles.py,
 * routes_experiments.py. Имена полей совпадают с JSON бэкенда (snake_case).
 */

export interface HealthPayload {
  status: string;
  build_id: string;
}

export interface SimulateDefaults {
  duration_s: number;
  sample_rate_hz: number;
  seed: number;
  repeat: number;
  interval_s: number;
}

export interface CaptureDefaults {
  duration_s: number;
  sample_rate_hz: number;
  range_v: number;
  repeat: number;
  interval_s: number;
}

export interface OperationDefaults {
  simulate: SimulateDefaults;
  capture: CaptureDefaults;
  ranges: number[];
}

/** Ответ GET /api/config — единственный источник nonce запуска для клиента. */
export interface ConfigPayload {
  root: string;
  profiles: string[];
  defaults: OperationDefaults;
  build_id: string;
  mutation_nonce: string;
  static_asset_hash: string;
  static_assets: Record<string, string>;
}

/** lnt.catalog.query_models.SessionHealth. */
export const SESSION_HEALTH_VALUES = [
  "ok",
  "corrupt_manifest",
  "missing_files",
  "partial",
  "duplicate_id",
  "context_invalid",
  "analysis_invalid",
] as const;

export type SessionHealth = (typeof SESSION_HEALTH_VALUES)[number];

export interface CatalogSession {
  id: string;
  health: SessionHealth;
  created_utc: string | null;
  source: string | null;
  session_type: string | null;
  profile: string | null;
  label: string | null;
  storage_path?: string | null;
}

export interface CatalogPage {
  items: CatalogSession[];
  next_cursor: string | null;
}

/** Query-параметры GET /api/catalog/sessions (CatalogQuery). */
export interface CatalogQuery {
  page_size?: number;
  cursor?: string | null;
  health?: SessionHealth;
  session_type?: string;
  source?: string;
  profile?: string;
  label?: string;
  tag?: string;
  created_from?: string;
  created_to?: string;
  include_paths?: boolean;
}

export type FieldKind = "string" | "number" | "boolean" | "enum" | "timestamp";
export type FieldSource = "automatic" | "profile" | "user" | "derived";
export type CollectionStatus = "collected" | "unavailable" | "not_collected";

export interface ContextField {
  kind: FieldKind;
  value: string | number | boolean;
  unit?: string | null;
  uncertainty?: number | null;
  source?: FieldSource;
  collection_status?: CollectionStatus;
  collection_reason?: string | null;
  captured_at: string;
}

export interface ContextResponse {
  session_id: string;
  revision: number;
  health: string;
  reason_codes: string[];
  fields: Record<string, ContextField>;
  tags: string[];
  notes: string | null;
}

/** PUT /api/context/{session_id} — оптимистичная блокировка по revision. */
export interface ContextUpdateRequest {
  expected_revision: number;
  fields?: Record<string, ContextField> | null;
  tags?: string[] | null;
  notes?: string | null;
}

export type ProfileKind = "location" | "equipment" | "front_end" | "transformer" | "conditions";

export interface QuantityData {
  value: number;
  unit: string;
}

export interface LocationData {
  alias: string;
  outlet: string;
  circuit: string;
}

export interface EquipmentData {
  alias: string;
  model: string;
}

export interface FrontEndData {
  resistance: QuantityData;
  c1: QuantityData;
  c2: QuantityData;
}

export interface TransformerData {
  nominal_primary: QuantityData;
  nominal_secondary: QuantityData;
}

export interface ConditionsData {
  damper_state: "on" | "off" | "unknown";
  nearby_load_states: string[];
}

export type ProfileData =
  | LocationData
  | EquipmentData
  | FrontEndData
  | TransformerData
  | ConditionsData;

export interface ProfileRevision {
  profile_id: string;
  kind: ProfileKind;
  revision: number;
  captured_at: string;
  data: ProfileData;
}

export interface ProfileList {
  items: ProfileRevision[];
}

/** Краткий список дисковых сессий GET /api/sessions (payloads.sessions_payload). */
export interface LegacySessionItem {
  name: string;
  status: string;
  error: string | null;
  analyzed: boolean;
  summary: Record<string, unknown> | null;
}

export interface LegacySessionsPayload {
  sessions: LegacySessionItem[];
}
