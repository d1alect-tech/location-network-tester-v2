/** Точка входа стенда бенча спектрограммы: монтирует продуктовую панель-эксплорер
 *  (charts/register.ts) в пустую страницу, чтобы бенч мерил рендер тайла, а не
 *  хром инспекции. Готовность объявляется флагом на window для Playwright. */

import { mountInspectSpectrogram } from "../src/components/charts/register";
import "../src/style.css";

interface BenchWindow extends Window {
  spectrogramBenchReady?: boolean;
}

const host = document.getElementById("panel-host");
if (!(host instanceof HTMLElement)) throw new Error("нет #panel-host");

mountInspectSpectrogram(host);
(window as unknown as BenchWindow).spectrogramBenchReady = true;
