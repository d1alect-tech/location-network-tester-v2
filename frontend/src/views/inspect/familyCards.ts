/** Карточки семейств characterization-v1: сетка, сгруппированная по статусу.
 *
 * Продуктовая посадка выигравшего варианта «Карточки» прототипа
 * `frontend/prototypes/extended-run.html`: группы со счётчиками, карточка на
 * семейство (имя, статус, RU-причина, поддержка, полоса, окно), вход каскадом
 * только при появлении результатов. Токены — только v6 (`extendedRun.css`);
 * отсутствующее поле — тихое тире, полоса поддержки не рисуется без счётчиков.
 */

import { el } from "../../components/primitives/dom";
import type { FamilySummary } from "./characterizationFamily";
import type { CharacterizationSummary } from "./extendedRun";
import { familyNameRu } from "./familyNames";
import { reasonCodeRu } from "./reasonCodes";

/** Порядок групп фиксирован; прочие статусы встают следом в порядке встречи. */
export const FAMILY_STATUS_GROUPS: readonly { readonly key: string; readonly title: string }[] = [
  { key: "available", title: "Доступно" },
  { key: "partial", title: "Частично" },
  { key: "unavailable", title: "Недоступно" },
];

const DASH = "—";
const EMPTY_GROUP = "нет семейств в этой группе";
const NO_CODES = "Причины не сообщены в бандле.";
const NO_REASON = "Причина не сообщена в бандле.";
const FULL_RESULT = "Результат полный, QC пройден.";
const SUMMARY_TITLE = "Сводка расширенного анализа";
/** Каскад входа не длиннее 240 мс: после тринадцатой карточки задержки нет. */
const ENTER_LAST = 13;

export type FamilyCardsOptions = {
  readonly session?: string | null;
};

type Bucket = { readonly key: string; readonly title: string; readonly items: FamilySummary[] };

function stagger(index: number): string {
  return String(Math.min(index, ENTER_LAST));
}

function statusTitle(status: string): string {
  return FAMILY_STATUS_GROUPS.find((group) => group.key === status)?.title ?? status;
}

function pillTone(status: string): string {
  if (status === "available") return "ok";
  if (status === "partial") return "warn";
  return "dim";
}

function hz(value: number | null): string {
  return value === null ? DASH : value.toFixed(1);
}

function bandText(family: FamilySummary): string {
  const { lowHz, highHz } = family.band;
  if (lowHz === null && highHz === null) return DASH;
  return `${hz(lowHz)}–${hz(highHz)} Гц`;
}

function windowText(family: FamilySummary): string {
  return family.window.durationS === null ? DASH : `${family.window.durationS.toFixed(1)} с`;
}

function supportText(family: FamilySummary): string {
  const { storedCount, missingCount } = family.support;
  if (storedCount === null || missingCount === null) return DASH;
  return `${storedCount} / ${missingCount}`;
}

/** Доля сохранённой поддержки; null — счётчиков нет, полоса не рисуется. */
function supportShare(family: FamilySummary): number | null {
  const { storedCount, missingCount } = family.support;
  if (storedCount === null || missingCount === null) return null;
  const total = storedCount + missingCount;
  return total === 0 ? 0 : storedCount / total;
}

function qcText(family: FamilySummary): string {
  if (family.qc.passed === null) return DASH;
  return family.qc.passed ? "ok" : "fail";
}

function codesOf(family: FamilySummary): readonly string[] | null {
  return family.reasonCodes ?? family.qc.reasonCodes;
}

function reasonText(family: FamilySummary): string {
  const codes = codesOf(family);
  if (codes === null) return NO_CODES;
  if (codes.length === 0) return family.status === "available" ? FULL_RESULT : NO_REASON;
  return codes.map(reasonCodeRu).join("; ");
}

function f1Text(value: number | null): string {
  return value === null ? "н/д" : `${value.toFixed(2)} Гц`;
}

function footRow(left: string, right: string): HTMLElement {
  return el("div", { className: "lnt-xr-foot" }, [
    el("span", { text: left }),
    el("span", { text: right }),
  ]);
}

