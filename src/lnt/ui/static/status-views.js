import {
  appendDataCell,
  appendTableHeader,
  element,
  numberText,
  valueText,
} from "./view-dom.js";

const STAGE_LABELS = {
  queued: "в очереди",
  checking_device: "проверка устройства",
  simulating: "симуляция",
  capturing: "захват",
  analyzing: "анализ",
  comparing: "сравнение",
  selftest: "самопроверка",
  done: "готово",
};

const STATUS_LABELS = {
  queued: "Задача в очереди",
  running: "Задача выполняется",
  cancelling: "Отмена после текущей сессии",
  succeeded: "Задача завершена",
  cancelled: "Задача отменена",
  failed: "Задача завершилась с ошибкой",
};

const RAIL_BY_STATUS = {
  queued: "rail-running",
  running: "rail-running",
  cancelling: "rail-running",
  succeeded: "rail-ok",
  failed: "rail-error",
  cancelled: "rail-warn",
};

const STAGE_PROGRESS = {
  queued: 1,
  checking_device: 2,
  simulating: 2,
  capturing: 2,
  analyzing: 3,
  comparing: 4,
  selftest: 4,
  done: 5,
};

export function renderDeviceStatus(el, payload) {
  const panel = el.closest(".measurement-rail");
  const noDriver = payload.driver_installed === false;
  const ready = payload.driver_installed === true && payload.device_opened === true && payload.firmware_present === true;
  const state = ready ? "ok" : noDriver ? "error" : "warn";
  const summary = ready
    ? "Готово к захвату"
    : noDriver
      ? "WinUSB не настроен"
      : payload.device_opened && !payload.firmware_present
        ? "Прошивка не загружена"
        : payload.error_message || "Осциллограф не найден";
  el.textContent = summary;

  panel?.classList.remove("rail-ok", "rail-warn", "rail-error", "state-ok", "state-warn", "state-error");
  panel?.classList.add(`rail-${state}`, `state-${state}`);
  const label = panel?.querySelector(".status-label");
  if (label) {
    label.className = `status-label status-${state}`;
    label.textContent = ready ? "Готово" : noDriver ? "Нет драйвера" : "Недоступно";
  }

  const checks = [
    ["Драйвер", payload.driver_installed],
    ["Устройство", payload.device_opened],
    ["Прошивка", payload.firmware_present],
  ];
  const items = panel?.querySelectorAll(".diagnostic-chain li") ?? [];
  checks.forEach(([name, passed], index) => {
    const item = items[index];
    if (!item) return;
    const dot = element("span", `status-dot status-${passed ? "ok" : "error"}`);
    item.replaceChildren(dot, document.createTextNode(`${name}: ${passed ? "готов" : "не готов"}`));
  });
  const helper = panel?.querySelector(".helper-text");
  if (helper) {
    const hints = Array.isArray(payload.hints) ? payload.hints.join(" ") : "";
    helper.textContent = hints || (ready ? "Устройство доступно для измерения." : "Проверьте USB и WinUSB, затем повторите проверку.");
  }
}

export function renderJobProgress(els, snapshot) {
  const section = els.progress.closest?.("section");
  if (section) {
    section.classList.remove("rail-running", "rail-ok", "rail-error", "rail-warn");
    const rail = RAIL_BY_STATUS[snapshot.status];
    if (rail) section.classList.add(rail);
  }
  const stage = snapshot.stage ?? "queued";
  const progress = STAGE_PROGRESS[stage] ?? 0;
  els.progress.value = progress;
  els.progress.textContent = `${progress} из 5 стадий`;
  els.stage.textContent = `Стадия: ${STAGE_LABELS[stage] ?? valueText(stage)}`;
  els.series.textContent = snapshot.series_total
    ? `Серия ${snapshot.series_index ?? "—"}/${snapshot.series_total}`
    : "Серия —/—";
  const written = Array.isArray(snapshot.written_sessions) && snapshot.written_sessions.length > 0
    ? ` Записано: ${snapshot.written_sessions.join(", ")}.`
    : "";
  const announcementKey = `${snapshot.status}:${stage}:${snapshot.series_index}/${snapshot.series_total}:${written}`;
  const now = Date.now();
  const lastAnnouncementAt = Number(els.status.dataset.lastAnnouncementAt ?? 0);
  const terminal = snapshot.status === "succeeded" || snapshot.status === "cancelled" || snapshot.status === "failed";
  if (
    announcementKey !== els.status.dataset.announcementKey
    && (lastAnnouncementAt === 0 || now - lastAnnouncementAt >= 1000 || terminal)
  ) {
    els.status.textContent = `${STATUS_LABELS[snapshot.status] ?? "Состояние задачи обновлено"}.${written}`;
    els.status.dataset.announcementKey = announcementKey;
    els.status.dataset.lastAnnouncementAt = String(now);
  }

  const steps = els.progress.closest("section")?.querySelectorAll(".job-steps li") ?? [];
  steps.forEach((step, index) => {
    step.classList.remove("is-current", "is-done", "is-failed");
    const stepNumber = index + 1;
    if (snapshot.status === "failed" && stepNumber === progress) step.classList.add("is-failed");
    else if (stepNumber < progress || snapshot.status === "succeeded") step.classList.add("is-done");
    else if (stepNumber === progress) step.classList.add("is-current");
  });
}

