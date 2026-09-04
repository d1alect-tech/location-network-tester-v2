/** B3-фасад: селекторы RBW/окна + таблица маркеров одним хэндлом для панели. */

import { createMarkersTable } from "./spectrumMarkersTable";
import type { MarkersPaintSource } from "./spectrumReadout";
import { createSpectrumSelectors } from "./spectrumSelectors";
import { createUnitsControl } from "./spectrumUnits";

export type { MarkersPaintSource };

export interface SpectrumExtras {
  readonly selects: HTMLElement;
  readonly markers: HTMLElement;
  paint(source: MarkersPaintSource): void;
}

export function createSpectrumExtras(): SpectrumExtras {
  const selectors = createSpectrumSelectors();
  let repaint: (source: MarkersPaintSource) => void = () => undefined;
  const units = createUnitsControl(() => repaint(last));
  const table = createMarkersTable(() => units.unit());
  let last: MarkersPaintSource = {
    payloadA: { frequency_hz: [], psd_v2_per_hz: [], point_count: 0 },
    payloadB: null,
    analysis: {},
  };
  repaint = (source) => {
    selectors.paint(source.payloadA);
    table.paint(source);
  };
  const selects = document.createElement("div");
  selects.append(selectors.root, units.root);
  return {
    selects,
    markers: table.root,
    paint(source) {
      last = source;
      repaint(source);
    },
  };
}
