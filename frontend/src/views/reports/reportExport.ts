/** Выгрузка .md-отчёта (T12.3): имя файла и скачивание Blob.
 * Чистые операции без сети и стора: рабочая область передаёт сюда тот же
 * markdown, что показан в previewBlock .md-блоке; селектор #lnt-rep-download
 * и текст кнопки не меняются (пин reports.spec.ts). */

import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";

export const REPORT_EXPORT_FORMAT = "md";

/** Имя файла выгрузки: report-<experiment_id>.md, мусор из id вычищен. */
export function buildReportFilename(experimentId: string): string {
  const safe = experimentId.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  return `report-${safe === "" ? "report" : safe}.md`;
}

/** Скачивает markdown как .md-файл через временный <a download>. */
export function downloadMarkdown(markdown: string, filename: string): void {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = el("a", { attrs: { href: url, download: filename } });
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  announcePolite("Файл отчёта скачан");
}
