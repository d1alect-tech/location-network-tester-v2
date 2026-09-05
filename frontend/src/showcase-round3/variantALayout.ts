/** Макет R3-A «Стойка» как переиспользуемая функция: сам вариант и типолаба
 *  монтируют один и тот же DOM, различие — только классы/токены на body. */
import {
  buildChannelBar,
  buildControlGroup,
  buildDeltaBadges,
  buildPeakTable,
  buildStatusBar,
  buildVerdicts,
  h,
} from "./kit";
import { buildSpectrumPanel } from "./spectrumPanel";

/** Монтирует стойку в #app; body-классы вешает вызывающий. */
export function mountVariantA(app: HTMLElement): void {
  const rack = h("aside", "rack", { "aria-label": "Контролы" }, [
    buildControlGroup("Пара", ["A — активная", "B — опорная", "Поменять местами"]),
    buildControlGroup("Маркеры", ["Пик", "Следующий пик", "Δ-маркер", "В таблицу"]),
    buildControlGroup("Трейсы", ["Average", "Max-Hold", "Min-Hold"]),
    buildControlGroup("Лимиты", ["Маска «розетка-порог»", "Margin ±2 дБ", "Из трейса B"]),
  ]);

  app.append(
    h("div", "app", { "data-showcase": "shell" }, [
      buildChannelBar(),
      h("div", "body", {}, [
        h("div", "center", {}, [
          h("div", "row-delta", {}, [
            buildDeltaBadges("line"),
            h("span", "bar-spacer", {}),
            buildVerdicts(),
          ]),
          buildSpectrumPanel({ traceA: "#3ec9e6", traceB: "#e6a13c" }),
          buildPeakTable(),
        ]),
        rack,
      ]),
      buildStatusBar(),
    ]),
  );
}
