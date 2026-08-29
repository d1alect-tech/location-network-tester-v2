/** V5 — «Аналитическая станция»: эволюция V3 по итогам приёмки.
 *  Шапка несёт только навигацию и прибор; контекст открытой сессии вынесен в
 *  отдельную полосу; статус задачи и корень вернулись в статус-бар (§5.5);
 *  показания даны ровно один раз; пики подняты в видимую зону и связаны
 *  маркерами со спектром; весь срез читается на 1280x800 без прокрутки. */
import "./variantV5.css";
import { ERROR_STATE, JOB, SESSIONS } from "../showcase-redesign/data";
import { buildCaptureForm } from "./form";
import { buildCatalog, buildKpiRow, buildSpectrumPanel, buildTabbar, h } from "./kit";
import { METERS, buildPeaks } from "./metrics";
import { mountPeakMarkers } from "./peakMarkers";

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");

const SESSION_ROOT = "C:\\Users\\Kirill\\lnt-sessions";

/** Шапка 32px: навигация и прибор. В V3 та же полоса несла шесть сущностей сразу,
 *  и таб-бар в ней не читался как главный. */
function buildStationHeader(): HTMLElement {
  return h("header", "hdr", {}, [
    h("span", "hdr-brand", {}, ["LNT"]),
    buildTabbar("Инспекция"),
    h("span", "hdr-status", {}, [
      h("span", "dot", { "aria-hidden": "true" }),
      "Hantek 6022BE · готов",
    ]),
  ]);
}

/** Полоса контекста документа (§1.2): какая сессия открыта, её состояние и полный путь.
 *  Состояние дано глифом и словом — не только цветом (§6). */
function buildDocbar(): HTMLElement {
  const session = SESSIONS[0];
  if (session === undefined) throw new Error("нет сессий");
  const path = session.storagePath ?? session.id;
  return h("div", "docbar", {}, [
    h("span", `docbar-glyph glyph-${session.health}`, { "aria-hidden": "true" }, [session.glyph]),
    h("span", "docbar-name", { title: session.label }, [session.label]),
    h("span", "docbar-meta", {}, [
      `${session.healthLabel} · ${session.typeLabel} · ${session.date}`,
    ]),
    h("span", "docbar-path", { "data-doc-path": "", title: path }, [path]),
    h("div", "docbar-actions", {}, [
      h("button", "btn-quiet", { type: "button" }, ["Сравнить с Б"]),
      h("button", "btn-quiet", { type: "button" }, ["Экспорт CSV"]),
    ]),
  ]);
}

/** Статус-бар 32px (§5.5): активная задача и корень сессий — каждый со своим действием. */
function buildStationStatusbar(): HTMLElement {
  return h("footer", "statusbar", {}, [
    h("span", "statusbar-item", {}, [
      h("span", "dot", { "aria-hidden": "true" }),
      `${JOB.status} — ${JOB.stage} · ${JOB.series}`,
    ]),
    h("button", "btn-quiet", { type: "button" }, ["Отмена серии"]),
    h("span", "statusbar-spacer", {}),
    h("span", "statusbar-item num", {}, [`Корень: ${SESSION_ROOT}`]),
    h("button", "btn-quiet", { type: "button" }, ["Открыть корень"]),
  ]);
}

/** Ошибка одной строкой (§1.6): сообщение и действие рядом. Отдельная панель
 *  «Состояние» в V3 держала 340px постоянного места ради одного баннера. */
function buildInlineError(): HTMLElement {
  return h("aside", "banner banner-inline", { "data-showcase": "error", role: "alert" }, [
    h("span", "banner-glyph", { "aria-hidden": "true" }, ["✕"]),
    h("p", "banner-msg", {}, [ERROR_STATE.message]),
    h("button", "btn-quiet", { type: "button" }, [ERROR_STATE.action]),
  ]);
}

const peaksPanel = h("section", "panel", { "data-showcase": "metrics" }, [
  h("div", "panel-hd", {}, [h("h2", "panel-title", {}, ["Пики спектра"])]),
  h("div", "panel-bd is-bare", {}, [buildPeaks()]),
]);
const peakRows = Array.from(peaksPanel.querySelectorAll<HTMLElement>("[data-peak-row]"));

let redrawMarkers: (() => void) | undefined;
const spectrum = buildSpectrumPanel(320, {
  onDraw: () => redrawMarkers?.(),
  onPlot: (plot) => {
    redrawMarkers = mountPeakMarkers(plot, peakRows);
  },
});

app.append(
  h("div", "app-v5", { "data-showcase": "shell" }, [
    buildStationHeader(),
    buildDocbar(),
    h("div", "app-body", {}, [
      h("div", "col-cat", {}, [buildCatalog()]),
      h("div", "col-main", {}, [
        spectrum,
        h("div", "kpi-panel", {}, [buildKpiRow(METERS, "row")]),
        h("div", "bottom-row", {}, [buildCaptureForm(), peaksPanel]),
        buildInlineError(),
      ]),
    ]),
    buildStationStatusbar(),
  ]),
);
