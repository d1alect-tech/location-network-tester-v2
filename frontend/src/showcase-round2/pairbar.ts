/** Полоса пары А/Б (V6): интерфейс называет обе сессии, которые нарисованы на графике.
 *  До этого варианта трассы «Сессия А» и «Сессия Б» не были ни к чему привязаны. */
import type { ShowcaseSession } from "../showcase-redesign/data";
import { h } from "./kit";

function buildSlot(role: string, slot: "a" | "b", session: ShowcaseSession): HTMLElement {
  return h("div", "pair-slot", { "data-pair": slot }, [
    h("span", "pair-role", {}, [role]),
    h("span", `pair-glyph glyph-${session.health}`, { "aria-hidden": "true" }, [session.glyph]),
    h("span", "pair-name", { title: session.label }, [session.label]),
    h("span", "pair-meta", {}, [`${session.typeLabel} · ${session.date}`]),
  ]);
}

export function buildPairbar(base: ShowcaseSession, compare: ShowcaseSession): HTMLElement {
  const path = compare.storagePath ?? compare.id;
  return h("div", "pairbar", {}, [
    buildSlot("База", "a", base),
    h("span", "pair-delta", { "aria-hidden": "true" }, ["Δ"]),
    buildSlot("Сравнение", "b", compare),
    h("span", "pair-path", { title: path }, [path]),
    h("button", "btn-quiet", { type: "button", "data-pair-swap": "" }, ["Поменять местами"]),
  ]);
}