function familyCard(family: FamilySummary, index: number): HTMLElement {
  const codes = codesOf(family);
  const share = supportShare(family);
  const card = el("article", {
    className: "lnt-xr-card lnt-xr-enter",
    attrs: { "data-family-id": family.id, "data-family-status": family.status, title: family.id },
  });
  card.style.setProperty("--i", stagger(index));
  const reasonChildren =
    codes === null || codes.length === 0
      ? []
      : [el("span", { className: "lnt-xr-code", text: codes.join(", ") })];
  const body: Node[] = [
    el("div", { className: "lnt-xr-card-top" }, [
      el("span", {
        className: `lnt-status-pill lnt-xr-pill-${pillTone(family.status)}`,
        text: statusTitle(family.status),
      }),
      el("span", { className: "lnt-xr-id", text: family.id.slice(0, 3) }),
    ]),
    el("p", { className: "lnt-xr-name", text: familyNameRu(family.id) }),
    el("p", { className: "lnt-xr-reason", text: reasonText(family) }, reasonChildren),
  ];
  if (share !== null) {
    const fill = el("div", { className: "lnt-xr-bar-fill" });
    fill.style.setProperty("--i", stagger(index));
    fill.style.setProperty("--share", share.toFixed(3));
    body.push(
      el("div", { className: "lnt-xr-bar", attrs: { title: "Сохранено против пропущено" } }, [
        fill,
      ]),
    );
  }
  body.push(
    footRow(`поддержка ${supportText(family)}`, windowText(family)),
    footRow(bandText(family), `qc ${qcText(family)}`),
  );
  card.append(...body);
  return card;
}

function statusGroup(bucket: Bucket, total: number, offset: number, index: number): HTMLElement {
  const section = el("section", {
    className: "lnt-xr-group lnt-xr-enter",
    attrs: { "data-family-group": bucket.key },
  });
  section.style.setProperty("--i", stagger(index * 3));
  const grid = el("div", { className: "lnt-xr-grid" });
  if (bucket.items.length === 0) {
    grid.append(el("p", { className: "lnt-xr-empty", text: EMPTY_GROUP }));
  }
  bucket.items.forEach((family, position) => {
    grid.append(familyCard(family, offset + position));
  });
  section.append(
    el("div", { className: "lnt-xr-group-head" }, [
      el("h3", { text: bucket.title }),
      el("span", {
        className: "lnt-xr-count",
        attrs: { "data-group-count": bucket.key },
        text: `${bucket.items.length} из ${total}`,
      }),
    ]),
    grid,
  );
  return section;
}

function bucketsOf(families: readonly FamilySummary[]): Bucket[] {
  const buckets: Bucket[] = FAMILY_STATUS_GROUPS.map((group) => ({ ...group, items: [] }));
  for (const family of families) {
    const found = buckets.find((bucket) => bucket.key === family.status);
    if (found === undefined)
      buckets.push({ key: family.status, title: family.status, items: [family] });
    else found.items.push(family);
  }
  return buckets;
}

function topBar(
  summary: CharacterizationSummary,
  buckets: Bucket[],
  session: string | null,
): HTMLElement {
  const sessionLine = session === null ? "" : `Сессия ${session} · `;
  const chips = FAMILY_STATUS_GROUPS.map((group) => {
    const count = buckets.find((bucket) => bucket.key === group.key)?.items.length ?? 0;
    return el("span", {
      className: "lnt-xr-chip",
      attrs: { "data-tally": group.key },
      text: `${count} ${group.title.toLowerCase()}`,
    });
  });
  return el("div", { className: "lnt-xr-top lnt-xr-enter" }, [
    el("div", { className: "lnt-xr-top-text" }, [
      el("h3", { text: SUMMARY_TITLE }),
      el("p", {
        className: "lnt-xr-note",
        text: `${sessionLine}частота сети F01: ${f1Text(summary.f1Hz)}`,
      }),
    ]),
    el("div", { className: "lnt-xr-tally" }, chips),
  ]);
}

/** Сводка прогона карточками: шапка со счётчиками + группы по статусу. */
export function renderFamilyCards(
  summary: CharacterizationSummary,
  options: FamilyCardsOptions = {},
): HTMLElement {
  const buckets = bucketsOf(summary.families);
  const root = el("div", { className: "lnt-xr" }, [
    topBar(summary, buckets, options.session ?? null),
  ]);
  let offset = 0;
  buckets.forEach((bucket, index) => {
    root.append(statusGroup(bucket, summary.families.length, offset, index));
    offset += bucket.items.length;
  });
  return root;
}
