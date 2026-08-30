import { describe, expect, it } from "vitest";
import { createV6ShellHeader, createV6ShellStatusbar } from "./v6Shell";

const TAB_ROUTES = [
  "catalog",
  "capture",
  "inspect",
  "experiments",
  "reports",
  "settings",
] as const;

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

  it("clears aria-current when setActiveRoute is prepare", () => {
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
});
