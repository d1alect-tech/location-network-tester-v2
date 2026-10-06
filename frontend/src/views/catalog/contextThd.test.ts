/** THD-V инспектора: сравнение с пределом фактическими словами.
 * Оценочных слов («норма», «годен») в текстах блока нет вообще. */

import { describe, expect, it } from "vitest";
import { EMPTY_METRICS, type SessionMetrics } from "./contextMetrics";
import {
  renderThdBlock,
  thdBadgeText,
  thdBarScale,
  thdCaptionText,
  thdCompareOf,
} from "./contextThd";

function metrics(partial: Partial<SessionMetrics>): SessionMetrics {
  return { ...EMPTY_METRICS, ...partial };
}

describe("thdCompareOf", () => {
  it("выше предела при достаточных окнах", () => {
    expect(thdCompareOf(metrics({ thdRatio: 0.089, cycles: 930 }))).toBe("above");
  });

  it("ниже предела на границе включительно", () => {
    expect(thdCompareOf(metrics({ thdRatio: 0.08, cycles: 100 }))).toBe("below");
  });

  it("мало окон — сравнение не выдаётся", () => {
    expect(thdCompareOf(metrics({ thdRatio: 0.2, cycles: 99 }))).toBe("few");
    expect(thdCompareOf(metrics({ thdRatio: 0.2, cycles: null }))).toBe("few");
  });

  it("нет значения — нет данных", () => {
    expect(thdCompareOf(EMPTY_METRICS)).toBe("none");
  });
});

describe("тексты блока", () => {
  it("бейдж описывает положение относительно предела", () => {
    expect(thdBadgeText("above")).toBe("выше предела 8 %");
    expect(thdBadgeText("below")).toBe("ниже предела 8 %");
    expect(thdBadgeText("few")).toBe("окон гармоник меньше 100");
    expect(thdBadgeText("none")).toBe("нет данных");
  });

  it("ни один текст блока не содержит оценочных слов", () => {
    const compares = ["above", "below", "few", "none"] as const;
    for (const compare of compares) {
      expect(thdBadgeText(compare)).not.toMatch(/норм|годен/iu);
      expect(thdCaptionText(EMPTY_METRICS, compare)).not.toMatch(/норм|годен/iu);
    }
  });

  it("подпись называет порог интерфейса и число окон", () => {
    const caption = thdCaptionText(metrics({ thdRatio: 0.037, cycles: 620 }), "below");
    expect(caption).toContain("Предел 8 % — порог интерфейса");
    expect(caption).toContain("Окон проанализировано: 620");
    const none = thdCaptionText(EMPTY_METRICS, "none");
    expect(none).toContain("пропущенное не подменяется нулём");
  });
});

describe("renderThdBlock", () => {
  it("полоса масштабируется к двойному пределу, метка предела на середине", () => {
    const block = renderThdBlock(metrics({ thdRatio: 0.08, cycles: 200 }));
    expect(block.getAttribute("data-thd-compare")).toBe("below");
    const fill = block.querySelector<HTMLElement>(".thd-bar-fill");
    expect(fill?.style.transform).toBe("scaleX(0.500)");
    expect(block.querySelector(".thd-limit-mark")).not.toBeNull();
  });

  it("без значения полоса пуста и значение подписано «недоступно»", () => {
    const block = renderThdBlock(EMPTY_METRICS);
    expect(block.querySelector(".thd-value")?.textContent).toBe("недоступно");
    expect(block.querySelector<HTMLElement>(".thd-bar-fill")?.style.transform).toBe(
      "scaleX(0.000)",
    );
    expect(thdBarScale(null)).toBe(0);
  });

  it("значение сверх шкалы не растягивает полосу дальше единицы", () => {
    expect(thdBarScale(0.5)).toBe(1);
  });
});
