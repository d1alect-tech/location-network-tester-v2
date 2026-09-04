/** Статические секции и рендеры данных рабочей области «Настройки».
 * V6 (D3=A): панельная система kit.css §5.2 — каждая секция строится через
 * panelSection() (section.panel > .panel-hd/.panel-title + .panel-bd).
 * Диагностика и preflight — .banner/.glyph (тон-полоса 4px заменена на
 * баннерную 3px), команда сборника — .frame/.t-mono, приватность —
 * .readout-grid. Legacy lnt-set-* классы оставлены как e2e-хуки.
 * Только построение DOM из готовых данных и констант модели: без сети,
 * без состояния, без слушателей — интерактив остаётся в settingsWorkspace. */

import { el } from "../../components/primitives/dom";
import { privacyGroups, supportBundleGuidance } from "./settingsModel";

const DEVICE_STATE_TONES: Record<string, "ok" | "warn" | "info"> = {
  ready: "ok",
  running_vid: "warn",
  device_absent: "info",
};

const DEVICE_STATE_GLYPHS: Record<string, string> = {
  ok: "●",
  warn: "▲",
  info: "○",
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

/** Каркас V6-секции: section.panel с шапкой и телом. legacyHook — e2e-хук
 * (lnt-set-section обязателен для скриншот-теста settings.spec). */
export function panelSection(
  title: string,
  body: Node[],
  legacyHook: string,
  titleTag: "h3" | "h4" = "h3",
): HTMLElement {
  return el("section", { className: `panel lnt-set-section ${legacyHook}` }, [
    el("div", { className: "panel-hd" }, [el(titleTag, { className: "panel-title", text: title })]),
    el("div", { className: "panel-bd" }, body),
  ]);
}

export function errorBlock(text: string): HTMLElement {
  return el("div", { className: "banner banner-inline lnt-set-error", attrs: { role: "alert" } }, [
    el("span", { className: "banner-glyph", text: "✕", attrs: { "aria-hidden": "true" } }),
    el("p", { className: "banner-msg", text }),
  ]);
}

export function renderDeviceState(state: DeviceStateLike): HTMLElement {
  const tone = DEVICE_STATE_TONES[state.state] ?? "info";
  const glyphClass = tone === "ok" ? "glyph-ok" : tone === "warn" ? "glyph-warn" : "";
  const root = el("div", {
    className: "panel lnt-set-device-state",
    attrs: { "data-device-state": state.state, role: "status" },
  });
  root.append(
    el("div", { className: "panel-hd" }, [
      el("h4", {
        className: "panel-title lnt-set-device-title",
        text: `Состояние: ${state.state}`,
      }),
    ]),
    el("div", { className: "panel-bd" }, [
      el("div", { className: `banner lnt-set-tone-${tone}` }, [
        el("p", { className: `glyph ${glyphClass}`.trim() }, [
          el("span", {
            className: "banner-glyph",
            text: DEVICE_STATE_GLYPHS[tone],
            attrs: { "aria-hidden": "true" },
          }),
          el("span", { text: state.description_ru }),
        ]),
        el("p", {
          className: "banner-msg lnt-set-recovery",
          text: `Что делать: ${state.recovery_action_ru}`,
        }),
      ]),
    ]),
  );
  return root;
}

export function renderPreflight(report: PreflightReportLike): HTMLElement {
  const findings = el("ul", {
    className: "lnt-set-preflight-findings",
    attrs: { "aria-label": "Замечания предстартовой проверки" },
  });
  for (const finding of report.findings) {
    const blocked = finding.severity === "block";
    findings.append(
      el(
        "li",
        {
          className: `glyph ${blocked ? "glyph-err lnt-set-finding-block" : "glyph-warn lnt-set-finding-warn"}`,
        },
        [
          el("span", {
            className: "banner-glyph",
            text: blocked ? "✕" : "▲",
            attrs: { "aria-hidden": "true" },
          }),
          el("span", {
            text: `${blocked ? "Блокирует" : "Предупреждение"} · ${finding.code}: ${finding.message_ru} Что делать: ${finding.recovery_action_ru}`,
          }),
        ],
      ),
    );
  }
  if (report.findings.length === 0) {
    findings.append(el("li", { className: "t-compact", text: "Замечаний нет." }));
  }
  const statusClass = report.ready ? "lnt-set-ready-ok" : "lnt-set-ready-blocked";
  const statusGlyph = report.ready ? "glyph-ok" : "glyph-warn";
  const root = el("div", { className: "panel lnt-set-preflight" });
  root.append(
    el("div", { className: "panel-hd" }, [
      el("h4", { className: "panel-title", text: "Готовность захвата" }),
    ]),
    el("div", { className: "panel-bd" }, [
      el("div", { className: `banner ${statusClass}`, attrs: { role: "status" } }, [
        el("p", { className: `glyph ${statusGlyph}` }, [
          el("span", {
            className: "banner-glyph",
            text: report.ready ? "●" : "▲",
            attrs: { "aria-hidden": "true" },
          }),
          el("span", {
            text: report.ready
              ? "Захват готов к запуску."
              : "Захват заблокирован: устраните замечания с пометкой «Блокирует».",
          }),
        ]),
      ]),
      findings,
    ]),
  );
  return root;
}

export function buildBundleSection(): HTMLElement {
  const guidance = supportBundleGuidance();
  return panelSection(
    "Журналы и сборник поддержки",
    [
      el("p", {
        className: "t-body lnt-set-honest-note",
        text: "Кнопки сборки в панели нет: бэкенд не предоставляет HTTP-маршрут для сборника поддержки. Сборник собирается командой CLI:",
      }),
      el("pre", { className: "frame t-mono lnt-set-command", text: guidance.command }),
      el("ul", { className: "lnt-set-flags" }, [
        ...guidance.flags.map((flag) =>
          el("li", { className: "t-body" }, [
            el("code", { className: "t-mono", text: flag.flag }),
            el("span", { text: ` — ${flag.detail}` }),
          ]),
        ),
      ]),
      el("p", { className: "t-compact", text: "Состав сборника:" }),
      el("ul", { className: "lnt-set-contents" }, [
        ...guidance.contents.map((item) => el("li", { className: "t-body", text: item })),
      ]),
      el("p", { className: "t-compact", text: guidance.manifestNote }),
    ],
    "lnt-set-bundle-guidance",
  );
}

const PRIVACY_GLYPHS: Record<string, { mark: string; glyph: string }> = {
  automatic: { mark: "●", glyph: "glyph-ok" },
  opt_in: { mark: "▲", glyph: "glyph-warn" },
  never: { mark: "✕", glyph: "glyph-err" },
};

export function buildPrivacySection(): HTMLElement {
  return panelSection(
    "Приватность: что собирается",
    privacyGroups().map((group) => {
      const marker: { mark: string; glyph: string } = PRIVACY_GLYPHS[group.id] ?? {
        mark: "●",
        glyph: "glyph-ok",
      };
      return el("div", { className: `lnt-set-privacy-group lnt-set-privacy-${group.id}` }, [
        el("h4", { className: "t-sub lnt-set-privacy-title" }, [
          el("span", {
            className: `glyph ${marker.glyph}`,
            text: marker.mark,
            attrs: { "aria-hidden": "true" },
          }),
          el("span", { text: ` ${group.title}` }),
        ]),
        el("p", { className: "t-compact", text: group.intro }),
        el("dl", { className: "readout-grid lnt-rep-grid" }, [
          ...group.items.flatMap((item) => [
            el("dt", { className: "readout-label", text: item.key }),
            el("dd", { className: "t-body", text: item.detail }),
          ]),
        ]),
      ]);
    }),
    "lnt-set-privacy",
  );
}
