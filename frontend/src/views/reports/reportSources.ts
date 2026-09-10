import type { LntApiClient } from "../../api/client";
import type { OpenRecord } from "../../api/types-research";
import { metricValue } from "./reportRequest";

export async function loadReportHealth(
  client: LntApiClient,
  signal: AbortSignal,
): Promise<{ map: Map<string, string>; warningMessage: string | null }> {
  try {
    const page = await client.catalogSessions({ page_size: 200 }, { signal });
    const map = new Map<string, string>();
    for (const session of page.items) map.set(session.id, String(session.health ?? "ok"));
    return { map, warningMessage: null };
  } catch (error) {
    if (signal.aborted) throw error;
    return {
      map: new Map(),
      warningMessage: error instanceof Error ? error.message : String(error),
    };
  }
}

export async function collectReportValues(
  client: LntApiClient,
  members: OpenRecord[],
  featureKey: string,
  signal: AbortSignal,
): Promise<{ values: Map<string, number>; failures: { session_id: string; message: string }[] }> {
  const values = new Map<string, number>();
  const failures: { session_id: string; message: string }[] = [];
  for (const member of members) {
    const sessionId = String(member.session_id);
    try {
      const detail = await client.plots.detail(sessionId, { signal });
      signal.throwIfAborted();
      const value = metricValue(detail, featureKey);
      if (value !== null) values.set(sessionId, value);
      else failures.push({ session_id: sessionId, message: "значение отсутствует в деталях" });
    } catch (error) {
      if (signal.aborted) throw error;
      failures.push({
        session_id: sessionId,
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }
  return { values, failures };
}
