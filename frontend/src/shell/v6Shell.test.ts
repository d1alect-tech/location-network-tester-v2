import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { createV6ShellHeader, createV6ShellStatusbar } from "./v6Shell";

const TAB_ROUTES = ["catalog", "capture", "inspect", "experiments", "reports", "settings"] as const;

const TITLES: Record<(typeof TAB_ROUTES)[number], string> = {
  catalog: "Каталог",
  capture: "Захват",
  inspect: "Инспекция",
  experiments: "Эксперименты",
  reports: "Отчёты",
  settings: "Настройки",
};

/** Реальный CSS оболочки: корень vitest — frontend/, запуск из репо тоже. */
function readShellCss(): string {
  const roots = [resolve(process.cwd(), "src/shell"), resolve(process.cwd(), "frontend/src/shell")];
  for (const root of roots) {
    const path = resolve(root, "v6Shell.css");
    if (existsSync(path)) return readFileSync(path, "utf8");
  }
  throw new Error("не найден v6Shell.css");
}

function ruleBody(css: string, selector: string): string {
  const match = new RegExp(`${selector.replace(/[.[\]{}()*+?/^$|\\]/g, "\\$&")}\\s*{([^}]*)}`).exec(
    css,
  );
  expect(match, `нет правила ${selector}`).not.toBeNull();
  return (match?.[1] ?? "").trim();
}

describe("createV6ShellHeader", () => {
  it("builds header.hdr with brand LNT and six tab links in route order", () => {
    // Given / When
    const { root } = createV6ShellHeader({ activeRoute: "inspect" });

    // Then
    expect(root.tagName).toBe("HEADER");
    expect(root.classList.contains("hdr")).toBe(true);
    expect(root.querySelector(".hdr-brand")?.textContent).toBe("LNT");

    const links = [...root.querySelectorAll(".tabbar a.snav-item")];
    expect(links).toHaveLength(6);
    expect(links.map((link) => link.getAttribute("data-route"))).toEqual([...TAB_ROUTES]);
    expect(links.map((link) => link.id)).toEqual(TAB_ROUTES.map((route) => `nav-${route}`));
    expect(links.map((link) => link.getAttribute("href"))).toEqual(
      TAB_ROUTES.map((route) => `#/${route}`),
    );
    // Supersession: ярлык живёт в .lbl пункта «Иконки-ярлыки», textContent
    // ссылки совпадает с прежним текстовым табом — контракт имени не менялся.
    expect(links.map((link) => link.querySelector(".lbl")?.textContent)).toEqual(
      TAB_ROUTES.map((route) => TITLES[route]),
    );
    expect(root.querySelector('a[href="#/prepare"]')).toBeNull();
  });

  it("marks the active tab with aria-current=page and is-active", () => {
    // Given / When
    const { root } = createV6ShellHeader({ activeRoute: "inspect" });

    // Then
    const inspect = root.querySelector("#nav-inspect");
    expect(inspect?.getAttribute("aria-current")).toBe("page");
    expect(inspect?.classList.contains("is-active")).toBe(true);
    expect(root.querySelectorAll('.tabbar a.snav-item[aria-current="page"]')).toHaveLength(1);
    expect(root.querySelector("#nav-catalog")?.classList.contains("is-active")).toBe(false);
  });

  it("clears aria-current for a route without a tab (killed legacy prepare)", () => {
    // Given
    const header = createV6ShellHeader({ activeRoute: "inspect" });

    // When
    header.setActiveRoute("prepare");

    // Then
    expect(header.root.querySelectorAll('[aria-current="page"]')).toHaveLength(0);
  });

  it("moves the active tab when setActiveRoute switches to catalog", () => {
    // Given
    const header = createV6ShellHeader({ activeRoute: "inspect" });

    // When
    header.setActiveRoute("catalog");

    // Then
    const catalog = header.root.querySelector("#nav-catalog");
    const inspect = header.root.querySelector("#nav-inspect");
    expect(catalog?.getAttribute("aria-current")).toBe("page");
    expect(catalog?.classList.contains("is-active")).toBe(true);
    expect(inspect?.getAttribute("aria-current")).toBeNull();
    expect(inspect?.classList.contains("is-active")).toBe(false);
  });

  it("replaces .hdr-status text when setDeviceStatus is called", () => {
    // Given
    const header = createV6ShellHeader({ activeRoute: "inspect" });
    const status = header.root.querySelector(".hdr-status");
    expect(status).not.toBeNull();

    // When
    header.setDeviceStatus("Hantek 6022BE · запись");

    // Then
    expect(status?.textContent).toBe("Hantek 6022BE · запись");
  });
});

