import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";

/** Mount/unmount: размонтированная оболочка не держит слушателей
 * (matchMedia темы, hashchange маршрутов) и не реагирует на hash. */
describe("AppShell mount/unmount", () => {
  let container: HTMLElement;
  let addMedia: ReturnType<typeof vi.fn>;
  let removeMedia: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState(null, "", "/");
    window.location.hash = "";
    addMedia = vi.fn();
    removeMedia = vi.fn();
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: (() => ({
        matches: true,
        addEventListener: addMedia,
        removeEventListener: removeMedia,
      })) as unknown as typeof window.matchMedia,
    });
    container = document.createElement("div");
    container.id = "app";
    document.body.appendChild(container);
  });

  it("dispose снимает hashchange и media-подписки, повторный вызов безопасен", async () => {
    const shell = new AppShell(container);
    shell.init();
    expect(addMedia).toHaveBeenCalledWith("change", expect.any(Function));

    const removeSpy = vi.spyOn(window, "removeEventListener");
    shell.dispose();
    expect(removeSpy).toHaveBeenCalledWith("hashchange", expect.any(Function));
    expect(removeMedia).toHaveBeenCalledWith("change", expect.any(Function));
    expect(() => shell.dispose()).not.toThrow();
    removeSpy.mockRestore();

    // После размонтирования смена hash не перерисовывает представление.
    window.location.hash = "#/capture";
    await new Promise<void>((resolve) => {
      setTimeout(resolve, 0);
    });
    expect(container.querySelector(".capture-view")).toBeNull();
    shell.dispose();
  });
});
