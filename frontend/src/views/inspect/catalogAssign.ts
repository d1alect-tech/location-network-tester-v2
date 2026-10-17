import type { SessionHealth } from "../../api/types";
import "./catalogAssign.css";
import { el } from "../../components/primitives/dom";
import type { PairSlot } from "./pairState";

/** M1 (план inspect-v1-selection-ux, todo 4): видимые кнопки назначения
 * «А» (база) / «Б» (сравнение) на каждой строке каталога. Инвариант M1:
 * испускается ВСЕГДА loadKey (dir-name для дублей), никогда сырой id.
 * Занятый строкой слот зеркалится aria-pressed и не испускается —
 * move и освобождение соседа решает pairState.assignSlot. */

export interface AssignRow {
  readonly id: string;
  readonly name: string | null;
  readonly loadKey: string;
  readonly health: SessionHealth;
}

export type AssignListener = (slot: PairSlot, loadKey: string) => void;

export interface AssignButtonsHandle {
  /** Контейнер кнопок: рендер строки кладёт его в roleCell. */
  readonly el: HTMLElement;
  /** Writable-коллбэк: владелец строки ведёт его к pair.assignSlot. */
  onAssign: AssignListener;
  /** Кладётся в row-keydown: event.code KeyA/KeyB — физические клавиши,
   * layout-independent; ввод в текстовых полях игнорируется. */
  readonly handleKeydown: (event: KeyboardEvent) => void;
}

interface SlotMeta {
  readonly aria: string;
  readonly letter: string;
}

const SLOT_META: Readonly<Record<PairSlot, SlotMeta>> = {
  a: { aria: "Сделать базой", letter: "А" },
  b: { aria: "Сделать сравнением", letter: "Б" },
};

const SLOTS: readonly PairSlot[] = ["a", "b"];

function renderButton(slot: PairSlot, row: AssignRow, pressed: boolean): HTMLButtonElement {
  const meta = SLOT_META[slot];
  return el("button", {
    className: "cat-assign",
    text: meta.letter,
    attrs: {
      type: "button",
      "data-assign": slot,
      tabindex: "-1",
      "aria-label": meta.aria,
      title: row.loadKey,
      "aria-pressed": pressed ? "true" : "false",
    },
  });
}

function isTextField(target: EventTarget | null): boolean {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
}

export function assignButtons(row: AssignRow, inPair: PairSlot | null): AssignButtonsHandle {
  const buttons: Record<PairSlot, HTMLButtonElement> = {
    a: renderButton("a", row, inPair === "a"),
    b: renderButton("b", row, inPair === "b"),
  };
  const handle: AssignButtonsHandle = {
    el: el("span", { className: "cat-assign-wrap" }, [buttons.a, buttons.b]),
    onAssign: () => {},
    handleKeydown(event) {
      if (event.code !== "KeyA" && event.code !== "KeyB") return;
      if (isTextField(event.target)) return;
      emit(event.code === "KeyA" ? "a" : "b");
    },
  };

  function emit(slot: PairSlot): void {
    if (inPair === slot) return;
    handle.onAssign(slot, row.loadKey);
  }

  for (const slot of SLOTS) {
    buttons[slot].addEventListener("click", (event) => {
      event.stopPropagation();
      emit(slot);
    });
  }
  return handle;
}
