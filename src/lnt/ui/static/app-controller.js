import {
  ApiError,
  cancelJob,
  getConfig,
  getJob,
  getSessionDetail,
  getSpectrum,
  getWaveform,
  listSessions,
  startJob,
  watchJob,
} from "./api.js";
import {
  applyConfig,
  collectElements,
  compareRequest,
  fillBaselineSelect,
  fillSessionSelect,
  jobElements,
  observeHeaderScroll,
  requestFromForm,
  setStartControlsDisabled,
  syncCaptureBaselineState,
  syncCaptureInputState,
  updateCompareButton,
} from "./app-dom.js";
import { applyChartTheme, failChart } from "./chart-views.js";
import { adviceFor, jobTitle } from "./feedback.js";
import { createJobController } from "./job-controller.js";
import { createSessionController } from "./session-controller.js";
import { filterSessions } from "./session-filter.js";
import { createThemeController } from "./theme.js";
import {
  plotSpectrum,
  plotWaveform,
  renderCompare,
  renderDeviceStatus,
  renderError,
  renderJobProgress,
  renderSelftest,
  renderSessionDetail,
  renderSessions,
} from "./views.js";

export function bootstrapApp(root = document) {
  const elements = collectElements(root);
  const progressElements = jobElements(elements);
  const baseTitle = document.title;
  let jobs;

  function showError(error) {
    let message = "Операция не завершена. Повторите действие.";
    if (error instanceof ApiError) {
      if (error.status === 409) message = "Уже выполняется задача.";
      else if (error.status === 422) message = error.detail;
      else message = error.detail || message;
    } else if (error instanceof Error && error.message) {
      message = error.message;
    }
    renderError(elements.errorBanner, message, adviceFor(message));
    elements.errorBanner.focus?.();
  }

  function clearError() {
    renderError(elements.errorBanner, "");
  }

  function disableStartControls(disabled) {
    setStartControlsDisabled(root, elements, disabled);
  }

  function clearSessionSearch() {
    elements.sessionSearch.value = "";
    sessions.setQuery("");
    elements.sessionSearch.focus();
  }

  const sessions = createSessionController({
    api: { getSessionDetail, getSpectrum, getWaveform, listSessions },
    charts: { failChart, plotSpectrum, plotWaveform },
    filterSessions,
    render: {
      catalog(items, selectedName, callbacks, extras) {
        renderSessions(elements.sessionsList, items, {
          ...callbacks,
          selectedName,
          query: extras?.query ?? "",
          onClearSearch: clearSessionSearch,
        });
        const catalog = extras?.sessions ?? items;
        fillSessionSelect(elements.compareForm.elements.session_a, catalog, "Выберите сессию A");
        fillSessionSelect(elements.compareForm.elements.session_b, catalog, "Выберите сессию B");
        fillBaselineSelect(elements.captureForm.elements.baseline_session, catalog);
        updateCompareButton(elements, jobs?.activeJobId ?? null);
      },
      detail: (detail) => renderSessionDetail(elements.sessionDetail, detail),
    },
    clearError,
    reportError: showError,
    syncStartControls: () => disableStartControls(jobs?.activeJobId !== null),
  });

  jobs = createJobController({
    api: { cancelJob, getJob, startJob, watchJob },
    elements: {
      cancel: elements.jobCancel,
      progress: elements.jobProgress,
      status: elements.jobStatus,
    },
    render: {
      compare: (result) => renderCompare(elements.compareResult, result),
      device: (result) => renderDeviceStatus(elements.deviceStatus, result),
      progress: (snapshot) => {
        renderJobProgress(progressElements, snapshot);
        document.title = jobTitle(snapshot, baseTitle);
      },
      selftest: (result) => renderSelftest(elements.selftestResult, result),
    },
    clearError,
    reportError: showError,
    setStartControlsDisabled: disableStartControls,
    refreshSessions: sessions.refresh,
    reopenSession: sessions.reopen,
  });

  async function loadConfig() {
    try {
      applyConfig(root, elements, await getConfig());
    } catch (error) {
      showError(error);
    }
  }

  elements.simulateForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void jobs.run(requestFromForm(elements.simulateForm, "simulate"));
  });
  elements.captureForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void jobs.run(requestFromForm(elements.captureForm, "capture"));
  });
  elements.captureForm.addEventListener("change", () => {
    syncCaptureInputState(elements.captureForm);
    syncCaptureBaselineState(elements.captureForm);
  });
  syncCaptureInputState(elements.captureForm);
  syncCaptureBaselineState(elements.captureForm);
  elements.deviceCheck.addEventListener("click", () => void jobs.run({ kind: "device_check" }));
  elements.selftest.addEventListener("click", () => void jobs.run({ kind: "selftest" }));
  elements.sessionsRefresh.addEventListener("click", () => void sessions.refresh());
  elements.sessionSearch.addEventListener("input", () => {
    sessions.setQuery(elements.sessionSearch.value);
  });
  elements.sessionSearchClear.addEventListener("click", clearSessionSearch);
  elements.compareForm.addEventListener("change", () => updateCompareButton(elements, jobs.activeJobId));
  elements.compareForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void jobs.run(compareRequest(elements.compareForm));
  });
  elements.sessionDetail.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const analyzeButton = target?.closest('[data-action="analyze"]');
    if (analyzeButton) {
      void jobs.run({ kind: "analyze", session_name: analyzeButton.dataset.sessionName });
    } else if (target?.closest("#waveform-load-btn")) {
      void sessions.loadWaveform();
    } else if (target?.closest("#waveform-ch2-btn")) {
      void sessions.loadWaveform("ch2");
    }
  });
  elements.jobCancel.addEventListener("click", () => void jobs.cancel());

  const theme = createThemeController({
    root: document.documentElement,
    select: elements.themeSelect,
    storage: window.localStorage,
    media: window.matchMedia("(prefers-color-scheme: dark)"),
    onChange: applyChartTheme,
  });
  theme.start();
  observeHeaderScroll(window, elements.appHeader);

  const skipLink = root.querySelector(".skip-link");
  const mainContent = root.getElementById("main-content");
  skipLink?.addEventListener("click", () => mainContent?.focus());

  elements.jobProgress.hidden = true;
  elements.jobCancel.hidden = true;
  void Promise.all([loadConfig(), sessions.refresh()]);
  return { jobs, sessions, theme };
}
