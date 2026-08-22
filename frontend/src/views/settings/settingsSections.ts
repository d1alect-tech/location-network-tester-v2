/** Статические секции и рендеры данных рабочей области «Настройки».
 * Только построение DOM из готовых данных и констант модели: без сети,
 * без состояния, без слушателей — интерактив остаётся в settingsWorkspace. */

import { el } from "../../components/primitives/dom";
import { privacyGroups, supportBundleGuidance } from "./settingsModel";

const DEVICE_STATE_TONES: Record<string, string> = {
  ready: "ok",
  running_vid: "warn",
  device_absent: "info",
};

export interface DeviceStateLike {
  state: string;
  description_ru: string;
  recovery_action_ru: string;
}

export interface PreflightFindingLike {
  severity: string;
  code: string;
  message_ru: string;
  recovery_action_ru: string;
}

export interface PreflightReportLike {
  ready: boolean;
  findings: PreflightFindingLike[];
}

export function errorBlock(text: string): HTMLElement {
  return el("p", { className: "lnt-set-error", attrs: { role: "alert" }, text });
}

export function renderDeviceState(state: DeviceStateLike): HTMLElement {
  return el(
    "div",
    {
      className: `lnt-set-device-state lnt-set-tone-${DEVICE_STATE_TONES[state.state] ?? "info"}`,
      attrs: { "data-device-state": state.state, role: "status" },
    },
    [
      el("p", { className: "lnt-set-device-title", text: `Состояние: ${state.state}` }),
      el("p", { text: state.description_ru }),
      el("p", {
        className: "lnt-set-recovery",
        text: `Что делать: ${state.recovery_action_ru}`,
      }),
    ],
  );
}

export function renderPreflight(report: PreflightReportLike): HTMLElement {
  const findings = el("ul", {
    className: "lnt-set-preflight-findings",
    attrs: { "aria-label": "Замечания предстартовой проверки" },
  });
  for (const finding of report.findings) {
    findings.append(
      el("li", {
        className: finding.severity === "block" ? "lnt-set-finding-block" : "lnt-set-finding-warn",
        text: `${finding.severity === "block" ? "Блокирует" : "Предупреждение"} · ${finding.code}: ${finding.message_ru} Что делать: ${finding.recovery_action_ru}`,
      }),
    );
  }
  if (report.findings.length === 0) {
    findings.append(el("li", { text: "Замечаний нет." }));
  }
  return el("div", {}, [
    el("p", {
      className: report.ready ? "lnt-set-ready-ok" : "lnt-set-ready-blocked",
      attrs: { role: "status" },
      text: report.ready
        ? "Захват готов к запуску."
        : "Захват заблокирован: устраните замечания с пометкой «Блокирует».",
    }),
    findings,
  ]);
}

export function buildBundleSection(): HTMLElement {
  const guidance = supportBundleGuidance();
  return el("section", { className: "lnt-set-section lnt-set-bundle-guidance" }, [
    el("h3", { className: "lnt-exp-subtitle", text: "Журналы и сборник поддержки" }),
    el("p", {
      className: "lnt-set-honest-note",
      text: "Кнопки сборки в панели нет: бэкенд не предоставляет HTTP-маршрут для сборника поддержки. Сборник собирается командой CLI:",
    }),
    el("pre", { className: "lnt-set-command", text: guidance.command }),
    el("ul", { className: "lnt-set-flags" }, [
      ...guidance.flags.map((flag) =>
        el("li", {}, [el("code", { text: flag.flag }), el("span", { text: ` — ${flag.detail}` })]),
      ),
    ]),
    el("p", { className: "lnt-helper-text", text: "Состав сборника:" }),
    el("ul", { className: "lnt-set-contents" }, [
      ...guidance.contents.map((item) => el("li", { text: item })),
    ]),
    el("p", { className: "lnt-helper-text", text: guidance.manifestNote }),
  ]);
}

export function buildPrivacySection(): HTMLElement {
  return el("section", { className: "lnt-set-section lnt-set-privacy" }, [
    el("h3", { className: "lnt-exp-subtitle", text: "Приватность: что собирается" }),
    ...privacyGroups().map((group) =>
      el("div", { className: `lnt-set-privacy-group lnt-set-privacy-${group.id}` }, [
        el("h4", { className: "lnt-set-privacy-title", text: group.title }),
        el("p", { className: "lnt-helper-text", text: group.intro }),
        el("dl", { className: "lnt-rep-grid" }, [
          ...group.items.flatMap((item) => [
            el("dt", { text: item.key }),
            el("dd", { text: item.detail }),
          ]),
        ]),
      ]),
    ),
  ]);
}
