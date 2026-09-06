/** U2: заливка channel-bar в capture из формы и stored-префов анализа.
 *  Полоса — проекция (3 кГц … min(3 МГц, 0.45 × fs), та же формула, что README);
 *  RBW/окно — то, что применится при следующем анализе (ключи селекторов
 *  spectrum-панели); сегментов до анализа нет — честный прочерк. */

import type { ChannelbarHandle } from "../components/channelbar/channelbar";
import { createChannelbar, formatBandRange, formatHz } from "../components/channelbar/channelbar";
import { MARKER_WINDOW_LABELS, storedRbw, storedWindow } from "../views/inspect/spectrumSelectors";
import type { ModeFormHandle } from "./modeForm";
import type { CaptureFormValues } from "./modes";

/** Монтаж бара с подпиской на форму. U4: леса снесены, всегда монтируется. */
export function mountCaptureChannelbar(form: ModeFormHandle): ChannelbarHandle {
  const bar = createChannelbar();
  const repaint = (): void => paintCaptureChannelbar(bar, form.values());
  form.onChange(repaint);
  repaint();
  return bar;
}

export function paintCaptureChannelbar(bar: ChannelbarHandle, values: CaptureFormValues): void {
  const fs = Number(values.sampleRateHz);
  const rbw = storedRbw();
  const window = storedWindow();
  bar.paint({
    band:
      Number.isFinite(fs) && fs > 0 ? formatBandRange(3000, Math.min(3_000_000, 0.45 * fs)) : null,
    rbw: rbw === null ? null : formatHz(rbw),
    window: window === null ? "Ханн" : (MARKER_WINDOW_LABELS[window] ?? window),
    detector: "Среднее",
    segments: null,
  });
}