function deltaPresentation(delta) {
  const value = Number(delta);
  if (!Number.isFinite(value) || Math.abs(value) < 0.05) {
    return { className: "delta-neutral", text: "0.0 дБ = без изменения" };
  }
  if (value < 0) {
    return { className: "delta-improved", text: `${value.toFixed(1)} дБ ↓ улучшение` };
  }
  return { className: "delta-worse", text: `+${value.toFixed(1)} дБ ↑ ухудшение` };
}

function metricPercent(valueA, valueB) {
  if (typeof valueA !== "number" || typeof valueB !== "number") return "н/д";
  if (!Number.isFinite(valueA) || !Number.isFinite(valueB) || valueA === 0) return "н/д";
  const percent = ((valueB - valueA) / valueA) * 100;
  return `${percent >= 0 ? "+" : ""}${percent.toFixed(1)}%`;
}

export function renderCompare(el, payload) {
  const summary = element("p", "analysis-state", `A: ${valueText(payload.session_a_id)} · B: ${valueText(payload.session_b_id)} · Δ = B − A`);
  const table = element("table", "compare-table");
  table.append(element("caption", "", "Сравнение A/B"));
  appendTableHeader(table, ["Метрика", "A", "B", "Δ"]);
  const body = document.createElement("tbody");

  for (const peak of payload.peak_deltas ?? []) {
    const row = document.createElement("tr");
    const heading = element("th", "", `Пик ${numberText(peak.frequency_hz, 0)} Гц`);
    heading.scope = "row";
    row.append(heading);
    appendDataCell(row, `${numberText(peak.level_a_db, 1)} дБ`, "A");
    appendDataCell(row, `${numberText(peak.level_b_db, 1)} дБ`, "B");
    const presentation = deltaPresentation(peak.delta_db);
    const deltaCell = appendDataCell(row, presentation.text, "Δ");
    deltaCell.className = presentation.className;
    body.append(row);
  }

  for (const metric of payload.metric_deltas ?? []) {
    const row = document.createElement("tr");
    const heading = element("th", "", valueText(metric.name));
    heading.scope = "row";
    row.append(heading);
    appendDataCell(row, numberText(metric.value_a), "A");
    appendDataCell(row, numberText(metric.value_b), "B");
    appendDataCell(row, `${numberText(metric.value_a)} → ${numberText(metric.value_b)} (${metricPercent(metric.value_a, metric.value_b)})`, "Δ");
    body.append(row);
  }
  if (!body.childElementCount) {
    const row = document.createElement("tr");
    const cell = element("td", "", "Нет данных для сравнения");
    cell.colSpan = 4;
    row.append(cell);
    body.append(row);
  }
  table.append(body);
  el.replaceChildren(summary, table);
}

export function renderSelftest(el, payload) {
  const state = payload.ok ? "state-ok" : "state-error";
  const title = payload.ok ? "Selftest пройден" : "Selftest не пройден";
  const result = element("div", state);
  result.append(element("h3", "", title), element("p", "", valueText(payload.message)));
  if (payload.frequency_hz !== null && payload.frequency_hz !== undefined) {
    result.append(element("p", "analysis-state", `Частота: ${numberText(payload.frequency_hz, 0)} Гц`));
  }
  if (payload.cycles_analyzed !== null && payload.cycles_analyzed !== undefined) {
    result.append(element("p", "analysis-state", `Циклов: ${valueText(payload.cycles_analyzed)}`));
  }
  el.replaceChildren(result);
}

export function renderError(bannerEl, message, advice) {
  if (!message) {
    bannerEl.hidden = true;
    bannerEl.replaceChildren();
    return;
  }
  const title = element("h2", "", "Операция не завершена");
  title.id = "error-title";
  const content = [title, element("p", "", String(message))];
  if (advice) content.push(element("p", "error-hint", advice));
  bannerEl.replaceChildren(...content);
  bannerEl.hidden = false;
}
