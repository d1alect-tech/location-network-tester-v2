/** Кит раунда 3: приборная рамка по брифу #13 — channel-bar, статус-бар,
 *  чипы пары A/B, дельта-бейджи, пик-таблица с Δ-колонкой, вердикты маски. */
import { METRICS } from "../showcase-redesign/data";
import { LIMIT, MARKERS, PAIR_PEAKS, PAIR_SUMMARY, VERDICTS, fmtDb, fmtHz } from "./data";

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  cls = "",
  attrs: Readonly<Record<string, string>> = {},
  kids: readonly (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  for (const [key, val] of Object.entries(attrs)) node.setAttribute(key, val);
  for (const kid of kids) node.append(kid);
  return node;
}

function num(text: string, unit?: string): HTMLElement {
  const span = h("span", "t-num", {}, [text]);
  if (unit !== undefined) span.append(h("span", "t-unit", {}, [unit]));
  return span;
}

function barField(label: string, value: HTMLElement): HTMLElement {
  return h("span", "bar-field", {}, [h("span", "t-tag", {}, [label]), value]);
}

/** Channel-bar: ключевые параметры измерения всегда на виду (FSW/Keysight). */
export function buildChannelBar(withPair = true): HTMLElement {
  const rbw = (METRICS.resolutionHz * 1.5).toLocaleString("ru-RU", { maximumFractionDigits: 1 });
  const bar = h("div", "channelbar", { "data-r3": "channelbar", role: "group" }, [
    h("span", "bar-brand", {}, ["LNT"]),
    barField("Полоса", num("3–45", "кГц")),
    barField("RBW", num(rbw, "Гц")),
    barField("Окно", h("span", "t-num", {}, ["Ханна"])),
    barField("Детектор", h("span", "t-num", {}, ["Average"])),
    barField("Сегментов", num(String(METRICS.cyclesAnalyzed))),
    h("span", "bar-spacer", {}),
  ]);
  if (withPair) bar.append(buildPairChips());
  return bar;
}

/** Чипы пары: A циан ●, B янтарь ■ — семантика DESIGN.md. */
export function buildPairChips(): HTMLElement {
  return h("span", "pair-chips", { "data-r3": "pair" }, [
    h("span", "chip chip-a", {}, [
      h("span", "swatch", { "aria-hidden": "true" }, ["●"]),
      `A ${PAIR_SUMMARY.a.label}`,
    ]),
    h("span", "chip chip-b", {}, [
      h("span", "swatch", { "aria-hidden": "true" }, ["■"]),
      `B ${PAIR_SUMMARY.b.label}`,
    ]),
  ]);
}

/** Дельта-бейджи пары: сигнатура интерфейса — Δ первокласснее одиночного трейса. */
export function buildDeltaBadges(size: "line" | "hero"): HTMLElement {
  const cls = size === "hero" ? "delta-badges delta-badges--hero" : "delta-badges";
  const numCls = size === "hero" ? "t-num-big" : "t-num";
  return h("div", cls, { "data-r3": "delta" }, [
    h("span", "delta-badge", {}, [
      h("span", "t-tag", {}, [`Δ пик ${fmtHz(PAIR_SUMMARY.deltaPeakAtHz)}`]),
      h("span", numCls, {}, [
        fmtDb(PAIR_SUMMARY.deltaPeakDb, true),
        h("span", "t-unit", {}, ["дБ"]),
      ]),
    ]),
    h("span", "delta-badge", {}, [
      h("span", "t-tag", {}, [
        `Δ полоса ${fmtHz(PAIR_SUMMARY.bandLowHz)}–${fmtHz(PAIR_SUMMARY.bandHighHz)}`,
      ]),
      h("span", numCls, {}, [
        fmtDb(PAIR_SUMMARY.deltaBandDb, true),
        h("span", "t-unit", {}, ["дБ"]),
      ]),
    ]),
  ]);
}

