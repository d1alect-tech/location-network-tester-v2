/** Наполнение панели «Риппл / шум»: тексты и data-value обновляются в
 * фиксированных слотах. Состояния idle/loading/ready/error сменяются
 * атрибутами корня, а не пересборкой DOM. */

import { el } from "../../../components/primitives/dom";
import type { RippleSpectrumMode } from "./rippleChart";
import { RIPPLE_DASH } from "./rippleModel";
import type { RippleBandOption, RippleViewModel } from "./rippleModel";
import { createRipplePanelDom } from "./ripplePanelDom";

export type RipplePanelState = "idle" | "loading" | "ready" | "error";

export type RipplePanelView = {
  readonly root: HTMLElement;
  readonly chartHost: HTMLElement;
  readonly message: HTMLElement;
  readonly bandSelect: HTMLSelectElement;
  readonly modeButtons: Readonly<Record<RippleSpectrumMode, HTMLButtonElement>>;
  begin(session: string): void;
  clear(session: string): void;
  paint(view: RippleViewModel): void;
  fail(kind: string, reason: string, message: string): void;
  setBands(bands: readonly RippleBandOption[], selected: number): void;
  setMode(mode: RippleSpectrumMode): void;
  chartEmpty(text: string): void;
  chartReady(): void;
};

export function createRipplePanelView(): RipplePanelView {
  const dom = createRipplePanelDom();
  const {
    root,
    chartHost,
    message,
    bandSelect,
    psd,
    asd,
    sessionEl,
    chips,
    cards,
    intervalSlots,
    intervalCount,
    qc,
    spectrumMeta,
    baselineStatus,
    baselineRms,
    baselineVpp,
    baselineSession,
    chartEmpty,
  } = dom;

  function paintCards(view: RippleViewModel): void {
    for (const metric of view.metrics) {
      const target = cards.get(metric.key);
      if (target === undefined) continue;
      target.root.dataset.value = metric.raw === null ? "null" : String(metric.raw);
      target.root.dataset.available = String(metric.raw !== null);
      target.root.title = metric.reason ?? "";
      target.value.textContent = metric.text;
      target.note.textContent = metric.note;
    }
  }

  function paintIntervals(view: RippleViewModel): void {
    for (const [index, slot] of intervalSlots.entries()) {
      const data = view.intervals[index];
      if (data === undefined) continue;
      slot.dataset.value = data.raw === null ? "null" : String(data.raw);
      slot.textContent = data.text;
      slot.title = data.reason ?? "";
      slot.dataset.complete = String(data.complete);
    }
    intervalCount.textContent = view.intervalCountText;
    intervalCount.title = view.intervalCount === 0 ? "" : `${view.intervalCount} окон`;
  }

  function paintBaseline(view: RippleViewModel): void {
    const base = view.baseline;
    baselineStatus.textContent =
      base.status === "none"
        ? "не приложен"
        : base.status === "available"
          ? "сравнение доступно"
          : "сравнение недоступно";
    baselineRms.textContent = base.rmsText;
    baselineRms.dataset.value = base.rmsRaw === null ? "null" : String(base.rmsRaw);
    baselineVpp.textContent = base.vppText;
    baselineVpp.dataset.value = base.vppRaw === null ? "null" : String(base.vppRaw);
    baselineSession.textContent = base.session === null ? "" : `· ${base.session}`;
    root.querySelector<HTMLElement>("[data-ripple-baseline]")?.setAttribute("title", base.text);
  }

  function resetValues(): void {
    for (const target of cards.values()) {
      target.root.dataset.value = "null";
      target.root.dataset.available = "false";
      target.root.title = "";
      target.value.textContent = RIPPLE_DASH;
      target.note.textContent = "";
    }
    for (const slot of intervalSlots) {
      slot.dataset.value = "null";
      slot.dataset.complete = "false";
      slot.title = "";
      slot.textContent = "—";
    }
    intervalCount.textContent = "";
    qc.textContent = "";
    qc.title = "";
    spectrumMeta.textContent = "";
    spectrumMeta.title = "";
    baselineStatus.textContent = "";
    baselineRms.textContent = RIPPLE_DASH;
    baselineRms.dataset.value = "null";
    baselineVpp.textContent = RIPPLE_DASH;
    baselineVpp.dataset.value = "null";
    baselineSession.textContent = "";
    root.querySelector<HTMLElement>("[data-ripple-baseline]")?.setAttribute("title", "");
  }

  return {
    root,
    chartHost,
    message,
    bandSelect,
    modeButtons: { psd, asd },
    begin(session) {
      root.dataset.state = "loading";
      root.dataset.sessionId = session;
      root.dataset.availability = "none";
      root.dataset.error = "";
      root.dataset.reason = "";
      sessionEl.textContent = session;
      sessionEl.title = session;
      resetValues();
      message.textContent = "Загрузка ripple-артефакта…";
      message.dataset.tone = "info";
      chartEmpty.textContent = "загрузка сохранённого спектра…";
      chartEmpty.hidden = false;
      chartHost.hidden = true;
    },
    clear(session) {
      root.dataset.state = "idle";
      root.dataset.sessionId = session;
      root.dataset.availability = "none";
      root.dataset.error = "";
      root.dataset.reason = "";
      sessionEl.textContent = session;
      sessionEl.title = session;
      resetValues();
      message.textContent = "";
      message.dataset.tone = "";
      chartEmpty.textContent = "сессия не выбрана";
      chartEmpty.hidden = false;
      chartHost.hidden = true;
      for (const item of chips) {
        item.textContent = "—";
        item.title = "";
      }
    },
    paint(view) {
      root.dataset.state = "ready";
      root.dataset.availability = view.availability;
      root.dataset.error = "";
      root.dataset.reason = "";
      message.textContent = "";
      message.dataset.tone = "";
      for (const [index, item] of chips.entries()) {
        const text = view.chips[index] ?? "—";
        item.textContent = text;
        item.title = text;
      }
      paintCards(view);
      paintIntervals(view);
      qc.textContent = view.qcText;
      qc.title = view.qcText;
      spectrumMeta.textContent = view.spectrumMeta;
      spectrumMeta.title = view.spectrumMeta;
      paintBaseline(view);
      if (view.spectrumAvailable) {
        chartEmpty.hidden = true;
        chartHost.hidden = false;
      } else {
        chartEmpty.textContent = view.spectrumText;
        chartEmpty.hidden = false;
        chartHost.hidden = true;
      }
    },
    fail(kind, reason, text) {
      root.dataset.state = "error";
      root.dataset.error = kind;
      root.dataset.reason = reason;
      root.dataset.availability = "none";
      resetValues();
      message.textContent = text;
      message.dataset.tone = "error";
      chartEmpty.textContent = "спектр не построен";
      chartEmpty.hidden = false;
      chartHost.hidden = true;
      for (const item of chips) {
        item.textContent = "—";
        item.title = "";
      }
    },
    setBands(bands, selected) {
      bandSelect.replaceChildren(
        ...bands.map((band) => el("option", { text: band.label, attrs: { value: band.id } })),
      );
      bandSelect.hidden = bands.length <= 1;
      const active = bands[selected]?.id;
      if (active !== undefined) bandSelect.value = active;
    },
    setMode(mode) {
      psd.setAttribute("aria-pressed", String(mode === "psd"));
      asd.setAttribute("aria-pressed", String(mode === "asd"));
    },
    chartEmpty(text) {
      chartEmpty.textContent = text;
      chartEmpty.hidden = false;
      chartHost.hidden = true;
    },
    chartReady() {
      chartEmpty.hidden = true;
      chartHost.hidden = false;
    },
  };
}
