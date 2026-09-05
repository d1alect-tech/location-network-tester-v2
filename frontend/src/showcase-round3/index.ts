/** Индекс раунда 3: три витрины по дизайн-брифу #13. */
import "./index.css";
import { h } from "./kit";

const VARIANTS = [
  {
    page: "showcase-r3a.html",
    title: "R3-A «Стойка»",
    note: "FSW-плотность: полный периметр, softkey-колонка, нейтральный графит, IBM Plex.",
  },
  {
    page: "showcase-r3b.html",
    title: "R3-B «Верстак»",
    note: "Spike-гибрид: график-центр, докируемые панели, тёплый графит, Golos + JetBrains Mono.",
  },
  {
    page: "showcase-r3c.html",
    title: "R3-C «Пара»",
    note: "Сигнатура-максимум: паирбар A/B/Δ — герой экрана, холодный графит.",
  },
  {
    page: "showcase-r3a-type.html",
    title: "R3-A типолаба",
    note: "Макет «Стойки» + живой переключатель шрифтовых систем: Плекс / Терминал / Гротеск / Журнал.",
  },
] as const;

const app = document.getElementById("app");
if (!(app instanceof HTMLElement)) throw new Error("нет #app");

app.append(
  h("div", "index", {}, [
    h("p", "index-kicker", {}, ["Раунд 3 · дизайн-бриф #13"]),
    h("h1", "index-title", {}, ["Витрины: прибор, не приложение"]),
    h("p", "index-note", {}, [
      "Во всех витринах фиксированы: тёмный приборный цвет, маркеры и пик-таблица с Δ-колонкой, " +
        "маска с margin и вердиктом, дельта-полоса B − A. Варьируются: плотность рамки, " +
        "типографика, температура хрома.",
    ]),
    h(
      "ul",
      "index-list",
      {},
      VARIANTS.map((variant) =>
        h("li", "", {}, [
          h("a", "", { href: variant.page }, [variant.title]),
          h("span", "", {}, [variant.note]),
        ]),
      ),
    ),
  ]),
);
