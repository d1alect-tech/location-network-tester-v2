/** Общий помощник axe для e2e-спеков: одна декларация window.axe,
 * типизированный запуск и сводка serious/critical нарушений с деталями
 * узлов (html + сообщения проверок) для диагностики в ассертах. */

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";

const here = dirname(fileURLToPath(import.meta.url));

/** Локальная вендореная копия axe-core (офлайн-политика репозитория). */
export const AXE_SCRIPT_PATH = resolve(here, "../../node_modules/axe-core/axe.min.js");

interface AxeCheckResult {
  id: string;
  message: string;
}

interface AxeNode {
  html: string;
  any: AxeCheckResult[];
}

interface AxeViolation {
  id: string;
  impact: string | null;
  nodes: AxeNode[];
}

interface AxeRunResult {
  violations: AxeViolation[];
}

/** Доступ к window.axe без глобальной декларации: существующие спеки
 * (catalog/experiments) уже расширяют Window своими типами — повторная
 * декларация с иной формой узлов ломает слияние интерфейсов (TS2717).
 * Приведение выполняется ВНУТРИ browser-колбэка evaluate. */

export interface AxeSeriousSummary {
  id: string;
  impact: string | null;
  nodes: { html: string; checks: string[] }[];
}

/** Вставляет axe на страницу (офлайн, из node_modules). */
export async function injectAxe(page: Page): Promise<void> {
  await page.addScriptTag({ path: AXE_SCRIPT_PATH });
}

/** Прогоняет axe по WCAG 2.x A/AA и возвращает только serious/critical. */
export async function seriousAxeViolations(page: Page): Promise<AxeSeriousSummary[]> {
  const results = await page.evaluate(() => {
    const axe = (
      window as unknown as {
        axe?: { run(t: Document, o?: Record<string, unknown>): Promise<AxeRunResult> };
      }
    ).axe;
    if (!axe) throw new Error("axe не загружен на страницу");
    return axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] });
  });
  return results.violations
    .filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""))
    .map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      nodes: violation.nodes.map((node) => ({
        html: node.html,
        checks: node.any.map((check) => `${check.id}: ${check.message}`),
      })),
    }));
}
