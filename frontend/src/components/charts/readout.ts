/** Сводка выбранного значения под курсором (todo 41).
 * Общая для связанных графиков: обновляется из хука setCursor любого из них.
 * aria-live — доступная альтернатива визуальному курсору. */

import { el } from "../primitives/dom";

export interface ReadoutSeries {
  label: string;
  marker?: string;
}

export interface ReadoutUpdate {
  xValue: number | null;
  values: ReadonlyArray<number | null>;
}

function format(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString("ru-RU", { maximumSignificantDigits: 6 });
}

const OUTSIDE = "Курсор вне графика";

export interface ReadoutHandle {
  root: HTMLElement;
  update(update: ReadoutUpdate): void;
  setSeries(series: readonly ReadoutSeries[]): void;
}

export function createReadout(
  xLabel: string,
  yLabel: string,
  initialSeries: readonly ReadoutSeries[] = [],
): ReadoutHandle {
  const caption = el("span", { className: "lnt-readout-caption", text: "Значение под курсором" });
  const table = el("table", { className: "lnt-readout-table" });
  const header = el("thead");
  const headerRow = el("tr", {}, [
    el("th", { text: xLabel }),
    ...initialSeries.map((series) =>
      el("th", {
        text: series.marker === undefined ? series.label : `${series.marker} ${series.label}`,
      }),
    ),
  ]);
  header.append(headerRow);
  const body = el("tbody");
  const valueRow = el("tr", {}, [el("td", { text: "—" })]);
  body.append(valueRow);
  table.append(header, body);

  const live = el("p", {
    className: "lnt-visually-hidden",
    attrs: { "aria-live": "polite" },
  });

  let seriesLabels = initialSeries;

  function renderRow(update: ReadoutUpdate): string[] {
    const cells = [format(update.xValue)];
    for (const value of update.values) {
      cells.push(value === null && update.xValue !== null ? "нет в ряду" : format(value));
    }
    valueRow.replaceChildren(...cells.map((text) => el("td", { text })));
    return cells;
  }

  function rebuildHeader(): void {
    header.replaceChildren(
      el("tr", {}, [
        el("th", { text: xLabel }),
        ...seriesLabels.map((series) =>
          el("th", {
            text: series.marker === undefined ? series.label : `${series.marker} ${series.label}`,
          }),
        ),
      ]),
    );
  }

  return {
    root: el("div", { className: "lnt-readout" }, [caption, table, live]),
    setSeries(series) {
      seriesLabels = series;
      rebuildHeader();
    },
    update(update) {
      if (update.xValue === null) {
        valueRow.replaceChildren(
          el("td", { attrs: { colspan: String(seriesLabels.length + 1) }, text: OUTSIDE }),
        );
        live.textContent = OUTSIDE;
        return;
      }
      const cells = renderRow(update);
      live.textContent = `${yLabel}. ${xLabel}: ${cells[0]}; ${cells
        .slice(1)
        .map((cell, i) => `${seriesLabels[i]?.label ?? ""}: ${cell}`)
        .join("; ")}`;
    },
  };
}
