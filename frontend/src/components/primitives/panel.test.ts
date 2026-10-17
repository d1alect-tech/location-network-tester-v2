/** Контракт примитива рамки (todo 2, ui-refactor-2, RED→GREEN): panel.ts
 * строит DOM канонической рамки из primitives/panel.css — те же классы, что
 * эмитят живые виды (section.panel > div.panel-hd > *.panel-title + div.panel-bd).
 * Плотность/геометрия видов — в scoped CSS видов, не здесь. */

import { describe, expect, it } from "vitest";
import { el } from "./dom";
import { panel, panelBd, panelHd, panelTitle } from "./panel";

describe("primitives/panel: структура канонической рамки", () => {
  it("panel() — section.panel; доп. класс и атрибуты сохраняются", () => {
    const node = panel({ className: "capture-livegram", attrs: { "aria-label": "Спектрограмма" } });
    expect(node.tagName).toBe("SECTION");
    expect(node.classList.contains("panel")).toBe(true);
    expect(node.classList.contains("capture-livegram")).toBe(true);
    expect(node.getAttribute("aria-label")).toBe("Спектрограмма");
  });

  it("panelHd/panelTitle/panelBd — канонические классы, заголовок с текстом", () => {
    const root = panel({}, [panelHd({}, [panelTitle("Спектрограмма")]), panelBd()]);
    expect(root.querySelector(".panel-hd")).not.toBeNull();
    const title = root.querySelector(".panel-hd > .panel-title");
    expect(title).not.toBeNull();
    expect(title?.textContent).toBe("Спектрограмма");
    expect(root.querySelector(".panel-bd")).not.toBeNull();
  });

  it("panelTitle — заголовок h2 (идиома живых панелей capture/reports)", () => {
    expect(panelTitle("Заголовок").tagName).toBe("H2");
  });

  it("panelBd bare — канонический модификатор .panel-bd.is-bare", () => {
    const bare = panelBd({ bare: true });
    expect(bare.classList.contains("panel-bd")).toBe(true);
    expect(bare.classList.contains("is-bare")).toBe(true);
    expect(panelBd().classList.contains("is-bare")).toBe(false);
  });

  it("рамка совмещается с живым содержимым: hd-хвосты и дети bd", () => {
    const root = panel({}, [
      panelHd({}, [panelTitle("Шапка"), el("span", { text: "хвост" })]),
      panelBd({}, [el("p", { text: "содержимое" })]),
    ]);
    expect(root.querySelector(".panel-hd span")?.textContent).toBe("хвост");
    expect(root.querySelector(".panel-bd p")?.textContent).toBe("содержимое");
  });
});
