/** Иконки таббара оболочки: вариант «Иконки-ярлыки» (todo 7 ui-refactor).
 * Инлайн-SVG 16×16 на currentColor — тон пункта ведёт тон глифа.
 * Геометрия штриха из прототипа frontend/prototypes/shell.html (вариант 3). */
import { svgEl } from "../components/primitives/dom";
import type { V6Route } from "./v6Shell";

type IconPart = readonly [tag: "rect" | "circle" | "path", attrs: Record<string, string>];

const ICONS = {
  catalog: [
    ["rect", { x: "2", y: "3", width: "12", height: "4.4", rx: "1" }],
    ["rect", { x: "2", y: "8.6", width: "12", height: "4.4", rx: "1" }],
  ],
  capture: [
    ["circle", { cx: "8", cy: "8", r: "5.2" }],
    ["circle", { cx: "8", cy: "8", r: "1.9", fill: "currentColor", stroke: "none" }],
  ],
  scope: [
    ["rect", { x: "2", y: "3.2", width: "12", height: "9.6", rx: "1" }],
    ["path", { d: "M4.2 8.8h1.2l1.2-3.4 1.6 5.2 1.2-1.8h2" }],
  ],
  sa: [
    ["path", { d: "M4.8 12.6V9.4M8 12.6V4.8M11.2 12.6V7.2" }],
    ["path", { d: "M3 13.4h10" }],
  ],
  inspect: [
    ["circle", { cx: "7", cy: "7", r: "4.3" }],
    ["path", { d: "M10.2 10.2 14 14" }],
    ["path", { d: "M4.8 7.6 6.2 5.6l1.2 2.4 1.2-1.6" }],
  ],
  experiments: [
    [
      "path",
      {
        d: "M5.6 2h4.8M6.6 2v4.3L3.9 11.6A1.5 1.5 0 0 0 5.2 14h5.6a1.5 1.5 0 0 0 1.3-2.4L9.4 6.3V2",
      },
    ],
    ["path", { d: "M5.2 10.6h5.6" }],
  ],
  reports: [
    ["path", { d: "M4 2.2h5L12.4 5.6V13.8H4z" }],
    ["path", { d: "M9 2.2v3.4h3.4" }],
    ["path", { d: "M6.2 8.8h4.2M6.2 11.2h4.2" }],
  ],
  settings: [
    ["path", { d: "M2 5.2h6.2M11.8 5.2H14M2 10.8h2.2M7.8 10.8H14" }],
    ["circle", { cx: "10", cy: "5.2", r: "1.8" }],
    ["circle", { cx: "6", cy: "10.8", r: "1.8" }],
  ],
} as const satisfies Record<V6Route, readonly IconPart[]>;

/** Глиф раздела: декоративный (aria-hidden), имя пункта несёт ярлык. */
export function navIcon(route: V6Route): SVGElement {
  return svgEl(
    "svg",
    {
      class: "ico",
      viewBox: "0 0 16 16",
      fill: "none",
      stroke: "currentColor",
      "stroke-width": "1.4",
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
      "aria-hidden": "true",
    },
    ICONS[route].map(([tag, attrs]) => svgEl(tag, { ...attrs })),
  );
}