/** Маркерные чипы в стиле SDRangel: M1 слева, Δ справа. */
export function buildMarkerChips(): HTMLElement {
  return h("div", "marker-chips", { "data-r3": "markers" }, [
    h("span", "marker-chip marker-m1", {}, [
      h("span", "t-tag", {}, ["M1"]),
      num(fmtHz(MARKERS.m1.frequencyHz)),
      num(fmtDb(MARKERS.m1.levelDb), "дБ"),
    ]),
    h("span", "marker-chip marker-delta", {}, [
      h("span", "t-tag", {}, ["M2−M1"]),
      num(`+${fmtHz(MARKERS.m2DeltaHz)}`),
      num(fmtDb(MARKERS.m2DeltaDb, true), "дБ"),
    ]),
  ]);
}

/** Пик-таблица с Δ-колонкой (Spike + бриф: дельта — колонка первого ряда). */
export function buildPeakTable(): HTMLElement {
  const head = h("tr", "", {}, [
    h("th", "", { scope: "col" }, ["Частота"]),
    h("th", "num", { scope: "col" }, ["A, дБ"]),
    h("th", "num", { scope: "col" }, ["B, дБ"]),
    h("th", "num col-delta", { scope: "col" }, ["Δ, дБ"]),
    h("th", "num", { scope: "col" }, ["Q"]),
  ]);
  const rows = PAIR_PEAKS.map((row) =>
    h("tr", "", {}, [
      h("td", "", {}, [num(fmtHz(row.frequencyHz))]),
      h("td", "num trace-a", {}, [num(fmtDb(row.aDb))]),
      h("td", "num trace-b", {}, [num(fmtDb(row.bDb))]),
      h("td", "num col-delta", {}, [num(fmtDb(row.deltaDb, true))]),
      h("td", "num", {}, [num(row.q.toLocaleString("ru-RU", { maximumFractionDigits: 2 }))]),
    ]),
  );
  return h("table", "peak-table", { "data-r3": "peaks" }, [
    h("caption", "t-tag", {}, ["Пики спектра · дБ отн. 1 В²/Гц"]),
    h("thead", "", {}, [head]),
    h("tbody", "", {}, rows),
  ]);
}

/** Вердикты маски: Pass/Fail в углу, детали — по-русски (Keysight). */
export function buildVerdicts(): HTMLElement {
  const badges = VERDICTS.map((verdict) =>
    h(
      "span",
      `verdict ${verdict.pass ? "verdict-pass" : "verdict-fail"}`,
      { "data-r3": `verdict-${verdict.session.toLowerCase()}` },
      [
        h("span", "t-tag", {}, [`${verdict.session} · ${LIMIT.title}`]),
        h("span", "t-bar", {}, [verdict.pass ? "ПРОХОДИТ" : "НЕ ПРОХОДИТ"]),
        h("span", "t-num verdict-detail", {}, [verdict.detail]),
      ],
    ),
  );
  return h("div", "verdicts", {}, badges);
}

/** Статус-бар: устройство, корень, ENBW-репорт (низ рамки). */
export function buildStatusBar(): HTMLElement {
  return h("footer", "statusbar", { "data-r3": "statusbar" }, [
    h("span", "statusbar-item", {}, [
      h("span", "dot dot-ok", { "aria-hidden": "true" }),
      "Hantek 6022BE · готов",
    ]),
    h("span", "statusbar-item t-num", {}, ["Корень: C:\\lnt-sessions"]),
    h("span", "bar-spacer", {}),
    h("span", "statusbar-item t-num", {}, ["RBW 146,5 Гц · ENBW 1,5 бина · дБ отн. 1 В²/Гц"]),
  ]);
}

/** Группа контролов правой стойки (вариант A, softkey-колонка FSW). */
export function buildControlGroup(title: string, actions: readonly string[]): HTMLElement {
  return h("section", "ctl-group", {}, [
    h("h2", "t-tag ctl-title", {}, [title]),
    ...actions.map((label) => h("button", "ctl-btn t-bar", { type: "button" }, [label])),
  ]);
}

/** Док-панель верстака (вариант B, Spike): заголовок со «схваткой». */
export function buildDockPanel(title: string, body: readonly HTMLElement[]): HTMLElement {
  return h("section", "dock-panel", {}, [
    h("header", "dock-head", {}, [
      h("span", "dock-grip", { "aria-hidden": "true" }, ["⠿"]),
      h("h2", "t-tag", {}, [title]),
    ]),
    h("div", "dock-body", {}, body),
  ]);
}
