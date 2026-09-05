/** Типолаба R3-A: макет «Стойки» + живой переключатель шрифтовых систем.
 *  Реакция владельца на #14: макет A хорош, работаем над шрифтами. */
import "../showcase-redesign/fonts/fonts.css";
import "./tokens.css";
import "./kit.css";
import "./variantA.css";
import "./typeLab.css";
import { h } from "./kit";
import { mountVariantA } from "./variantALayout";

interface TypeSystem {
  id: string;
  label: string;
  note: string;
}

const SYSTEMS: readonly TypeSystem[] = [
  { id: "t1", label: "Плекс", note: "IBM Plex Sans + Plex Mono — база R3-A" },
  { id: "t2", label: "Терминал", note: "JetBrains Mono целиком — прошивка прибора" },
  { id: "t3", label: "Гротеск", note: "Golos 800 + Source Code Pro, крупные числа" },
  { id: "t4", label: "Журнал", note: "Source Serif 4 для чисел + Source Sans 3" },
  { id: "t5", label: "Системный", note: "Arial + Consolas — без веб-шрифтов вообще" },
];

function select(id: string, buttons: readonly HTMLButtonElement[]): void {
  document.body.dataset.type = id;
  window.location.hash = id;
  for (const button of buttons) {
    button.setAttribute("aria-pressed", String(button.dataset.system === id));
  }
}

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");
document.body.classList.add("r3", "r3--a");
mountVariantA(app);

const buttons = SYSTEMS.map((system) =>
  h("button", "type-btn", { type: "button", "data-system": system.id, title: system.note }, [
    h("span", "t-tag", {}, [system.id.toUpperCase()]),
    h("span", "type-btn-label", {}, [system.label]),
  ]),
);
for (const button of buttons) {
  button.addEventListener("click", () => select(button.dataset.system ?? "t1", buttons));
}

app.append(
  h(
    "div",
    "type-lab",
    { "data-r3": "type-lab", role: "group", "aria-label": "Шрифтовая система" },
    [h("span", "t-tag type-lab-title", {}, ["Шрифты"]), ...buttons],
  ),
);
const fromHash = window.location.hash.slice(1);
select(SYSTEMS.some((system) => system.id === fromHash) ? fromHash : "t1", buttons);
