/** Задача 14 RED: статус-модель вкладки «Осциллограф» — staged-реестр
 * (В/дел/пробник/частота всегда; триггер только при idle), маркеры
 * «→ …», глобальная строка «применится при следующем запуске: …»,
 * pendingCount, индикатор [data-trig-state] «в приборе»/«при
 * запуске», перевод baseline при переходе в running (маркеры гаснут),
 * dispose отписывается. */

import { afterEach, describe, expect, it } from "vitest";
import type { LiveStatePayload, LiveWatchHandle, LiveWatchHandlers } from "../../api/types-live";
import { createLiveChip } from "../../components/liveStrip/liveChip";
import { createLiveSeg } from "../../components/liveStrip/liveSeg";
import type { LiveStateSource } from "../../components/liveStrip/liveStrip";
import { el } from "../../components/primitives/dom";
import { mountScopeStatus } from "./scopeStatus";

function button(root: ParentNode, selector: string): HTMLButtonElement {
  const node = root.querySelector(selector);
  if (!(node instanceof HTMLButtonElement)) throw new Error(`нет кнопки ${selector}`);
  return node;
}

const RUNNING: LiveStatePayload = {
  state: "running",
  mode: "sim",
  busy_reason: null,
  trigger: null,
};

function trigHost(attr: string, values: readonly string[], texts: readonly string[]): HTMLElement {
  const host = el("div", { className: "lnt-live-ctl" });
  const group = el("div", { className: "lnt-scope-seg", attrs: { role: "group" } });
  values.forEach((value, index) => {
    group.append(
      el("button", {
        text: texts[index],
        attrs: { type: "button", "aria-pressed": String(index === 0), [attr]: value },
      }),
    );
  });
  host.append(group);
  return host;
}

