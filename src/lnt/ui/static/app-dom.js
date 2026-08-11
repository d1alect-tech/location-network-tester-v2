const NUMBER_FIELDS = new Set([
  "duration_s",
  "sample_rate_hz",
  "seed",
  "repeat",
  "interval_s",
  "range_v",
  "channels",
]);

const START_CONTROL_SELECTOR = [
  "#device-check-btn",
  "#selftest-btn",
  '#simulate-form button[type="submit"]',
  '#capture-form button[type="submit"]',
  '#compare-form button[type="submit"]',
  '#session-detail [data-action="analyze"]',
].join(",");

export function collectElements(root) {
  return {
    configRoot: root.getElementById("config-root"),
    deviceCheck: root.getElementById("device-check-btn"),
    deviceStatus: root.getElementById("device-status"),
    simulateForm: root.getElementById("simulate-form"),
    captureForm: root.getElementById("capture-form"),
    sessionsList: root.getElementById("sessions-list"),
    sessionsRefresh: root.getElementById("sessions-refresh-btn"),
    sessionDetail: root.getElementById("session-detail"),
    compareForm: root.getElementById("compare-form"),
    compareResult: root.getElementById("compare-result"),
    selftest: root.getElementById("selftest-btn"),
    selftestResult: root.getElementById("selftest-result"),
    jobProgress: root.getElementById("job-progress"),
    jobStage: root.getElementById("job-stage"),
    jobSeries: root.getElementById("job-series"),
    jobCancel: root.getElementById("job-cancel-btn"),
    jobStatus: root.getElementById("job-status"),
    errorBanner: root.getElementById("error-banner"),
    appHeader: root.querySelector(".app-header"),
    themeSelect: root.getElementById("theme-select"),
    sessionSearch: root.getElementById("session-search"),
    sessionSearchClear: root.getElementById("session-search-clear"),
  };
}

export function observeHeaderScroll(win, header) {
  let scheduled = false;
  const update = () => {
    scheduled = false;
    header.classList.toggle("is-scrolled", win.scrollY > 0);
  };
  win.addEventListener(
    "scroll",
    () => {
      if (scheduled) return;
      scheduled = true;
      win.requestAnimationFrame(update);
    },
    { passive: true },
  );
  update();
}

export function jobElements(elements) {
  return {
    progress: elements.jobProgress,
    stage: elements.jobStage,
    series: elements.jobSeries,
    status: elements.jobStatus,
  };
}

export function updateCompareButton(elements, activeJobId) {
  const submit = elements.compareForm.querySelector('button[type="submit"]');
  const data = new FormData(elements.compareForm);
  const sessionA = data.get("session_a");
  const sessionB = data.get("session_b");
  submit.disabled = activeJobId !== null || !sessionA || !sessionB || sessionA === sessionB;
}

export function setStartControlsDisabled(root, elements, disabled) {
  for (const control of root.querySelectorAll(START_CONTROL_SELECTOR)) {
    control.disabled = disabled;
  }
  if (!disabled) updateCompareButton(elements, null);
}

export function fillSessionSelect(select, sessions, placeholder) {
  const current = select.value;
  const option = document.createElement("option");
  option.value = "";
  option.textContent = placeholder;
  const options = [option];
  for (const session of sessions) {
    if (session.status !== "valid" || !session.analyzed) continue;
    if (session.summary?.session_type === "line_quality") continue;
    const item = document.createElement("option");
    item.value = session.name;
    item.textContent = session.name;
    options.push(item);
  }
  select.replaceChildren(...options);
  if (sessions.some((session) => session.name === current && session.analyzed)) {
    select.value = current;
  }
}

export function fillBaselineSelect(select, sessions) {
  const current = select.value;
  const option = document.createElement("option");
  option.value = "";
  option.textContent = "Без базовой сессии";
  const options = [option];
  const names = [];
  for (const session of sessions) {
    if (session.status !== "valid" || session.summary?.session_type !== "self_noise") continue;
    const item = document.createElement("option");
    item.value = session.name;
    item.textContent = session.name;
    options.push(item);
    names.push(session.name);
  }
  if (names.length === 0) {
    option.textContent = "Нет самошумных сессий — запишите захват с флажком «Самошум»";
  }
  select.replaceChildren(...options);
  if (names.includes(current)) {
    select.value = current;
  }
}

export function syncCaptureBaselineState(form) {
  const checkbox = form.elements.namedItem("self_noise");
  const select = form.elements.namedItem("baseline_session");
  if (!checkbox || !select) return;
  if (checkbox.disabled) return;
  if (checkbox.checked) {
    select.disabled = true;
    select.value = "";
  } else {
    select.disabled = false;
  }
}

export function syncCaptureInputState(form) {
  const inputSelect = form.elements.namedItem("input");
  if (!inputSelect) return;
  const transformer = inputSelect.value === "transformer";
  const channels = form.elements.namedItem("channels");
  if (channels) {
    if (transformer) channels.value = "1";
    channels.disabled = transformer;
  }
  const selfNoise = form.elements.namedItem("self_noise");
  if (selfNoise) {
    if (transformer) selfNoise.checked = false;
    selfNoise.disabled = transformer;
  }
  const baseline = form.elements.namedItem("baseline_session");
  if (baseline) {
    if (transformer) baseline.value = "";
    baseline.disabled = transformer;
  }
}

function applyFormDefaults(form, defaults) {
  if (!defaults || typeof defaults !== "object") return;
  for (const [name, value] of Object.entries(defaults)) {
    const field = form.elements.namedItem(name);
    if (!field || value === null || value === undefined) continue;
    if (field instanceof HTMLInputElement && field.type === "checkbox") {
      field.checked = Boolean(value);
    } else {
      field.value = String(value);
    }
  }
}

export function applyConfig(root, elements, config) {
  const sessionRoot = config.root ?? config.session_root ?? "не указан";
  elements.configRoot.textContent = `Каталог: ${sessionRoot}`;
  elements.configRoot.title = String(sessionRoot);
  const path = root.querySelector(".session-path");
  if (path) path.textContent = String(sessionRoot);

  const profileSelect = elements.simulateForm.elements.profile;
  if (Array.isArray(config.profiles) && config.profiles.length > 0) {
    const options = [];
    for (const profile of config.profiles) {
      const value = typeof profile === "string" ? profile : profile?.name ?? profile?.id ?? profile?.value;
      if (value === null || value === undefined) continue;
      const option = document.createElement("option");
      option.value = String(value);
      option.textContent = String(value);
      options.push(option);
    }
    if (options.length > 0) profileSelect.replaceChildren(...options);
  }
  const defaults = config.defaults ?? {};
  applyFormDefaults(elements.simulateForm, defaults.simulate ?? defaults);
  applyFormDefaults(elements.captureForm, defaults.capture ?? defaults);
}

export function requestFromForm(form, kind) {
  const request = { kind };
  const data = new FormData(form);
  for (const [name, rawValue] of data.entries()) {
    if (name === "self_noise") continue;
    const value = String(rawValue).trim();
    if (value === "") continue;
    request[name] = NUMBER_FIELDS.has(name) ? Number(value) : value;
  }
  if (kind === "capture") {
    request.self_noise = data.has("self_noise");
    if (request.input === "transformer") request.channels = 1;
  }
  return request;
}

export function compareRequest(form) {
  const data = new FormData(form);
  return {
    kind: "compare",
    session_a: String(data.get("session_a")),
    session_b: String(data.get("session_b")),
  };
}
