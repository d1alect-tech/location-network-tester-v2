import assert from "node:assert/strict";
import { test } from "node:test";

import { createJobController } from "../../src/lnt/ui/static/job-controller.js";

class FakeApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
  }
}

function makeElements() {
  return {
    cancel: { hidden: true, disabled: true, textContent: "" },
    progress: { hidden: true },
    status: { textContent: "" },
  };
}

function makeHarness({ getJob }) {
  const reported = [];
  const watchers = [];
  const elements = makeElements();
  const controller = createJobController({
    api: {
      startJob: async () => ({ job_id: "job-1", kind: "device_check", status: "running", stage: "running" }),
      getJob: getJob ?? (async () => ({ job_id: "job-1", kind: "device_check", status: "running" })),
      watchJob: (jobId, handlers) => {
        const watcher = { jobId, handlers, closed: false, close() { this.closed = true; } };
        watchers.push(watcher);
        return watcher;
      },
      cancelJob: async () => ({ job_id: "job-1", status: "cancelling" }),
    },
    elements,
    render: { progress: () => {}, device: () => {}, compare: () => {}, selftest: () => {} },
    clearError: () => {},
    reportError: (error) => reported.push(String(error?.message ?? error)),
    setStartControlsDisabled: () => {},
    refreshSessions: async () => {},
    reopenSession: async () => {},
  });
  return { controller, reported, watchers, elements };
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

test("повторный запуск при активной задаче сообщает об ошибке, а не молчит", async () => {
  const { controller, reported } = makeHarness({});
  await controller.run({ kind: "device_check" });
  assert.equal(controller.activeJobId, "job-1");
  await controller.run({ kind: "device_check" });
  assert.equal(reported.length, 1);
  assert.match(reported[0], /выполняется/i);
});

test("потерянная после рестарта сервера задача разблокирует управление", async () => {
  const { controller, reported, watchers } = makeHarness({
    getJob: async () => {
      throw new FakeApiError(404, "задача не найдена");
    },
  });
  await controller.run({ kind: "device_check" });
  assert.equal(watchers.length, 1);
  watchers[0].handlers.onError({});
  await flush();
  assert.equal(controller.activeJobId, null, "activeJobId должен сброситься");
  assert.ok(watchers[0].closed, "watcher должен быть закрыт");
  assert.ok(
    reported.some((message) => /перезапущен|потеряна/i.test(message)),
    `ожидалось сообщение о потерянной задаче, получено: ${JSON.stringify(reported)}`,
  );
});

test("временный сбой сети не сбрасывает активную задачу", async () => {
  const { controller, watchers, elements } = makeHarness({
    getJob: async () => {
      throw new FakeApiError(0, "Сеть недоступна.");
    },
  });
  await controller.run({ kind: "device_check" });
  watchers[0].handlers.onError({});
  await flush();
  assert.equal(controller.activeJobId, "job-1", "задача должна остаться активной");
  assert.ok(!watchers[0].closed, "watcher не должен закрываться");
  assert.match(elements.status.textContent, /восстановлени/i);
});

test("пропущенный терминальный снапшот добирается через getJob при сбое потока", async () => {
  const { controller, watchers } = makeHarness({
    getJob: async () => ({ job_id: "job-1", kind: "device_check", status: "succeeded", result: {} }),
  });
  await controller.run({ kind: "device_check" });
  watchers[0].handlers.onError({});
  await flush();
  assert.equal(controller.activeJobId, null, "терминальный статус должен завершить задачу");
});
