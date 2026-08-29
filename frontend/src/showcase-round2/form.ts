/** Раунд 2: форма захвата (сериалы в disclosure) и inline-баннер ошибки (§1.5, §1.6). */
import {
  CAPTURE_FORM,
  CAPTURE_MODES,
  CAPTURE_SOURCES,
  ERROR_STATE,
} from "../showcase-redesign/data";
import { h } from "./kit";

function field(label: string, control: HTMLElement): HTMLLabelElement {
  return h("label", "field", {}, [h("span", "field-label", {}, [label]), control]);
}

function sel(name: string, items: readonly { id: string; title: string }[]): HTMLSelectElement {
  const node = h("select", "ctl", { name, id: name });
  for (const item of items) node.append(h("option", "", { value: item.id }, [item.title]));
  return node;
}

function inp(name: string, value: string, type = "text"): HTMLInputElement {
  return h("input", "ctl", { name, id: name, type, value });
}

/** Disclosure «Серия и протокол»: повторы, интервал, профиль симуляции. */
function buildSeriesDisclosure(): { toggle: HTMLElement; body: HTMLElement } {
  const toggle = h(
    "button",
    "disc-toggle",
    { type: "button", "aria-expanded": "false", "aria-controls": "series-bay" },
    ["Серия и протокол"],
  );
  const body = h("div", "disc-body", { id: "series-bay", hidden: "" }, [
    field("Повторов, шт.", inp("repeat", CAPTURE_FORM.repeat, "number")),
    field("Интервал стартов, с", inp("interval", CAPTURE_FORM.intervalS, "number")),
    field(
      "Профиль симуляции",
      sel(
        "profile",
        CAPTURE_FORM.profiles.map((p) => ({ id: p, title: p })),
      ),
    ),
  ]);
  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!open));
    body.hidden = open;
  });
  return { toggle, body };
}

/** Форма захвата: поля — классы .form-grid; сетку задаёт вариант. */
export function buildCaptureForm(): HTMLElement {
  const modeSel = sel(
    "mode",
    CAPTURE_MODES.map((mode) => ({ id: mode.id, title: `${mode.title} · ${mode.channels}` })),
  );
  const rangeSel = sel(
    "range",
    CAPTURE_FORM.ranges.map((range) => ({ id: range, title: range })),
  );
  const disclosure = buildSeriesDisclosure();

  const form = h("form", "panel", { "data-showcase": "capture-form" }, [
    h("div", "panel-hd", {}, [h("h2", "panel-title", {}, ["Захват"])]),
    h("div", "panel-bd", {}, [
      h("div", "form-grid", {}, [
        field("Режим измерения", modeSel),
        field("Источник записи", sel("source", CAPTURE_SOURCES)),
        field("Длительность, с", inp("duration", CAPTURE_FORM.durationS, "number")),
        field("Частота дискретизации, Гц", inp("rate", CAPTURE_FORM.sampleRateHz, "number")),
        field("Диапазон CH1", rangeSel),
        field("Метка", inp("label", CAPTURE_FORM.label)),
      ]),
      disclosure.toggle,
      disclosure.body,
      h("div", "form-actions", {}, [h("button", "btn", { type: "submit" }, ["Запустить запись"])]),
    ]),
  ]);
  form.addEventListener("submit", (event) => event.preventDefault());
  return form;
}

/** Ошибка подключения: приглушённый тинт, без «кислотности» (§4). */
export function buildError(): HTMLElement {
  return h("aside", "banner", { "data-showcase": "error", role: "alert" }, [
    h("h2", "banner-title", {}, [ERROR_STATE.title]),
    h("p", "banner-msg", {}, [ERROR_STATE.message]),
    h("button", "btn btn-secondary", { type: "button" }, [ERROR_STATE.action]),
  ]);
}
