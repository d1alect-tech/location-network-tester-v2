/** Задача 16 RED: статус-модель SA-вкладки — staged-реестр span/RBW
 * (только при idle: на ходу селекторы уходят конфигом saWorkspace),
 * маркеры «→ …», строка «применится при следующем запуске», pendingCount,
 * перевод baseline при переходе в running (маркеры гаснут), горячие
 * изменения при running стейджингом не помечаются, dispose отписывается. */

import { afterEach, describe, expect, it } from "vitest";
import type { LiveStatePayload, LiveWatchHandle, LiveWatchHandlers } from "../../api/types-live";
import { createLiveSeg } from "../../components/liveStrip/liveSeg";
import type { LiveStateSource } from "../../components/liveStrip/liveStrip";
import { el } from "../../components/primitives/dom";
import { mountSaStatus } from "./saStatus";

const IDLE: LiveStatePayload = { state: "idle", mode: "sim", busy_reason: null, trigger: null };
const RUNNING: LiveStatePayload = {
  state: "running",
  mode: "sim",
  busy_reason: null,
  trigger: null,
};

function input(dataAttr: string, value: string): HTMLInputElement {
  return el("input", {
    attrs: { type: "number", [dataAttr]: "", value },
  }) as HTMLInputElement;
}

function mountStatus(): {
  handle: ReturnType<typeof mountSaStatus>;
  emit: (state: LiveStatePayload) => void;
  pending: number[];
  span: HTMLElement;
  rbw: HTMLElement;
  low: HTMLInputElement;
  high: HTMLInputElement;
  change: (field: HTMLInputElement, value: string) => void;
  clickRbw: (value: string) => void;
} {
  const rbwSeg = createLiveSeg(
    {
      key: "rbw",
      kind: "ctl",
      aria: "Разрешающая полоса",
      options: [
        { value: "10", text: "10" },
        { value: "50", text: "50" },
        { value: "100", text: "100" },
      ],
      current: "50",
    },
    () => undefined,
  );
  const span = el("div", { attrs: { "data-ctl": "span" } }, [
    input("data-sa-band-low", "0"),
    input("data-sa-band-high", "4000000"),
  ]);
  const rbw = el("div", { attrs: { "data-ctl": "rbw" } }, [rbwSeg.root]);
  document.body.append(span, rbw);

  const watchers: LiveWatchHandlers[] = [];
  const closed = { count: 0 };
  const source: LiveStateSource = {
    watchFrames: (handlers: LiveWatchHandlers): LiveWatchHandle => {
      watchers.push(handlers);
      return {
        close: () => {
          closed.count += 1;
        },
      };
    },
  };
  const pending: number[] = [];
  const handle = mountSaStatus({
    live: source,
    hosts: { span, rbw },
    onPendingChange: (count) => pending.push(count),
  });
  return {
    handle,
    emit: (state) => {
      for (const watcher of [...watchers]) watcher.onState?.(state);
    },
    pending,
    span,
    rbw,
    low: span.querySelector("[data-sa-band-low]") as HTMLInputElement,
    high: span.querySelector("[data-sa-band-high]") as HTMLInputElement,
    change: (field, value) => {
      field.value = value;
      field.dispatchEvent(new Event("change", { bubbles: true }));
    },
    clickRbw: (value) => {
      const button = rbw.querySelector<HTMLButtonElement>(`[data-value="${value}"]`);
      if (button === null) throw new Error(`нет сегмента RBW ${value}`);
      button.click();
    },
  };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("saStatus: staged-реестр SA (задача 16)", () => {
  it("idle: смена RBW → маркер + строка + pendingCount; значение в слоте НЕ подменено", () => {
    const t = mountStatus();

    t.clickRbw("100");

    const mark = t.rbw.querySelector<HTMLElement>('[data-live-mark="rbw"]');
    expect(mark?.hidden).toBe(false);
    expect(mark?.textContent).toBe("→ 100 Гц");
    expect(t.handle.stagedLine.textContent).toContain("применится при следующем запуске");
    expect(t.handle.stagedLine.textContent).toContain("RBW 100 Гц");
    expect(t.handle.stagedLine.hasAttribute("hidden")).toBe(false);
    expect(t.pending.at(-1)).toBe(1);
  });

  it("idle: смена полосы → маркер «→ 0–2 МГц»; дефолт гасит отклонение", () => {
    const t = mountStatus();

    t.change(t.high, "2000000");

    const mark = t.span.querySelector<HTMLElement>('[data-live-mark="span"]');
    expect(mark?.hidden).toBe(false);
    expect(mark?.textContent).toBe("→ 0 Гц–2.0 МГц");
    expect(t.handle.stagedLine.textContent).toContain("Полоса 0 Гц–2.0 МГц");
    expect(t.pending.at(-1)).toBe(1);

    t.change(t.high, "4000000");
    expect(mark?.hidden).toBe(true);
    expect(t.handle.stagedLine.hasAttribute("hidden")).toBe(true);
    expect(t.pending.at(-1)).toBe(0);
  });

  it("мусорная полоса (конец ≤ начала) стейджингом не помечается", () => {
    const t = mountStatus();

    t.change(t.high, "0");

    const mark = t.span.querySelector<HTMLElement>('[data-live-mark="span"]');
    expect(mark?.hidden).toBe(true);
    expect(t.handle.stagedLine.hasAttribute("hidden")).toBe(true);
  });

  it("running: изменения горячие — стейджинга нет; переход в running гасит маркеры", () => {
    const t = mountStatus();
    t.clickRbw("100");
    t.change(t.high, "2000000");
    expect(t.pending.at(-1)).toBe(2);

    t.emit(RUNNING);
    const rbwMark = t.rbw.querySelector<HTMLElement>('[data-live-mark="rbw"]');
    const spanMark = t.span.querySelector<HTMLElement>('[data-live-mark="span"]');
    expect(rbwMark?.hidden).toBe(true);
    expect(spanMark?.hidden).toBe(true);
    expect(t.handle.stagedLine.hasAttribute("hidden")).toBe(true);
    expect(t.pending.at(-1)).toBe(0);

    // На ходу селекторы уходят конфигом — маркер не появляется.
    t.clickRbw("10");
    expect(t.rbw.querySelector<HTMLElement>('[data-live-mark="rbw"]')?.hidden).toBe(true);
    t.change(t.high, "3000000");
    expect(t.span.querySelector<HTMLElement>('[data-live-mark="span"]')?.hidden).toBe(true);
  });

  it("снапшот: после Run новая база — возврат к прежнему значению снова staged", () => {
    const t = mountStatus();
    const mark = t.rbw.querySelector<HTMLElement>('[data-live-mark="rbw"]');

    // До запуска: 100 — отклонение от дефолта 50.
    t.clickRbw("100");
    expect(mark?.hidden).toBe(false);

    // Run: staged-цели ушли в прибор — база переведена на 100, маркер погашен.
    t.emit(RUNNING);
    expect(mark?.hidden).toBe(true);
    t.emit({ ...IDLE });

    // 100 больше не отклонение…
    t.clickRbw("100");
    expect(mark?.hidden).toBe(true);
    // …а возврат к 50 — новое отклонение.
    t.clickRbw("50");
    expect(mark?.hidden).toBe(false);
    expect(mark?.textContent).toBe("→ 50 Гц");
  });

  it("dispose снимает слушателей хостов и закрывает подписку", () => {
    const t = mountStatus();
    t.handle.dispose();

    // События после dispose ничего не меняют.
    t.clickRbw("100");
    expect(t.rbw.querySelector<HTMLElement>('[data-live-mark="rbw"]')?.hidden).toBe(true);
    t.change(t.high, "2000000");
    expect(t.handle.stagedLine.hasAttribute("hidden")).toBe(true);
  });
});
