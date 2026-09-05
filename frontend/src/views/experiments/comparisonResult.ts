/** Рендер результата сравнения (лист C3b, выделен из comparisonView):
 * отчёт сравнимости → гейт с точной причиной; envelope statistics-runs →
 * панель результата с обязательной маркировкой; баннеры статуса.
 * Парсинг эффекта инжектится колбэком (effectFromPayload живёт в C3a-листе),
 * дублирования нет. Лист не импортирует comparisonView/experimentsWorkspace. */

import type { ComparabilityReport, StatisticsResultEnvelope } from "../../api/types-research";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { renderResultPanel } from "./resultPanel";
import type { EffectView } from "./resultPanel";

export interface ComparisonResultTarget {
  root: HTMLElement;
  resultHost: HTMLElement;
  /** V6-хост гейта (.comparability-gate); без него состояние гейта не пишется. */
  gateHost?: HTMLElement;
  /** Дополнительные токен-классы баннера (V6: banner banner-inline). */
  bannerClass?: string;
}

function setGate(target: ComparisonResultTarget, state: "ok" | "blocked", text: string): void {
  const { gateHost } = target;
  if (!gateHost) return;
  gateHost.setAttribute("data-state", state);
  gateHost.textContent = text;
}

/** Парсер сырого эффекта envelope; реализация — effectFromPayload (лист C3a). */
export type ComparisonEffectParser = (raw: unknown) => EffectView | null;

export function renderEnvelope(
  target: ComparisonResultTarget,
  envelope: StatisticsResultEnvelope,
  parseEffect: ComparisonEffectParser,
): void {
  const meta = envelope.metadata;
  if (envelope.result_kind === "refusal") {
    const reason = String((envelope.result as Record<string, unknown>).reason_code ?? "unknown");
    target.resultHost.replaceChildren(
      renderResultPanel({
        title: "Результат сравнения",
        effect: null,
        refusalReason: reason,
        metadata: meta,
      }),
    );
    return;
  }
  if (envelope.result_kind === "effect") {
    const effectRaw = (envelope.result as Record<string, unknown>).effect;
    const driftRaw = (envelope.result as Record<string, unknown>).drift;
    target.resultHost.replaceChildren(
      renderResultPanel({
        title: "Результат сравнения",
        effect: parseEffect(effectRaw),
        drift: driftRaw ? parseEffect(driftRaw) : null,
        metadata: meta,
        limitationsExtra:
          meta.estimator === "qualified_within_run_contrast"
            ? ["Квалифицированный внутрисерийный контраст: причинный вывод недоступен."]
            : [],
      }),
    );
    return;
  }
  target.resultHost.replaceChildren(
    renderResultPanel({
      title: "Описательный результат (без интервала)",
      effect: parseEffect(envelope.result),
      metadata: meta,
      limitationsExtra: ["N ниже минимума инференции: интервал не строится."],
    }),
  );
}

export function renderReport(target: ComparisonResultTarget, report: ComparabilityReport): void {
  const blocks = report.findings.filter((f) => f.level === "block");
  if (!report.comparable) {
    const reason = blocks.map((f) => f.code).join(", ");
    setGate(
      target,
      "blocked",
      `Сравнение заблокировано проверкой сравнимости. Точная причина: ${reason}. Числовой расчёт запрещён до устранения.`,
    );
    target.resultHost.replaceChildren(
      el(
        "div",
        { className: "lnt-exp-banner lnt-exp-banner-warn banner", attrs: { role: "alert" } },
        [
          el("strong", { text: "Сравнение заблокировано проверкой сравнимости." }),
          el("p", { text: `Точная причина: ${reason}. Числовой расчёт запрещён до устранения.` }),
          ...report.findings.map((f) =>
            el("p", {
              className: "lnt-exp-meta-line",
              text: `${f.dimension}: ${String(f.level)} · ${String(f.code)} · поля: ${Array.isArray(f.fields) ? (f.fields as string[]).join(", ") : String(f.fields)}`,
            }),
          ),
        ],
      ),
    );
    announcePolite("Сравнение заблокировано проверкой сравнимости");
    return;
  }
  const confirmed = `Сравнимость подтверждена (${String(report.findings.length)} измерений без блокировок). Можно запускать расчёт.`;
  setGate(target, "ok", confirmed);
  showBanner(target, confirmed, "ok");
}

export function showBanner(
  target: ComparisonResultTarget,
  message: string,
  tone: "ok" | "warn" | "error",
): void {
  announcePolite(message);
  const existing = target.root.querySelector(".lnt-exp-compare-status");
  existing?.remove();
  const tokens = target.bannerClass ? ` ${target.bannerClass}` : "";
  const banner = el("p", {
    className: `lnt-exp-banner lnt-exp-banner-${tone} lnt-exp-compare-status${tokens}`,
    attrs: tone === "error" ? { role: "alert" } : { role: "status" },
    text: message,
  });
  target.resultHost.before(banner);
}