describe("таббар «Иконки-ярлыки» (todo 7 ui-refactor)", () => {
  it("каждый пункт несёт глиф .ico и ярлык .lbl с именем маршрута", () => {
    // Given / When
    const { root } = createV6ShellHeader({ activeRoute: "catalog" });

    // Then
    for (const route of TAB_ROUTES) {
      const link = root.querySelector(`#nav-${route}`);
      expect(link, `пункт ${route}`).not.toBeNull();
      const icon = link?.querySelector("svg.ico");
      expect(icon, `глиф ${route} — инлайн-SVG`).not.toBeNull();
      expect(icon?.getAttribute("aria-hidden")).toBe("true");
      expect(link?.querySelector(".lbl")?.textContent).toBe(TITLES[route]);
      // Имя пункта держат title и aria-label: на узком вьюпорте ярлык скрыт.
      expect(link?.getAttribute("title")).toBe(TITLES[route]);
      expect(link?.getAttribute("aria-label")).toBe(TITLES[route]);
    }
  });

  it("data-mount живёт до первой реальной смены маршрута", () => {
    // Given: входная анимация привязана к монтажу оболочки.
    const header = createV6ShellHeader({ activeRoute: "catalog" });
    expect(header.root.hasAttribute("data-mount")).toBe(true);

    // When: повтор того же маршрута (init вызывает setActiveRoute тем же маршрутом).
    header.setActiveRoute("catalog");

    // Then: вход не гаснет от служебного вызова.
    expect(header.root.hasAttribute("data-mount")).toBe(true);

    // When: реальная смена.
    header.setActiveRoute("reports");

    // Then: replay входа на частом действии невозможен.
    expect(header.root.hasAttribute("data-mount")).toBe(false);
  });

  it("worst-case: длинный ярлык остаётся в .lbl и не меняет имя пункта", () => {
    // Given
    const { root } = createV6ShellHeader({ activeRoute: "catalog" });
    const link = root.querySelector("#nav-experiments") as HTMLAnchorElement;
    const lbl = link.querySelector(".lbl") as HTMLElement;

    // When: ярлык длиннее предела эллипсиса (маршрут не добавляем).
    lbl.textContent = "Прослеживаемость измерений и калибровочные коэффициенты стенда";

    // Then: имя пункта (title/aria-label) не следует за переполненным ярлыком.
    expect(lbl.textContent).toBe("Прослеживаемость измерений и калибровочные коэффициенты стенда");
    expect(link.getAttribute("title")).toBe(TITLES.experiments);
    expect(link.getAttribute("aria-label")).toBe(TITLES.experiments);
  });

  it("CSS: тон без геометрии — font-weight не переключается между состояниями", () => {
    // Given
    const css = readShellCss();

    // Then: ни базовое, ни активное правило пункта шапки не трогают font-weight —
    // смена вкладки не двигает геометрию соседей (замер e2e: 0px).
    expect(ruleBody(css, ".hdr .tabbar .snav-item")).not.toMatch(/font-weight/);
    expect(ruleBody(css, ".hdr .tabbar .snav-item.is-active")).not.toMatch(/font-weight/);
    // Активная подложка — токен тона, не разовый цвет.
    expect(ruleBody(css, ".hdr .tabbar .snav-item.is-active")).toContain("var(--lnt-accent-tint)");
  });

  it("CSS: вход только под data-mount и гасится prefers-reduced-motion", () => {
    // Given
    const css = readShellCss();

    // Then: анимация входа привязана к монтажу, у активного пункта её нет.
    expect(ruleBody(css, ".hdr .tabbar .snav-item.is-active")).not.toMatch(/animation/);
    expect(ruleBody(css, ".hdr[data-mount] .tabbar .snav-item.is-active")).toContain("lnt-nav-in");
    expect(ruleBody(css, ".hdr[data-mount] .tabbar .snav-item.is-active")).toContain(
      "var(--lnt-t-mount)",
    );
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(reduced).toContain(".hdr[data-mount] .tabbar .snav-item.is-active");
    expect(reduced).toMatch(/animation:\s*none/);
  });

  it("CSS: на <=767px ярлык скрыт, пункт держит тач-таргет 44px", () => {
    // Given
    const css = readShellCss();
    const mobile = css.slice(css.indexOf("@media (max-width: 767px)"));

    // Then
    expect(ruleBody(mobile, ".hdr .tabbar .snav-item .lbl")).toContain("display: none");
    const item = ruleBody(mobile, ".hdr .tabbar .snav-item");
    expect(item).toContain("var(--lnt-touch-target-min)");
  });
});

describe("createV6ShellStatusbar", () => {
  it("builds footer.statusbar with ready, spacer, and root path children", () => {
    // Given / When
    const { root } = createV6ShellStatusbar();

    // Then
    expect(root.tagName).toBe("FOOTER");
    expect(root.classList.contains("statusbar")).toBe(true);
    expect(root.children).toHaveLength(3);
    expect(root.children[0]?.textContent).toBe("готов");
    expect(root.children[1]?.classList.contains("statusbar-spacer")).toBe(true);
    expect(root.children[2]?.textContent).toBe("Корень: …");
  });

  it("exposes a polite live region for status changes", () => {
    // Given / When
    const { root } = createV6ShellStatusbar();

    // Then
    expect(root.getAttribute("role")).toBe("status");
    expect(root.getAttribute("aria-label")).toBe("Состояние приложения");
  });
});
