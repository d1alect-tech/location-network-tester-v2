import { describe, expect, it } from "vitest";
import type { SessionDetailPayload } from "../../api/types-plots";
import { detailForPeaks } from "./spectrumPanelData";

/** Задача 9 (ui-refactor-3): мост пиков отдаёт ТОЛЬКО реальный detail-конверт
 * сервера (payloads.py:77-87 — честные флаги, настоящий манифест); объект без
 * конверта → null: доступность никогда не выдумывается. Раньше здесь
 * собирался fabricated-конверт manifest:{} + spectrum_available:true. */

const REAL_DETAIL: SessionDetailPayload = {
  name: "ses-a",
  manifest: { session_id: "ses-a" },
  analysis: {
    spectrum: { peaks: [{ frequency_hz: 1000, level_db: -40, prominence_db: 12, q_factor: 8 }] },
  },
  spectrum_available: false,
  waveform_available: true,
  ch2_available: false,
};

describe("detailForPeaks: конверт без фабрикации (задача 9)", () => {
  it("передаёт реальный detail-конверт как есть: честные флаги и манифест", () => {
    const detail = detailForPeaks(REAL_DETAIL);

    expect(detail).toBe(REAL_DETAIL);
    expect(detail?.spectrum_available).toBe(false);
    expect(detail?.waveform_available).toBe(true);
    expect(detail?.ch2_available).toBe(false);
    expect(detail?.manifest).toEqual({ session_id: "ses-a" });
  });

  it("объект без конверта detail → null: доступность не выдумывается", () => {
    expect(detailForPeaks({ analysis: { spectrum: { peaks: [] } } })).toBeNull();
    expect(detailForPeaks({ analysis: {} })).toBeNull();
    expect(detailForPeaks({})).toBeNull();
  });
});
