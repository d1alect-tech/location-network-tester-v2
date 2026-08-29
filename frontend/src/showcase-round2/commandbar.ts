/** Захват как командная полоса (V6): на экране анализа запись — вспомогательное
 *  действие, поэтому все поля §1.5 живут в одной докированной строке, а серия и
 *  протокол остаются в disclosure. Панель на 310px высоты уступила место графику. */
import { CAPTURE_FORM, CAPTURE_MODES, CAPTURE_SOURCES } from "../showcase-redesign/data";
import { h } from "./kit";

function field(label: string, control: HTMLElement): HTMLLabelElement {
  return h("label", "cmd-field", {}, [h("span", "cmd-label", {}, [label]), control]);
}

function sel(name: string, items: readonly { id: string; title: string }[]): HTMLSelectElement {
  const node = h("select", "ctl", { name, id: `v6-${name}`, title: items[0]?.title ?? "" });
  for (const item of items) node.append(h("option", "", { value: item.id }, [item.title]));
  return node;
}

function inp(name: string, value: string, type = "text"): HTMLInputElement {
  return h("input", "ctl", { name, id: `v6-${name}`, type, value });
}

export function buildCommandbar(): HTMLElement {
  const body = h("div", "disc-body cmd-series", { id: "v6-series", hidden: "" }, [
    field("Повторов, шт.", inp("repeat", CAPTURE_FORM.repeat, "number")),
    field("Интервал стартов, с", inp("interval", CAPTURE_FORM.intervalS, "number")),
    field(
      "Профиль симуляции",
      sel(
        "profile",
        CAPTURE_FORM.profiles.map((profile) => ({ id: profile, title: profile })),
      ),
    ),
  ]);
  const toggle = h(
    "button",
    "disc-toggle",
    { type: "button", "aria-expanded": "false", "aria-controls": "v6-series" },
    ["Серия и протокол"],
  );
  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!open));
    body.hidden = open;
  });

  const form = h("form", "cmdbar", { "data-showcase": "capture-form" }, [
    h("div", "cmd-fields", {}, [
      field(
        "Режим измерения",
        sel(
          "mode",
          CAPTURE_MODES.map((mode) => ({ id: mode.id, title: `${mode.title} · ${mode.channels}` })),
        ),
      ),
      field("Источник записи", sel("source", CAPTURE_SOURCES)),
      field("Длительность, с", inp("duration", CAPTURE_FORM.durationS, "number")),
      field("Частота, Гц", inp("rate", CAPTURE_FORM.sampleRateHz, "number")),
      field(
        "Диапазон CH1",
        sel(
          "range",
          CAPTURE_FORM.ranges.map((range) => ({ id: range, title: range })),
        ),
      ),
      field("Метка", inp("label", CAPTURE_FORM.label)),
      h("div", "cmd-actions", {}, [
        toggle,
        h("button", "btn", { type: "submit" }, ["Запустить запись"]),
      ]),
    ]),
    body,
  ]);
  form.addEventListener("submit", (event) => event.preventDefault());
  return form;
}
