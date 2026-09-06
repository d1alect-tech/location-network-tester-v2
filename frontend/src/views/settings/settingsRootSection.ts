import type { LntApiClient } from "../../api/client";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { createRootChoiceBlock } from "./settingsRootChoice";
import { createRootNoteBlock } from "./settingsRootNote";
import { panelSection } from "./settingsSections";

export interface RootSectionHandle {
  section: HTMLElement;
  refresh: () => Promise<void>;
}

export function createRootSection(client: LntApiClient): RootSectionHandle {
  const rootNote = createRootNoteBlock();
  const rootChoice = createRootChoiceBlock();
  const rootValue = el("code", { className: "t-mono lnt-set-root-value", text: "…" });
  const rootRetry = el("button", {
    className: "btn btn-secondary",
    text: "Повторить",
    attrs: { type: "button", id: "lnt-set-root-retry", hidden: "" },
  });
  rootRetry.addEventListener("click", () => void refresh());
  const section = panelSection(
    "Корень сессий",
    [
      el("p", { className: "t-body", text: "Фактический корень (GET /api/config):" }),
      rootValue,
      rootRetry,
      el("div", { className: "form-grid" }, [rootNote.field]),
      el("div", { className: "form-actions" }, [rootNote.saveButton]),
      el("div", { className: "form-grid" }, [rootChoice.field]),
      el("div", { className: "form-actions" }, [rootChoice.copyButton]),
    ],
    "lnt-set-root",
  );

  async function refresh(): Promise<void> {
    try {
      const config = await client.bootstrap();
      const recovered = rootRetry.getAttribute("hidden") === null;
      rootValue.textContent = config.root;
      rootValue.removeAttribute("role");
      rootRetry.setAttribute("hidden", "");
      if (recovered) announcePolite("Корень сессий загружен");
    } catch (error) {
      const message = `Корень сессий недоступен: ${error instanceof Error ? error.message : String(error)}. Проверьте, что панель запущена, и повторите.`;
      rootValue.textContent = "недоступно (сервер не отвечает)";
      rootValue.setAttribute("role", "alert");
      rootRetry.removeAttribute("hidden");
      announcePolite(message);
    }
  }

  return { section, refresh };
}
