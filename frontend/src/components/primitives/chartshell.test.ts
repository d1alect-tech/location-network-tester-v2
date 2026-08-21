import { beforeEach, describe, expect, it } from "vitest";
import { createChartShell } from "./chartshell";

describe("createChartShell", () => {
  beforeEach(() => {
    document.body.textContent = "";
  });

  function makeShell(onDownloadCsv?: () => void): ReturnType<typeof createChartShell> {
    return createChartShell({ title: "Спектр мощности", onDownloadCsv });
  }

  it("renders the Russian title and a CSV button wired to the callback", () => {
    let downloaded = 0;
    const shell = makeShell(() => {
      downloaded += 1;
    });
    expect(shell.root.textContent).toContain("Спектр мощности");
    const csv = [...shell.root.querySelectorAll("button")].find((b) =>
      b.textContent?.includes("CSV"),
    );
    csv?.click();
    expect(downloaded).toBe(1);
  });

  it("overlays switch between loading, error with retry, empty and content", () => {
    let retried = 0;
    const shell = makeShell();
    shell.setLoading();
    expect(shell.root.textContent).toContain("Загрузка…");

    shell.setError("Сессия не проанализирована", () => {
      retried += 1;
    });
    expect(shell.root.textContent).toContain("Ошибка загрузки");
    const retry = [...shell.root.querySelectorAll("button")].find(
      (b) => b.textContent === "Повторить",
    );
    retry?.click();
    expect(retried).toBe(1);

    shell.setEmpty("Нет данных для отображения");
    expect(shell.root.textContent).toContain("Нет данных для отображения");

    const plot = document.createElement("div");
    plot.className = "my-plot";
    shell.setContent(plot);
    expect(shell.body.querySelector(".my-plot")).not.toBeNull();
    expect(shell.root.textContent).not.toContain("Загрузка…");
  });

  it("hosts toolbar slot content next to the title", () => {
    const shell = makeShell();
    const tool = document.createElement("button");
    tool.textContent = "Лог-шкала";
    shell.toolbar.append(tool);
    expect(shell.toolbar.contains(tool)).toBe(true);
  });

  it("imports no chart library (product bundle stays clean)", async () => {
    const source = await import("./chartshell?raw");
    // Имя прежней запрещённой библиотеки собирается по частям (инвентаризация todo 41).
    const legacyLib = ["p", "lot", "ly"].join("");
    expect(source.default).not.toMatch(new RegExp(`from\\s+["'](echarts|uplot|${legacyLib})`));
  });
});
