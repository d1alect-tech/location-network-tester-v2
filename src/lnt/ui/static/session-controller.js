import { sortSessions } from "./session-filter.js";

export function createSessionController({
  api,
  charts,
  filterSessions = (items) => items,
  render,
  clearError,
  reportError,
  syncStartControls,
}) {
  let nextEpoch = 0;
  let catalogEpoch = 0;
  let selectionEpoch = 0;
  let waveformEpoch = 0;
  let sessions = [];
  let sessionQuery = "";
  let selectedName = null;
  let selectedDetail = null;

  function advanceEpoch() {
    nextEpoch += 1;
    return nextEpoch;
  }

  function renderCatalog() {
    render.catalog(
      filterSessions(sessions, sessionQuery),
      selectedName,
      { onSelect: open, onRefresh: refresh },
      { query: sessionQuery, sessions },
    );
  }

  function setQuery(value) {
    sessionQuery = String(value ?? "");
    renderCatalog();
  }

  function beginSelection(name) {
    selectionEpoch = advanceEpoch();
    waveformEpoch = selectionEpoch;
    selectedName = name;
    selectedDetail = null;
    return selectionEpoch;
  }

  function selectionIsCurrent(name, epoch) {
    return selectedName === name && selectionEpoch === epoch;
  }

  function invalidateSelection() {
    selectionEpoch = advanceEpoch();
    waveformEpoch = selectionEpoch;
    selectedName = null;
    selectedDetail = null;
    render.detail(null);
  }

  async function refresh() {
    const epoch = advanceEpoch();
    catalogEpoch = epoch;
    try {
      const payload = await api.listSessions();
      if (catalogEpoch !== epoch) return;
      sessions = sortSessions(Array.isArray(payload.sessions) ? payload.sessions : []);
      if (selectedName !== null && !sessions.some((session) => session.name === selectedName)) {
        invalidateSelection();
      }
      renderCatalog();
    } catch (error) {
      if (catalogEpoch === epoch) reportError(error);
    }
  }

  async function open(session) {
    const name = session.name;
    const epoch = beginSelection(name);
    const isCurrent = () => selectionIsCurrent(name, epoch);
    renderCatalog();
    if (session.status === "invalid") {
      selectedDetail = { name, error: session.error };
      render.detail(selectedDetail);
      return;
    }

    selectedDetail = { name, pending: true };
    render.detail(selectedDetail);
    clearError();
    try {
      const detail = await api.getSessionDetail(name);
      if (!isCurrent()) return;
      selectedDetail = detail;
      render.detail(detail);
      syncStartControls();
      if (!detail.spectrum_available) return;
      const spectrum = await api.getSpectrum(name);
      if (!isCurrent()) return;
      await charts.plotSpectrum("spectrum-plot", spectrum, { isCurrent });
    } catch (error) {
      if (isCurrent()) reportError(error);
    }
  }

  async function loadWaveform(channel = "ch1") {
    if (selectedName === null) return;
    const name = selectedName;
    const selectedEpoch = selectionEpoch;
    const epoch = advanceEpoch();
    waveformEpoch = epoch;
    const isCurrent = () => (
      selectionIsCurrent(name, selectedEpoch) && waveformEpoch === epoch
    );
    try {
      const waveform = await api.getWaveform(name, channel);
      if (!isCurrent()) return;
      await charts.plotWaveform("waveform-plot", waveform, { isCurrent });
    } catch (error) {
      if (!isCurrent()) return;
      charts.failChart?.("waveform-plot");
      reportError(error);
    }
  }

  async function reopen() {
    const selected = sessions.find((session) => session.name === selectedName);
    if (selected) await open(selected);
  }

  return {
    get selectedDetail() { return selectedDetail; },
    get selectedName() { return selectedName; },
    get sessions() { return sessions; },
    loadWaveform,
    open,
    refresh,
    reopen,
    setQuery,
  };
}
