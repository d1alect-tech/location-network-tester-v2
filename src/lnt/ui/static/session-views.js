import { createChartShell } from "./chart-views.js";
import { renderCh1Section } from "./ch1-input-reference.js";
import { renderLineQualityView } from "./line-quality-views.js";
import { appendDataCell, appendTableHeader, element, numberText, valueText } from "./view-dom.js";

function emptySessions(callbacks) {
  const container = element("div", "empty-state");
  container.append(
    element("h3", "", "В каталоге нет сессий"),
    element("p", "", "Создайте симуляцию или выполните захват."),
  );
  const actions = element("div", "empty-actions");
  const createLink = element("a", "button button-primary", "Создать симуляцию");
  createLink.href = "#simulate-heading";
  const refreshButton = element("button", "button button-secondary", "Обновить каталог");
  refreshButton.type = "button";
  refreshButton.addEventListener("click", () => callbacks.onRefresh?.());
  actions.append(createLink, refreshButton);
  container.append(actions);
  return container;
}

function emptySearch(query, callbacks) {
  const container = element("div", "empty-state search-empty");
  const queryText = element("p", "helper-text");
  queryText.textContent = valueText(query);
  const clearButton = element("button", "button button-secondary", "Очистить поиск");
  clearButton.type = "button";
  clearButton.addEventListener("click", () => callbacks.onClearSearch?.());
  container.append(element("h3", "", "По запросу ничего не найдено"), queryText, clearButton);
  return container;
}

export function renderSessions(listEl, sessions, callbacks = {}) {
  if (!Array.isArray(sessions) || sessions.length === 0) {
    const query = String(callbacks.query ?? "").trim();
    listEl.replaceChildren(
      query ? emptySearch(callbacks.query, callbacks) : emptySessions(callbacks),
    );
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const session of sessions) {
    const row = element("button", "session-row");
    row.type = "button";
    row.dataset.sessionName = valueText(session.name);
    row.title = valueText(session.summary?.session_id ?? session.name);
    if (session.name === callbacks.selectedName) {
      row.classList.add("is-selected");
      row.setAttribute("aria-pressed", "true");
    } else {
      row.setAttribute("aria-pressed", "false");
    }
    if (session.status === "invalid") row.classList.add("is-error");

    const status = session.status === "invalid"
      ? `Повреждена: ${valueText(session.error)}`
      : session.analyzed ? "Проанализирована" : "Ожидает анализа";
    const summary = session.summary ?? {};
    const meta = [summary.created_utc, summary.source, summary.session_type, summary.profile, summary.label]
      .filter(Boolean)
      .join(" · ");
    const information = element("span", "field");
    information.append(element("span", session.status === "invalid" ? "status-error" : "", status));
    if (meta) information.append(element("span", "helper-text", meta));
    if (summary.session_type === "self_noise") {
      information.append(element("span", "badge badge-selfnoise", "Самошум"));
    }
    if (summary.session_type === "line_quality") {
      information.append(element("span", "badge badge-line-quality", "Сеть 50 Гц"));
    }
    if (summary.channels === "ch1_only") {
      information.append(element("span", "badge badge-single-channel", "1 канал"));
    }
    row.append(element("span", "analysis-state", valueText(session.name)), information);
    row.addEventListener("click", () => callbacks.onSelect?.(session));
    fragment.append(row);
  }
  listEl.replaceChildren(fragment);
}

function manifestView(manifest) {
  const list = element("dl", "manifest-grid");
  const labels = {
    session_id: "ID",
    created_utc: "Создана",
    source: "Источник",
    session_type: "Тип",
    profile: "Профиль",
    sample_rate_hz: "Частота дискретизации, Гц",
    duration_s: "Длительность, с",
    sample_count: "Отсчётов",
    parameters: "Параметры",
  };
  for (const [key, value] of Object.entries(manifest ?? {})) {
    if (!(key in labels)) continue;
    const item = document.createElement("div");
    item.append(element("dt", "", labels[key]), element("dd", "", valueText(value)));
    list.append(item);
  }
  return list;
}

function manifestDisclosure(manifest) {
  const disclosure = element("details", "manifest-disclosure");
  disclosure.append(element("summary", "", "Манифест"), manifestView(manifest));
  return disclosure;
}

