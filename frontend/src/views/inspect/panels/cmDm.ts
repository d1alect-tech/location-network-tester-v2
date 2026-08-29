/** CM/DM spectrum rows from cm_dm_spectrum.csv. cm_dm sessions only. */

import { el } from "../../../components/primitives/dom";
import { formatScalar } from "../w1Parse";
import { renderTable } from "./table";

export const CM_DM_KIND = "cm_dm";
export const CM_DM_LABEL = "CM/DM";

export type CmDmRow = {
  readonly frequencyHz: number;
  readonly cmPsd: number;
  readonly dmPsd: number;
  readonly coherence: number;
};

export function parseCmDmCsv(text: string): readonly CmDmRow[] | null {
  const lines = text.trim().split(/\r?\n/);
  const header = lines[0];
  if (header === undefined) return null;
  if (!header.includes("cm_psd") || !header.includes("dm_psd")) return null;
  const rows: CmDmRow[] = [];
  for (let i = 1; i < lines.length; i += 1) {
    const line = lines[i];
    if (line === undefined || line === "") continue;
    const parts = line.split(",");
    const frequencyHz = Number(parts[0]);
    const cmPsd = Number(parts[1]);
    const dmPsd = Number(parts[2]);
    const coherence = Number(parts[3]);
    if (![frequencyHz, cmPsd, dmPsd, coherence].every(Number.isFinite)) continue;
    rows.push({ frequencyHz, cmPsd, dmPsd, coherence });
  }
  return rows.length === 0 ? null : rows;
}

export function renderCmDm(body: HTMLElement, text: string): void {
  const rows = parseCmDmCsv(text);
  if (rows === null) return;
  body.append(el("p", { className: "lnt-w1-panel-note", text: `bins ${String(rows.length)}` }));
  renderTable(
    body,
    ["frequency_hz", "cm_psd", "dm_psd", "coherence"],
    rows.map((row) => [
      formatScalar(row.frequencyHz),
      formatScalar(row.cmPsd),
      formatScalar(row.dmPsd),
      formatScalar(row.coherence),
    ]),
  );
}
