/** Панель диагностики устройства и preflight: каждое состояние показывает
 * ТОЧНОЕ следующее действие на русском (подсказки Zadig с VID 04B4/04B5
 * приходят с бэкенда). Состояние кодируется текстом, не только цветом. */

import type { DeviceStatePayload, PreflightFinding, PreflightResponse } from "../api/types-device";
import { el } from "../components/primitives/dom";
import { announcePolite } from "../components/primitives/status";

/** Человекочитаемая подпись состояния цепочки драйвер → устройство → прошивка. */
const STATE_LABELS_RU: Record<DeviceStatePayload["state"], string> = {
  backend_unavailable: "Backend недоступен",
  driver_missing: "Драйвер не установлен",
  device_absent: "Устройство не найдено",
  bootloader_vid: "Загрузочный VID 04B4",
  running_vid: "Рабочий VID 04B5",
  handle_busy: "USB-handle занят",
  firmware_missing: "Прошивка не загружена",
  firmware_upload_failed: "Сбой загрузки прошивки",
  ready: "Готов к захвату",
};

export interface DevicePanelHandle {
  root: HTMLElement;
  /** Рисует состояние GET /api/device/state. */
  renderState(payload: DeviceStatePayload): void;
  /** Рисует отчёт POST /api/capture/preflight (findings block/warn). */
  renderPreflight(response: PreflightResponse): void;
}

function findingCard(finding: PreflightFinding): HTMLElement {
  const severityText = finding.severity === "block" ? "Блокирует запуск" : "Предупреждение";
  const severityClass = finding.severity === "block" ? "lnt-tone-error" : "lnt-tone-warn";
  const badge = el("span", {
    className: `lnt-status-pill ${severityClass}`,
    text: `${severityText} · ${finding.code}`,
  });
  return el("div", { className: "capture-finding" }, [
    badge,
    el("p", { className: "capture-finding-message", text: finding.message_ru }),
    el("p", {
      className: "capture-finding-action",
      text: `Что делать: ${finding.recovery_action_ru}`,
    }),
  ]);
}

export function createDevicePanel(): DevicePanelHandle {
  const stateSection = el("div", { className: "capture-device-state" });
  const findingsSection = el("div", { className: "capture-preflight-findings" });
  const root = el("section", { className: "capture-device-panel" }, [
    el("h3", { className: "capture-section-title", text: "Устройство и проверка перед записью" }),
    stateSection,
    findingsSection,
  ]);

  return {
    root,
    renderState: (payload) => {
      // Текстовое состояние + точное следующее действие из бэкенда.
      while (stateSection.firstChild) stateSection.removeChild(stateSection.firstChild);
      const pill = el("span", {
        className:
          payload.state === "ready"
            ? "lnt-status-pill lnt-tone-ok"
            : "lnt-status-pill lnt-tone-warn",
        text: STATE_LABELS_RU[payload.state],
      });
      stateSection.append(
        el("p", { className: "capture-device-line" }, [pill]),
        el("p", { className: "capture-device-desc", text: payload.description_ru }),
        el("p", {
          className: "capture-device-action",
          text: `Следующее действие: ${payload.recovery_action_ru}`,
        }),
      );
    },
    renderPreflight: (response) => {
      while (findingsSection.firstChild) findingsSection.removeChild(findingsSection.firstChild);
      const blocks = response.findings.filter((item) => item.severity === "block");
      if (response.ready && response.findings.length === 0) {
        findingsSection.append(
          el("p", {
            className: "capture-preflight-ok",
            text: "Preflight пройден: запуск безопасен.",
          }),
        );
        return;
      }
      if (response.findings.length === 0) return;
      const summary = el("p", {
        className: "capture-preflight-summary",
        text:
          blocks.length > 0
            ? `Preflight нашёл блокирующих замечаний: ${blocks.length}.`
            : "Preflight: только предупреждения.",
      });
      findingsSection.append(summary);
      for (const finding of response.findings) findingsSection.append(findingCard(finding));
      announcePolite(summary.textContent ?? "");
    },
  };
}