function mountStatus(): {
  status: ReturnType<typeof mountScopeStatus>;
  emit: (state: LiveStatePayload) => void;
  closed: { count: number };
  pending: number[];
  vdiv: HTMLElement;
  probe: HTMLElement;
  rate: HTMLElement;
  trigMode: HTMLElement;
  click: (host: HTMLElement, selector: string) => void;
} {
  const vdivSeg = createLiveSeg(
    {
      key: "vdiv",
      kind: "ctl",
      aria: "Вольт на деление",
      options: [
        { value: "5", text: "5" },
        { value: "1", text: "1" },
      ],
      current: "1",
    },
    () => undefined,
  );
  const probeSeg = createLiveSeg(
    {
      key: "probe",
      kind: "ctl",
      aria: "Пробник CH1",
      options: [
        { value: "1", text: "×1" },
        { value: "10", text: "×10" },
      ],
      current: "1",
    },
    () => undefined,
  );
  const chip = createLiveChip(
    {
      key: "rate",
      aria: "Частота дискретизации",
      options: [
        { value: "2000000", text: "2 МГц" },
        { value: "8000000", text: "8 МГц" },
      ],
      current: "8000000",
      menuTitle: "Частота · применяется при запуске",
    },
    () => undefined,
  );
  const vdiv = el("div", { className: "lnt-live-ctl", attrs: { "data-ctl": "vdiv" } }, [
    vdivSeg.root,
  ]);
  const probe = el("div", { className: "lnt-live-ctl", attrs: { "data-ctl": "probe" } }, [
    probeSeg.root,
  ]);
  const rate = el("div", { className: "lnt-live-ctl", attrs: { "data-ctl": "rate" } }, [chip.root]);
  const trigMode = trigHost("data-trigger-mode", ["auto", "normal"], ["Авто", "Норм"]);
  const trigSource = trigHost("data-trigger-source", ["ch1", "ch2"], ["CH1", "CH2"]);
  const trigSlope = trigHost("data-trigger-slope", ["rising", "falling"], ["Подъём", "Спад"]);
  document.body.append(vdiv, probe, rate, trigMode, trigSource, trigSlope);

  const watchers: LiveWatchHandlers[] = [];
  const closed = { count: 0 };
  // Фейк моделирует настоящий EventSource: после close() доставка мертва.
  const stream = { closed: false };
  const source: LiveStateSource = {
    watchFrames: (handlers: LiveWatchHandlers): LiveWatchHandle => {
      watchers.push(handlers);
      return {
        close: () => {
          stream.closed = true;
          closed.count += 1;
        },
      };
    },
  };
  const emit = (state: LiveStatePayload): void => {
    if (stream.closed) return;
    for (const watcher of watchers) watcher.onState?.(state);
  };
  const pending: number[] = [];
  const status = mountScopeStatus({
    live: source,
    hosts: { vdiv, probe, rate, trigMode, trigSource, trigSlope },
    onPendingChange: (count) => pending.push(count),
  });
  // Тесты дергают доставку через эмиттер: доставка уважает close().
  document.body.append(status.stagedLine, status.trigState);
  return {
    status,
    emit,
    closed,
    pending,
    vdiv,
    probe,
    rate,
    trigMode,
    click: (host, selector) => host.querySelector<HTMLButtonElement>(selector)?.click(),
  };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("mountScopeStatus: staged-реестр", () => {
  it("изменил В/дел → маркер, строка и pendingCount; возврат к базлайну гасит", () => {
    const { vdiv, pending } = mountStatus();
    const mark = vdiv.querySelector<HTMLElement>('[data-live-mark="vdiv"]');
    const line = document.querySelector<HTMLElement>("[data-staged-line]");
    expect(mark?.hidden).toBe(true);

    button(vdiv, '[data-value="5"]').click();
    expect(mark?.hidden).toBe(false);
    expect(mark?.textContent).toBe("→ 5 В/дел");
    expect(line?.textContent).toContain("применится при следующем запуске");
    expect(line?.textContent).toContain("В/дел 5 В/дел");
    expect(pending.at(-1)).toBe(1);

    // Возврат к применённому (1) — стейджинг снят честно.
    button(vdiv, '[data-value="1"]').click();
    expect(mark?.hidden).toBe(true);
    expect(pending.at(-1)).toBe(0);
  });

  it("пробник и частота стейджируются; слот чипа остаётся применённым значением", () => {
    const { probe, rate } = mountStatus();
    button(probe, '[data-value="10"]').click();
    expect(probe.querySelector<HTMLElement>('[data-live-mark="probe"]')?.textContent).toBe("→ ×10");
    button(rate, ".lnt-live-chip-btn").click();
    button(rate, "[role='option'][data-value='2000000']").click();
    expect(rate.querySelector<HTMLElement>('[data-live-mark="rate"]')?.textContent).toBe("→ 2 МГц");
    // Негативный: staged-число НЕ в элементе текущего значения.
    expect(rate.querySelector("[data-slot='rate']")?.textContent).toBe("8 МГц");
  });

  it("Run (переход в running): маркеры гаснут, baseline принимает staged, чип применён", () => {
    const { emit, vdiv, rate, pending } = mountStatus();
    button(vdiv, '[data-value="5"]').click();
    button(rate, ".lnt-live-chip-btn").click();
    button(rate, "[role='option'][data-value='2000000']").click();
    expect(pending.at(-1)).toBe(2);

    emit(RUNNING);
    expect(vdiv.querySelector<HTMLElement>('[data-live-mark="vdiv"]')?.hidden).toBe(true);
    expect(rate.querySelector<HTMLElement>('[data-live-mark="rate"]')?.hidden).toBe(true);
    expect(pending.at(-1)).toBe(0);
    expect(rate.querySelector("[data-slot='rate']")?.textContent).toBe("2 МГц");

    // После применения 5 В/дел повторный клик не стейджирует.
    button(vdiv, '[data-value="5"]').click();
    expect(pending.at(-1)).toBe(0);
  });

  it("триггер: при idle стейджируется, при running — горячий (без стейджинга)", () => {
    const { trigMode, emit, pending } = mountStatus();
    button(trigMode, '[data-trigger-mode="normal"]').click();
    expect(trigMode.querySelector<HTMLElement>('[data-live-mark="trigmode"]')?.textContent).toBe(
      "→ Норм",
    );
    expect(pending.at(-1)).toBe(1);

    // Горячий контур: на ходу клики триггера не помечаются.
    emit(RUNNING);
    expect(document.querySelector<HTMLElement>("[data-trig-state]")?.textContent).toBe("в приборе");
    button(trigMode, '[data-trigger-mode="auto"]').click();
    expect(pending.at(-1)).toBe(0);
  });

  it("dispose отписывается: слушатели хостов сняты, live-подписка закрыта", () => {
    const { status, emit, closed, vdiv, pending } = mountStatus();
    const before = pending.length;
    status.dispose();
    expect(closed.count).toBe(1);
    button(vdiv, '[data-value="1"]').click();
    expect(pending.length).toBe(before);
    emit(RUNNING);
    expect(document.querySelector<HTMLElement>("[data-trig-state]")?.textContent).toBe(
      "при запуске",
    );
  });
});
