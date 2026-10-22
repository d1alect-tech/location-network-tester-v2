/** Регрессия двух подтверждённых дефектов todo 8 (F1/F2 из dag/t8-verify.md).
 * Обе ветки проверяются на РЕАЛЬНЫХ артефактах кампании, скопированных в
 * fixtures/ (sha256: constant 63a0ef56…, clip-mismatch 31bea3ca…); вне
 * репозитория тест не читает ничего.
 *
 * F1: доступный спектр с нулевыми уровнями больше не называется недоступным.
 * F2: QC-строка не дублирует коды, уже показанные оценкой/счётчиками, и
 * целиком остаётся доступной в title. */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { RippleApi } from "../../../api/client-ripple";
import { isRippleArtifact } from "../../../api/guards-ripple";
import type { RippleArtifactPayload } from "../../../api/types-ripple";
import type { ChartHandle, ChartRenderRequest } from "../../../components/charts/types";
import { chartOutcome } from "./rippleChart";
import { reasonText } from "./rippleFormat";
import { buildRippleView } from "./rippleModel";
import { type RipplePanelHandle, createRipplePanel } from "./ripplePanel";

/** Путь к фикстурам от модуля, а не от cwd: тест одинаково работает из
 * корня репозитория и из frontend/. */
const FIXTURES = join(import.meta.dirname, "fixtures");
const CONSTANT = "ripple-constant-zero-spectrum";
const CLIP_MISMATCH = "ripple-clip-mismatch-qc";

/** Ёмкость двух строк слота QC: 475 px при 1280 и 10 px IBM Plex Mono
 * (измерено: 127 символов = 762 px ⇒ ≈6,0 px/символ ⇒ ≈79 символов в строке).
 * Пиксельную проверку делает rippleStability.spec.ts; здесь — дешёвый прокси. */
const QC_TWO_LINE_CAPACITY = 150;

function realArtifact(name: string): RippleArtifactPayload {
  const parsed: unknown = JSON.parse(readFileSync(join(FIXTURES, `${name}.json`), "utf8"));
  if (!isRippleArtifact(parsed)) throw new Error(`фикстура ${name} не прошла гвард ripple`);
  return parsed;
}

type FakeView = ChartHandle & { readonly requests: ChartRenderRequest[] };
const cleanups: Array<() => void> = [];

function mount(payload: RippleArtifactPayload): { panel: RipplePanelHandle; view: FakeView } {
  const api: RippleApi = { artifact: async () => payload };
  const container = document.createElement("div");
  document.body.append(container);
  let created: FakeView | null = null;
  const panel = createRipplePanel({
    api,
    createView: (options) => {
      const root = document.createElement("div");
      options.container.append(root);
      const requests: ChartRenderRequest[] = [];
      const view: FakeView = {
        root,
        requests,
        render(request) {
          requests.push(request);
        },
        applyTheme() {},
        getData: () => null,
        destroy() {},
      };
      created = view;
      return view;
    },
  });
  container.append(panel.root);
  cleanups.push(() => panel.destroy());
  if (created === null) throw new Error("chart view not created");
  return { panel, view: created };
}

function chartEmptyOf(root: HTMLElement): HTMLElement | null {
  return root.querySelector<HTMLElement>("[data-role='chart-empty']");
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  document.body.replaceChildren();
});

