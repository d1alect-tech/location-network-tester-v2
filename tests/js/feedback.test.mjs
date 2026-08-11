import assert from "node:assert/strict";
import { test } from "node:test";

import { adviceFor, jobTitle } from "../../src/lnt/ui/static/feedback.js";

const BASE_TITLE = "LNT — панель мониторинга";

test("adviceFor returns transformer hint for weak CH2", () => {
  const advice = adviceFor("CH2 слишком слаб для синхронизации: RMS 0.0251 В < 0.05 В");
  assert.ok(advice.includes("трансформатор 230:6"));
});

test("adviceFor returns catalog hint for existing dir", () => {
  const advice = adviceFor("каталог сессии уже существует: D:\\x");
  assert.ok(advice.includes("Каталог"));
});

test("adviceFor returns device hint", () => {
  for (const message of ["Устройство недоступно", "Драйвер не найден", "нет WinUSB"]) {
    const advice = adviceFor(message);
    assert.ok(advice.includes("Проверить устройство"), `нет подсказки для: ${message}`);
  }
});

test("adviceFor returns null for unknown and empty", () => {
  for (const message of ["", null, undefined, "что-то ещё"]) {
    assert.equal(adviceFor(message), null);
  }
});

test("jobTitle formats running series", () => {
  const snapshot = { status: "running", stage: "capturing", series_index: 2, series_total: 5 };
  assert.equal(jobTitle(snapshot, BASE_TITLE), "[2/5] Захват — LNT");
});

test("jobTitle without series omits brackets", () => {
  const snapshot = { status: "running", stage: "capturing", series_index: null, series_total: null };
  assert.equal(jobTitle(snapshot, BASE_TITLE), "Захват — LNT");
});

test("jobTitle returns base title on terminal states and null snapshot", () => {
  for (const status of ["succeeded", "cancelled", "failed"]) {
    assert.equal(jobTitle({ status, stage: "done" }, BASE_TITLE), BASE_TITLE);
  }
  assert.equal(jobTitle(null, BASE_TITLE), BASE_TITLE);
});
