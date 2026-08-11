const TERMINAL_STATUSES = new Set(["succeeded", "cancelled", "failed", "interrupted"]);
const SESSION_JOB_KINDS = new Set(["simulate", "capture", "analyze"]);

export function createJobController({
  api,
  elements,
  render,
  clearError,
  reportError,
  setStartControlsDisabled,
  refreshSessions,
  reopenSession,
}) {
  let activeJobId = null;
  let watcher = null;
  let recovering = false;

  async function finish(snapshot) {
    watcher?.close();
    watcher = null;
    activeJobId = null;
    elements.cancel.hidden = true;
    elements.cancel.disabled = true;
    elements.cancel.textContent = "Отменить после текущей сессии";
    setStartControlsDisabled(false);

    if (snapshot.error_message) reportError(new Error(snapshot.error_message));
    if (SESSION_JOB_KINDS.has(snapshot.kind)) await refreshSessions();
    if (snapshot.status !== "succeeded") return;
    if (snapshot.kind === "analyze") {
      await reopenSession();
    } else if (snapshot.kind === "compare") {
      render.compare(snapshot.result ?? {});
    } else if (snapshot.kind === "selftest") {
      render.selftest(snapshot.result ?? {});
    } else if (snapshot.kind === "device_check") {
      render.device(snapshot.result ?? {});
    }
  }

  async function recoverFromStreamError(jobId) {
    if (recovering || activeJobId !== jobId) return;
    recovering = true;
    try {
      const snapshot = await api.getJob(jobId);
      if (TERMINAL_STATUSES.has(snapshot.status)) {
        await finish(snapshot);
        return;
      }
      elements.status.textContent = "Связь с задачей прервана, ожидаем восстановление…";
    } catch (error) {
      if (error?.status === 404) {
        await finish({
          job_id: jobId,
          kind: "unknown",
          status: "failed",
          error_message:
            "Сервер был перезапущен — задача потеряна. Управление разблокировано, повторите действие.",
        });
        return;
      }
      elements.status.textContent = "Связь с задачей прервана, ожидаем восстановление…";
    } finally {
      recovering = false;
    }
  }

  function activate(snapshot) {
    activeJobId = snapshot.job_id;
    setStartControlsDisabled(true);
    elements.progress.hidden = false;
    elements.cancel.hidden = false;
    elements.cancel.disabled = snapshot.status === "cancelling";
    render.progress(snapshot);
    watcher = api.watchJob(snapshot.job_id, {
      onSnapshot(nextSnapshot) {
        render.progress(nextSnapshot);
        if (nextSnapshot.status === "cancelling") {
          elements.cancel.disabled = true;
          elements.cancel.textContent = "Отмена после текущей сессии…";
        }
        if (TERMINAL_STATUSES.has(nextSnapshot.status)) void finish(nextSnapshot);
      },
      onError() {
        void recoverFromStreamError(snapshot.job_id);
      },
    });
    if (TERMINAL_STATUSES.has(snapshot.status)) void finish(snapshot);
  }

  async function run(request) {
    if (activeJobId !== null) {
      reportError(new Error("Задача ещё выполняется — дождитесь завершения или отмените её."));
      return;
    }
    clearError();
    activeJobId = "pending";
    setStartControlsDisabled(true);
    try {
      const created = await api.startJob(request);
      const snapshot = created.stage ? created : await api.getJob(created.job_id);
      activate(snapshot);
    } catch (error) {
      activeJobId = null;
      setStartControlsDisabled(false);
      reportError(error);
    }
  }

  async function cancel() {
    if (!activeJobId) return;
    elements.cancel.disabled = true;
    elements.cancel.textContent = "Отмена после текущей сессии…";
    try {
      const snapshot = await api.cancelJob(activeJobId);
      render.progress(snapshot);
    } catch (error) {
      elements.cancel.disabled = false;
      elements.cancel.textContent = "Повторить отмену";
      reportError(error);
    }
  }

  return {
    get activeJobId() { return activeJobId; },
    cancel,
    run,
  };
}
