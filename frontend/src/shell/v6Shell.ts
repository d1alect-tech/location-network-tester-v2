import "./v6Shell.css";
import { el } from "../components/primitives/dom";
import { navIcon } from "./navIcons";

export const V6_ROUTES = [
  "catalog",
  "capture",
  "inspect",
  "experiments",
  "reports",
  "settings",
] as const;

export type V6Route = (typeof V6_ROUTES)[number];

const TITLES = {
  catalog: "Каталог",
  capture: "Захват",
  inspect: "Инспекция",
  experiments: "Эксперименты",
  reports: "Отчёты",
  settings: "Настройки",
} as const satisfies Record<V6Route, string>;

export type V6ShellHeaderOpts = {
  readonly activeRoute: string;
};

export type V6ShellHeader = {
  readonly root: HTMLElement;
  setActiveRoute(route: string): void;
  setDeviceStatus(text: string): void;
};

export type V6ShellStatusbar = {
  readonly root: HTMLElement;
};

function applyActive(links: readonly HTMLAnchorElement[], route: string): void {
  for (const link of links) {
    const on = link.dataset.route === route;
    link.classList.toggle("is-active", on);
    if (on) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  }
}

export function createV6ShellHeader(opts: V6ShellHeaderOpts): V6ShellHeader {
  const links: HTMLAnchorElement[] = [];
  const nav = el("nav", { className: "tabbar", attrs: { "aria-label": "Разделы" } });
  for (const route of V6_ROUTES) {
    const label = TITLES[route];
    // Пункт «Иконки-ярлыки»: глиф + короткий ярлык; aria-label держит имя
    // пункта и на узком вьюпорте, где ярлык скрыт (иконка aria-hidden).
    const link = el(
      "a",
      {
        className: "snav-item",
        attrs: {
          id: `nav-${route}`,
          href: `#/${route}`,
          "data-route": route,
          title: label,
          "aria-label": label,
        },
      },
      [navIcon(route), el("span", { className: "lbl", text: label })],
    );
    links.push(link);
    nav.append(link);
  }
  applyActive(links, opts.activeRoute);
  const device = el("span", { className: "hdr-status", text: "устройство · готов" });
  const root = el("header", { className: "hdr" }, [
    el("span", { className: "hdr-brand", text: "LNT" }),
    nav,
    device,
  ]);

  // Вход таббара: класс is-entering держит активный пункт до animationend,
  // поэтому первое разрешение маршрута (холодный диплинк разбирает URL до
  // первой отрисовки) переносит вход без обрыва затухания, а клики по
  // вкладкам после первой отрисовки вход не повторяют.
  let enteringLink: HTMLAnchorElement | null = null;
  let enteringOff: (() => void) | null = null;
  function markEntering(link: HTMLAnchorElement): void {
    if (enteringLink === link) return;
    enteringOff?.();
    enteringLink?.classList.remove("is-entering");
    enteringLink = link;
    link.classList.add("is-entering");
    const abort = new AbortController();
    link.addEventListener(
      "animationend",
      () => {
        link.classList.remove("is-entering");
        if (enteringLink === link) enteringLink = null;
      },
      { once: true, signal: abort.signal },
    );
    enteringOff = () => abort.abort();
  }
  const linkOf = (route: string): HTMLAnchorElement | null =>
    links.find((link) => link.dataset.route === route) ?? null;

  // Монтажное окно закрывается после первой отрисовки (двойной rAF), а не на
  // первой смене маршрута: до отрисовки смена переносит вход, после — клик.
  let mounted = true;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      mounted = false;
      // reduced-motion: animationend не придёт (animation: none) — класс входа
      // снимаем вместе с монтажным окном, он уже ничего не рисует.
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        enteringOff?.();
        enteringLink?.classList.remove("is-entering");
        enteringLink = null;
      }
    });
  });

  const initial = linkOf(opts.activeRoute);
  if (initial !== null) markEntering(initial);

  let current = opts.activeRoute;
  return {
    root,
    setActiveRoute(route: string): void {
      const changed = route !== current;
      current = route;
      applyActive(links, route);
      if (changed && mounted) {
        const active = linkOf(route);
        if (active !== null) markEntering(active);
      }
    },
    setDeviceStatus(text: string): void {
      device.textContent = text;
    },
  };
}

export function createV6ShellStatusbar(): V6ShellStatusbar {
  return {
    root: el(
      "footer",
      {
        className: "statusbar",
        attrs: { role: "status", "aria-label": "Состояние приложения" },
      },
      [
        el("span", { className: "statusbar-item", text: "готов" }),
        el("span", { className: "statusbar-spacer" }),
        el("span", { className: "statusbar-item", text: "Корень: …" }),
      ],
    ),
  };
}
