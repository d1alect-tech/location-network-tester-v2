/** Билет командбара inspect → параметры маршрута capture (C1).
 * Командбар говорит своим словарём (2ch/1ch, sim/device, 2v/5v), capture —
 * нативным (CaptureModeId, CaptureSource, range_v из {5, 1, 0.5}).
 * Неизвестное отбрасывается ключом, а не билетом целиком: валидные поля
 * доезжают даже рядом с мусором. Пустая метка не едет (нечем предзаполнять). */

import type { InspectCaptureTicket } from "./v6Chrome";

const MODE_TO_CAPTURE: Record<string, string> = {
  "2ch": "rc_measurement",
  "1ch": "single_channel",
};

const SOURCE_TO_CAPTURE: Record<string, string> = {
  sim: "simulator",
  device: "device",
};

/** ±2 В нет среди допустимых range_v capture: ближайшее — 1 В
 * (|2−1|=1 против |2−0.5|=1.5 и |2−5|=3). Фолбэк видимый: форма capture
 * покажет «1 В» до старта, молчаливой подмены нет. */
const RANGE_TO_CAPTURE: Record<string, string> = {
  "5v": "5",
  "2v": "1",
};

function putIf(params: Record<string, string>, key: string, value: string | undefined): void {
  if (value !== undefined && value !== "") params[key] = value;
}

export function ticketToCaptureParams(ticket: InspectCaptureTicket): Record<string, string> {
  const params: Record<string, string> = {};
  putIf(params, "mode", MODE_TO_CAPTURE[ticket.mode]);
  putIf(params, "source", SOURCE_TO_CAPTURE[ticket.source]);
  putIf(params, "range_v", RANGE_TO_CAPTURE[ticket.range]);
  const duration = ticket.duration.trim();
  if (duration !== "") params.duration_s = duration;
  const rate = ticket.rate.trim();
  if (rate !== "") params.sample_rate_hz = rate;
  const label = ticket.label.trim();
  if (label !== "") params.label = label.slice(0, 128);
  return params;
}
