/** V6 RED-контракты раздела «Настройки» (TDD RED, T2) — test-side зеркало
 * settings.spec.ts. Эталон: showcase-round2/kit.css (панели .panel/.panel-hd/
 * .panel-title/.panel-bd, стыковка hairline). Падение — только по missing class.
 * Зелёные пины: data-device-state, role=alert, CLI-подсказка сборника. */

import { describe, expect, it } from "vitest";
import {
  buildBundleSection,
  buildPrivacySection,
  errorBlock,
  renderDeviceState,
  renderPreflight,
} from "./views/settings/settingsSections";

describe("настройки V6: панельная система", () => {
  it("секция сборника — section.panel с шапкой .panel-title и телом .panel-bd", () => {
    // Given / When
    const section = buildBundleSection();

    // Then: V6-панель kit.css (§5.2)
    expect(
      section.classList.contains("panel"),
      "V6-разрыв: сборник без section.panel (сейчас section.lnt-set-section)",
    ).toBe(true);
    expect(
      section.querySelector(".panel-hd > .panel-title, .panel-title"),
      "V6-разрыв: у панели сборника нет .panel-title",
    ).not.toBeNull();
    expect(
      section.querySelector(".panel-bd"),
      "V6-разрыв: у панели сборника нет .panel-bd",
    ).not.toBeNull();
  });

  it("секция приватности — section.panel", () => {
    // Given / When
    const section = buildPrivacySection();

    // Then
    expect(section.classList.contains("panel"), "V6-разрыв: приватность без section.panel").toBe(
      true,
    );
    expect(
      section.querySelector(".panel-title"),
      "V6-разрыв: у панели приватности нет .panel-title",
    ).not.toBeNull();
  });

  it("состояние устройства — .panel с заголовком", () => {
    // Given / When
    const node = renderDeviceState({
      state: "device_absent",
      description_ru: "Устройство не обнаружено на шине USB.",
      recovery_action_ru: "Проверьте кабель и повторите проверку.",
    });

    // Then: V6 переносит блок диагностики в панельную систему
    expect(
      node.classList.contains("panel"),
      "V6-разрыв: состояние устройства без .panel (сейчас div.lnt-set-device-state)",
    ).toBe(true);
    expect(
      node.querySelector(".panel-title"),
      "V6-разрыв: у панели диагностики нет .panel-title",
    ).not.toBeNull();
  });

  it("preflight — .panel, ошибка — .banner.banner-inline", () => {
    // Given / When
    const report = renderPreflight({
      ready: false,
      findings: [
        {
          severity: "block",
          code: "device_not_ready",
          message_ru: "Устройство не готово.",
          recovery_action_ru: "Подключите осциллограф.",
        },
      ],
    });
    const error = errorBlock("Недопустимые символы в заметке.");

    // Then
    expect(report.classList.contains("panel"), "V6-разрыв: preflight без .panel").toBe(true);
    expect(
      error.classList.contains("banner") && error.classList.contains("banner-inline"),
      "V6-разрыв: ошибка без .banner.banner-inline (сейчас p.lnt-set-error)",
    ).toBe(true);
  });
});

describe("настройки V6: пины контрактов (уже зелёные)", () => {
  it("состояние хранит data-device-state и не оформляется как ошибка", () => {
    // Given / When
    const node = renderDeviceState({
      state: "device_absent",
      description_ru: "Устройство не обнаружено на шине USB.",
      recovery_action_ru: "Проверьте кабель.",
    });

    // Then: типизированное состояние, не role=alert
    expect(node.getAttribute("data-device-state")).toBe("device_absent");
    expect(node.getAttribute("role")).not.toBe("alert");
  });

  it("ошибка остаётся role=alert, сборник — кнопки панели плюс честный CLI", () => {
    // Given / When
    const error = errorBlock("Недопустимые символы.");
    const bundle = buildBundleSection();

    // Then
    expect(error.getAttribute("role")).toBe("alert");
    expect(bundle.textContent).toContain("uv run lnt support-bundle");
    expect(bundle.querySelector("#lnt-set-backup-run")?.textContent).toContain("Создать бэкап");
    expect(bundle.querySelector("#lnt-set-bundle-run")?.textContent).toContain("Собрать сборник");
    expect(bundle.querySelector("#lnt-set-bundle-status")).toBeInstanceOf(HTMLElement);
  });
});
