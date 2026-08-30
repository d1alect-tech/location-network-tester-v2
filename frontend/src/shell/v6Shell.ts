import "./v6Shell.css";
import { el } from "../components/primitives/dom";

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
    const link = el("a", {
      className: "snav-item",
      text: TITLES[route],
      attrs: {
        id: `nav-${route}`,
        href: `#/${route}`,
        "data-route": route,
      },
    });
    links.push(link);
    nav.append(link);
  }
  applyActive(links, opts.activeRoute);
  const device = el("span", { className: "hdr-status", text: "устройство · готов" });
  return {
    root: el("header", { className: "hdr" }, [
      el("span", { className: "hdr-brand", text: "LNT" }),
      nav,
      device,
    ]),
    setActiveRoute(route: string): void {
      applyActive(links, route);
    },
    setDeviceStatus(text: string): void {
      device.textContent = text;
    },
  };
}

export function createV6ShellStatusbar(): V6ShellStatusbar {
  return {
    root: el("footer", { className: "statusbar" }, [
      el("span", { className: "statusbar-item", text: "готов" }),
      el("span", { className: "statusbar-spacer" }),
      el("span", { className: "statusbar-item", text: "Корень: …" }),
    ]),
  };
}