describe("F1: доступный спектр нулевого уровня — не «недоступен»", () => {
  it("реальный constant-артефакт: спектр доступен, 5001 бин, все уровни 0", () => {
    const artifact = realArtifact(CONSTANT);
    expect(artifact.spectrum.availability).toBe("available");
    expect(artifact.spectrum.psd_v2_per_hz).toHaveLength(5001);
    expect(artifact.spectrum.psd_v2_per_hz.every((value) => value === 0)).toBe(true);
    expect(artifact.spectrum.asd_v_per_sqrt_hz.every((value) => value === 0)).toBe(true);
  });

  it("chartOutcome различает нулевой пол и недоступность в обоих режимах", () => {
    const constant = realArtifact(CONSTANT);
    const psd = chartOutcome(constant, "psd", "#5681ff");
    expect(psd.kind).toBe("zero_floor");
    expect(psd.kind === "zero_floor" ? psd.bins : -1).toBe(5001);
    expect(chartOutcome(constant, "asd", "#5681ff").kind).toBe("zero_floor");
    expect(chartOutcome(realArtifact(CLIP_MISMATCH), "psd", "#5681ff").kind).toBe("unavailable");
  });

  it("доступный спектр без бинов и без конечных точек — отдельные честные причины", () => {
    const empty = realArtifact(CONSTANT);
    empty.spectrum.frequency_hz = [];
    empty.spectrum.psd_v2_per_hz = [];
    empty.spectrum.asd_v_per_sqrt_hz = [];
    expect(chartOutcome(empty, "psd", "#5681ff").kind).toBe("no_bins");
    const broken = realArtifact(CONSTANT);
    broken.spectrum.psd_v2_per_hz = [-1, -2, -3];
    broken.spectrum.asd_v_per_sqrt_hz = [-1, -2, -3];
    broken.spectrum.frequency_hz = [1, 2, 3];
    expect(chartOutcome(broken, "psd", "#5681ff").kind).toBe("no_log_points");
  });

  it("панель: reason=zero_floor, подпись без «недоступ», availability видна на корне", async () => {
    const { panel, view } = mount(realArtifact(CONSTANT));
    await panel.setPair("ripple-real-constant");
    expect(panel.root.dataset.state).toBe("ready");
    expect(panel.root.dataset.spectrum).toBe("available");
    expect(view.requests).toHaveLength(0);
    const empty = chartEmptyOf(panel.root);
    expect(empty?.dataset.reason).toBe("zero_floor");
    expect(empty?.textContent ?? "").not.toContain("недоступ");
    expect(empty?.textContent ?? "").toContain("0");
    expect(empty?.title ?? "").not.toContain("недоступ");
  });

  it("ни -Infinity, ни NaN не сериализуются в DOM, data-value и title", async () => {
    const { panel } = mount(realArtifact(CONSTANT));
    await panel.setPair("ripple-real-constant");
    expect(panel.root.outerHTML).not.toContain("Infinity");
    expect(panel.root.outerHTML).not.toContain("NaN");
    for (const node of panel.root.querySelectorAll<HTMLElement>("[data-value]")) {
      const raw = node.getAttribute("data-value") ?? "";
      expect(raw === "null" || Number.isFinite(Number(raw)), `data-value=${raw}`).toBe(true);
    }
    for (const node of panel.root.querySelectorAll<HTMLElement>("[title]")) {
      expect(node.title).not.toMatch(/Infinity|NaN/);
    }
    // Карточки доступного артефакта несут его собственные байты, не подмену.
    expect(panel.root.querySelector("[data-metric='mean']")?.getAttribute("data-value")).toBe(
      "0.05000000074505806",
    );
    expect(panel.root.querySelector("[data-metric='rms-ac']")?.getAttribute("data-value")).toBe(
      "0",
    );
    expect(panel.root.querySelector("[data-metric='band']")?.getAttribute("data-value")).toBe("0");
  });

  it("недоступный спектр по-прежнему назван недоступным с машинной причиной", async () => {
    const { panel } = mount(realArtifact(CLIP_MISMATCH));
    await panel.setPair("ripple-real-clip");
    expect(panel.root.dataset.spectrum).toBe("unavailable");
    const empty = chartEmptyOf(panel.root);
    expect(empty?.dataset.reason).toBe("unavailable");
    expect(empty?.textContent ?? "").toContain("недоступен");
    expect(empty?.textContent ?? "").toContain(reasonText("clip_census_inconsistent"));
  });
});

describe("F2: QC-строка — без дублей кодов, без потери фактов", () => {
  it("реальный clip-mismatch: код оценки не повторяется, факт остаётся видимым", () => {
    const artifact = realArtifact(CLIP_MISMATCH);
    const model = buildRippleView(artifact, 0);
    expect(artifact.qc.reason_codes).toEqual(["clipping_unknown", "clip_census_inconsistent"]);
    expect(model.qcText).not.toContain("clip_census_inconsistent");
    expect(model.qcText).toContain(reasonText("clipping_unknown"));
    expect(model.qcOmitted).toEqual(["clip_census_inconsistent"]);
    expect(model.qcCodes).toEqual(artifact.qc.reason_codes);
  });

  it("полный текст и все машинные коды доступны в title", () => {
    const artifact = realArtifact(CLIP_MISMATCH);
    const model = buildRippleView(artifact, 0);
    expect(model.qcTitle).toContain(model.qcText);
    for (const code of artifact.qc.reason_codes) expect(model.qcTitle).toContain(code);
    expect(model.qcTitle.length).toBeGreaterThan(model.qcText.length);
  });

  it("видимая строка помещается в две строки слота 475 px", () => {
    const model = buildRippleView(realArtifact(CLIP_MISMATCH), 0);
    expect(model.qcText.length).toBeGreaterThan(0);
    expect(model.qcText.length).toBeLessThanOrEqual(QC_TWO_LINE_CAPACITY);
  });

  it("constant-артефакт: кодов нет — строка короткая и ничего не прячет", () => {
    const artifact = realArtifact(CONSTANT);
    const model = buildRippleView(artifact, 0);
    expect(model.qcOmitted).toEqual([]);
    expect(model.qcCodes).toEqual([]);
    expect(model.qcText.length).toBeLessThanOrEqual(QC_TWO_LINE_CAPACITY);
  });

  it("панель отдаёт QC в data-qc-codes и data-qc-omitted", async () => {
    const { panel } = mount(realArtifact(CLIP_MISMATCH));
    await panel.setPair("ripple-real-clip");
    const qc = panel.root.querySelector<HTMLElement>("[data-ripple-qc]");
    expect(qc?.getAttribute("data-qc-codes")).toBe("clipping_unknown clip_census_inconsistent");
    expect(qc?.getAttribute("data-qc-omitted")).toBe("clip_census_inconsistent");
    expect(qc?.title ?? "").toContain("clip_census_inconsistent");
    expect(qc?.textContent ?? "").not.toContain("clip_census_inconsistent");
  });

  it("враждебные строки артефакта остаются текстом, а не разметкой", async () => {
    const artifact = realArtifact(CLIP_MISMATCH);
    const hostile = '<img src=x onerror="alert(1)">';
    artifact.qc.reason_codes = [hostile];
    const band = artifact.bands.at(0);
    if (band !== undefined) band.id = hostile;
    const { panel } = mount(artifact);
    await panel.setPair(hostile);
    expect(panel.root.querySelectorAll("img")).toHaveLength(0);
    expect(panel.root.textContent ?? "").toContain(hostile);
    expect(panel.root.querySelector<HTMLElement>("[data-ripple-qc]")?.title ?? "").toContain(
      hostile,
    );
  });
});
