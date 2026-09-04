/** B3-фасад: селекторы RBW/окна + таблица маркеров одним хэндлом для панели. */

import { createMarkersTable } from "./spectrumMarkersTable";
import type { MarkersPaintSource } from "./spectrumReadout";
import { createSpectrumSelectors } from "./spectrumSelectors";

export type { MarkersPaintSource };

export interface SpectrumExtras {
  readonly selects: HTMLElement;
  readonly markers: HTMLElement;
  paint(source: MarkersPaintSource): void;
}

export function createSpectrumExtras(): SpectrumExtras {
  const selectors = createSpectrumSelectors();
  const table = createMarkersTable();
  return {
    selects: selectors.root,
    markers: table.root,
    paint(source) {
      selectors.paint(source.payloadA);
      table.paint(source);
    },
  };
}