function analysisView(detail) {
  const analysis = detail.analysis;
  if (analysis.line_quality) return renderLineQualityView(analysis);
  const container = element("div", "analysis-content");
  const table = element("table", "metrics-table");
  table.append(element("caption", "", "Метрики иголок"));
  appendTableHeader(table, ["Метрика", "Значение", "Единица / смысл"]);
  const body = document.createElement("tbody");
  const singleChannel = analysis.needle?.sync_source === "nominal";
  const syncLabel = singleChannel ? "номинал 20 мс (1 канал)" : "CH2 (сеть 50 Гц)";
  const syncValue = (value) => {
    if (typeof value === "number") return numberText(value);
    return singleChannel ? "н/д (1 канал)" : valueText(value);
  };
  const metrics = [
    ["μ_pk", analysis.needle?.needle_mean_v, "В"],
    ["σ/μ", analysis.needle?.needle_sigma_ratio, "разброс пиков"],
    ["P_async/P_sync", syncValue(analysis.needle?.async_sync_ratio), "асинхронность"],
    ["CV CH2", syncValue(analysis.needle?.lf_envelope_cv), "огибающая"],
    ["Частота сети", syncValue(analysis.needle?.line_frequency_hz), "Гц"],
    ["Циклы", analysis.needle?.cycles_analyzed, "шт."],
    ["Синхронизация", syncLabel, "источник фазовой привязки"],
  ];
  for (const [name, value, meaning] of metrics) {
    const row = document.createElement("tr");
    const heading = element("th", "", name);
    heading.scope = "row";
    row.append(heading);
    appendDataCell(row, typeof value === "number" ? numberText(value) : valueText(value));
    appendDataCell(row, meaning);
    body.append(row);
  }
  table.append(body);

  const spectrum = createChartShell({
    name: "spectrum",
    caption: "Логарифмический спектр мощности выбранной сессии",
    plotClass: "plot-spectrum",
  });
  const peaks = element("table", "peaks-table");
  peaks.append(element("caption", "", "Обнаруженные пики спектра"));
  appendTableHeader(peaks, ["Частота, Гц", "Уровень, дБ", "Выраженность, дБ", "Q"]);
  const peakBody = document.createElement("tbody");
  const peakItems = analysis.spectrum?.peaks ?? [];
  if (peakItems.length === 0) {
    const row = document.createElement("tr");
    const cell = element("td", "", "Выраженных пиков не найдено");
    cell.colSpan = 4;
    row.append(cell);
    peakBody.append(row);
  } else {
    for (const peak of peakItems) {
      const row = document.createElement("tr");
      appendDataCell(row, numberText(peak.frequency_hz, 0));
      appendDataCell(row, numberText(peak.level_db, 1));
      appendDataCell(row, numberText(peak.prominence_db, 1));
      appendDataCell(row, numberText(peak.q_factor, 1));
      peakBody.append(row);
    }
  }
  peaks.append(peakBody);
  container.append(table, renderCh1Section(analysis), spectrum, peaks);
  return container;
}

function waveformControls(detail) {
  const fragment = document.createDocumentFragment();
  if (!detail.waveform_available) return fragment;
  const button = element("button", "button button-secondary", "Осциллограмма CH1");
  button.id = "waveform-load-btn";
  button.type = "button";
  button.dataset.action = "load-waveform";
  const chart = createChartShell({
    name: "waveform",
    caption: "Превью осциллограммы выбранной сессии",
    plotClass: "plot-waveform",
    hidden: true,
  });
  if (detail.ch2_available === false) {
    fragment.append(button, chart);
    return fragment;
  }
  const ch2Button = element("button", "button button-secondary", "Осциллограмма CH2");
  ch2Button.id = "waveform-ch2-btn";
  ch2Button.type = "button";
  fragment.append(button, ch2Button, chart);
  return fragment;
}

export function renderSessionDetail(el, detail) {
  const heading = element("div", "panel-heading");
  const title = element("h2", "", "Детальный анализ");
  title.id = "detail-heading";
  heading.append(title);

  if (detail === null) {
    heading.append(element("span", "status-label", "Не выбрана"));
    const state = element("div", "empty-state");
    state.append(
      element("h3", "", "Сессия не выбрана"),
      element("p", "", "Выберите сессию в каталоге, чтобы открыть детальный анализ."),
    );
    el.replaceChildren(heading, state);
    return;
  }

  if (detail.pending === true) {
    heading.append(element("span", "status-label", "Загрузка…"));
    const state = element("div", "empty-state analysis-loading");
    state.setAttribute("role", "status");
    state.setAttribute("aria-live", "polite");
    state.append(
      element("h3", "", valueText(detail.name)),
      element("p", "", "Загрузка детального анализа…"),
    );
    el.replaceChildren(heading, state);
    return;
  }

  if (detail.error) {
    heading.append(element("span", "status-label status-error", "Повреждена"));
    const state = element("div", "empty-state state-error");
    state.append(element("h3", "", valueText(detail.name)), element("p", "", detail.error));
    el.replaceChildren(heading, state);
    return;
  }

  const analyzed = detail.analysis !== null && detail.analysis !== undefined;
  heading.append(element("span", analyzed ? "status-label status-ok" : "status-label", analyzed ? "Проанализирована" : "Не проанализирована"));
  const content = document.createDocumentFragment();
  if (analyzed) {
    content.append(analysisView(detail));
  } else {
    const empty = element("div", "empty-state analysis-empty");
    empty.append(
      element("h3", "", "Анализ ещё не выполнен"),
      element("p", "", "Запустите анализ, чтобы построить спектр и рассчитать метрики."),
    );
    const button = element("button", "button button-primary", "Анализировать");
    button.type = "button";
    button.dataset.action = "analyze";
    button.dataset.sessionName = valueText(detail.name);
    empty.append(button);
    content.append(empty);
  }
  content.append(waveformControls(detail));
  content.append(manifestDisclosure(detail.manifest));
  el.replaceChildren(heading, content);
}
