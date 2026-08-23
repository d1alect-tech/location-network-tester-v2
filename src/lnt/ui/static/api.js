/** @typedef {{status: "ok"}} HealthPayload */
/** @typedef {Record<string, unknown>} ConfigPayload */
/** @typedef {Record<string, unknown>} SessionSummary */
/** @typedef {{sessions: SessionSummary[]}} SessionListPayload */
/** @typedef {Record<string, unknown>} SessionDetailPayload */
/**
 * @typedef {object} SpectrumPayload
 * @property {number[]} frequency_hz
 * @property {number[]} psd_v2_per_hz
 * @property {number} point_count
 */
/**
 * @typedef {object} WaveformPayload
 * @property {"ch1" | "ch2"} channel
 * @property {number[]} time_s
 * @property {number[]} voltage_v
 * @property {number} point_count
 */
/**
 * @typedef {object} JobRequest
 * @property {"simulate" | "capture" | "analyze" | "compare" | "selftest" | "device_check"} kind
 */
/**
 * @typedef {object} JobSnapshot
 * @property {string} job_id
 * @property {string} status
 */
/**
 * @typedef {object} JobWatcher
 * @property {() => void} close
 */
/**
 * @typedef {object} JobWatchHandlers
 * @property {(snapshot: JobSnapshot) => void} onSnapshot
 * @property {(error: Event) => void} onError
 */

export const CSRF_HEADER = "X-LNT-Mutation-Nonce";
let mutationNonce = "";

export function installMutationNonce(nonce) {
  mutationNonce = nonce;
}

export class ApiError extends Error {
  /**
   * @param {number} status HTTP status, or zero when the server is unreachable.
   * @param {string} detail User-facing error detail.
   */
  constructor(status, detail) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * @template T
 * @param {string} path Same-origin API path.
 * @param {RequestInit} [options]
 * @returns {Promise<T>}
 */
async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new ApiError(0, "Сеть недоступна.");
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : response.statusText || "Ошибка запроса.";
    throw new ApiError(response.status, detail);
  }

  return response.json();
}

/** @returns {Promise<ConfigPayload>} */
export async function getConfig() {
  const config = await request("/api/config");
  installMutationNonce(config.mutation_nonce);
  return config;
}

/** @returns {Promise<SessionListPayload>} */
export async function listSessions() {
  return request("/api/sessions");
}

/**
 * @param {string} name
 * @returns {Promise<SessionDetailPayload>}
 */
export async function getSessionDetail(name) {
  return request(`/api/sessions/${encodeURIComponent(name)}`);
}

/**
 * @param {string} name
 * @param {number} [maxPoints=5000]
 * @returns {Promise<SpectrumPayload>}
 */
export async function getSpectrum(name, maxPoints = 5000) {
  const query = new URLSearchParams({ max_points: String(maxPoints) });
  return request(`/api/sessions/${encodeURIComponent(name)}/spectrum?${query}`);
}

/**
 * @param {string} name
 * @param {"ch1" | "ch2"} [channel="ch1"]
 * @param {number} [maxPoints=4000]
 * @returns {Promise<WaveformPayload>}
 */
export async function getWaveform(name, channel = "ch1", maxPoints = 4000) {
  const query = new URLSearchParams({
    channel,
    max_points: String(maxPoints),
  });
  return request(`/api/sessions/${encodeURIComponent(name)}/waveform?${query}`);
}

/**
 * @param {JobRequest} jobRequest
 * @returns {Promise<JobSnapshot>}
 */
export async function startJob(jobRequest) {
  return request("/api/jobs", {
    method: "POST",
    headers: {
      [CSRF_HEADER]: mutationNonce,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(jobRequest),
  });
}

/**
 * @param {string} jobId
 * @returns {Promise<JobSnapshot>}
 */
export async function getJob(jobId) {
  return request(`/api/jobs/${encodeURIComponent(jobId)}`);
}

/**
 * @param {string} jobId
 * @returns {Promise<JobSnapshot>}
 */
export async function cancelJob(jobId) {
  return request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
    headers: { [CSRF_HEADER]: mutationNonce },
  });
}

/**
 * @param {string} jobId
 * @param {JobWatchHandlers} handlers
 * @returns {JobWatcher}
 */
export function watchJob(jobId, { onSnapshot, onError }) {
  const eventSource = new EventSource(
    `/api/jobs/${encodeURIComponent(jobId)}/events`,
  );

  eventSource.addEventListener("snapshot", (event) => {
    const snapshot = JSON.parse(event.data);
    onSnapshot(snapshot);
    if (
      snapshot.status === "succeeded" ||
      snapshot.status === "failed" ||
      snapshot.status === "cancelled"
    ) {
      eventSource.close();
    }
  });
  eventSource.addEventListener("error", (event) => {
    onError(event);
  });

  return {
    close() {
      eventSource.close();
    },
  };
}
