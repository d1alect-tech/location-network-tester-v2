/** Задача 14 RED: компактная сегмент-группа liveSeg — нативные кнопки
 * aria-pressed, клик по нажатой — no-op, стрелки ←/→ двигают фокус И
 * активируют соседний сегмент (та же дорожка, что и клик), программный
 * pick для сброса/автосета. */

import { describe, expect, it } from "vitest";
import { createLiveSeg } from "./liveSeg";

function button(root: ParentNode, selector: string): HTMLButtonElement {
  const node = root.querySelector(selector);
  if (!(node instanceof HTMLButtonElement)) throw new Error(`нет кнопки ${selector}`);
  return node;
}

const OPTIONS = [
  { value: "5", text: "5" },
  { value: "1", text: "1" },
  { value: "0.5", text: "0.5" },
];

function mountSeg(): { seg: ReturnType<typeof createLiveSeg>; picks: string[] } {
  const picks: string[] = [];
  const seg = createLiveSeg(
    {
      key: "vdiv",
      kind: "ctl",
      aria: "Вольт на деление",
      options: OPTIONS,
      current: "5",
      groupAttrs: { id: "lnt-scope-vdiv" },
      groupClassName: "lnt-scope-seg",
    },
    (value) => picks.push(value),
  );
  document.body.append(seg.root);
  return { seg, picks };
}

describe("createLiveSeg", () => {
  it("строит группу role=group с кнопками data-value и aria-pressed по текущему", () => {
    const { seg } = mountSeg();
    expect(seg.root.id).toBe("lnt-scope-vdiv");
    expect(seg.root.classList.contains("lnt-scope-seg")).toBe(true);
    expect(seg.root.getAttribute("role")).toBe("group");
    const buttons = [...seg.root.querySelectorAll("button[data-value]")];
    expect(buttons.map((b) => b.textContent)).toEqual(["5", "1", "0.5"]);
    expect(buttons[0]?.getAttribute("aria-pressed")).toBe("true");
    expect(buttons[1]?.getAttribute("aria-pressed")).toBe("false");
    expect(seg.selection()).toBe("5");
  });

  it("клик по свободному сегменту активирует выбор; повторный клик по нажатому — no-op", () => {
    const { seg, picks } = mountSeg();
    button(seg.root, '[data-value="1"]').click();
    expect(picks).toEqual(["1"]);
    expect(seg.selection()).toBe("1");
    expect(seg.root.querySelector('[data-value="1"]')?.getAttribute("aria-pressed")).toBe("true");
    // Уже нажатый сегмент не дублирует выбор.
    button(seg.root, '[data-value="1"]').click();
    expect(picks).toEqual(["1"]);
  });

  it("стрелка вправо двигает фокус и активирует следующий сегмент", () => {
    const { seg, picks } = mountSeg();
    const first = seg.root.querySelector<HTMLButtonElement>('[data-value="5"]');
    first?.focus();
    first?.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(picks).toEqual(["1"]);
    expect(document.activeElement).toBe(seg.root.querySelector('[data-value="1"]'));
    // Крайний сегмент: переход зациклен (последний → первый).
    document.activeElement?.dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }),
    );
    expect(picks).toEqual(["1", "0.5"]);
  });

  it("paint переводит нажатое состояние без вызова onPick (истина сервиса)", () => {
    const { seg, picks } = mountSeg();
    seg.paint("0.5");
    expect(picks).toEqual([]);
    expect(seg.selection()).toBe("0.5");
    expect(seg.root.querySelector('[data-value="0.5"]')?.getAttribute("aria-pressed")).toBe("true");
  });

  it("pick — программная активация через ту же дорожку (сброс/автосет)", () => {
    const { seg, picks } = mountSeg();
    seg.pick("1");
    expect(picks).toEqual(["1"]);
    expect(seg.selection()).toBe("1");
  });
});
