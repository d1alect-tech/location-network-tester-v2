/** Шапка и приглашение «Отчётов»: заголовок на всю ширину над панелями,
 * пустая правая панель — оформленное приглашение, а не пустота.
 * V6-токены committed-волны сохранены: placeholder-title на заголовке и
 * lnt-helper-text на описании, .view-title/.view-desc — структурные хуки. */

import { el } from "../../components/primitives/dom";

export function createReportsHeader(): HTMLElement {
  return el("div", { className: "lnt-rep-header" }, [
    el("h2", { className: "placeholder-title view-title", text: "Отчёты" }),
    el("p", {
      className: "lnt-helper-text view-desc",
      text: "Отчёт собирается из существующих данных бэкенда: statistics-runs, детали сессий, рецепты. Готового HTTP-маршрута отчётов нет — выгрузка формируется клиентом из тех же данных, что показаны в превью.",
    }),
  ]);
}

export function createReportsInvitation(): HTMLElement {
  return el("div", { className: "lnt-rep-invitation" }, [
    el("p", {
      className: "lnt-helper-text",
      text: "Выберите эксперимент слева, затем соберите отчёт: превью покажет provenance, единицы, N, плоскости измерения и ограничения.",
    }),
  ]);
}
