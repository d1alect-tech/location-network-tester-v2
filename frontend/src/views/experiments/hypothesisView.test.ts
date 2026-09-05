/** U2: reload failure shows error + retry instead of bare «Список недоступен». */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import type { CursorPage, HypothesisRecord } from "../../api/types-research";
import { HypothesisView } from "./hypothesisView";

const RECORD: HypothesisRecord = {
  schema_version: 1,
  hypothesis_id: "h.260101.001",
  revision: 1,
  statement: "Пик на 22 кГц связан с фронтендом",
  mechanism: "Наводка по питанию",
  status: "draft",
};

function mockClient(
  hypotheses: (query?: unknown) => Promise<CursorPage<HypothesisRecord>>,
): Pick<LntApiClient, "research"> {
  return {
    research: { hypotheses },
  } as unknown as Pick<LntApiClient, "research">;
}

describe("HypothesisView reload", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("shows an error with retry when the hypothesis list fails to load", async () => {
    // Given: список гипотез недоступен.
    const hypotheses = vi.fn(async (): Promise<CursorPage<HypothesisRecord>> => {
      throw new Error("offline");
    });
    const view = new HypothesisView({ client: mockClient(hypotheses) });
    document.body.append(view.root);

    // When: начальная загрузка проваливается.
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    // Then: вместо голого «недоступен» — ошибка с причиной и кнопка повтора.
    const text = view.root.textContent ?? "";
    expect(text).toContain("недоступен");
    expect(text).toContain("offline");
    const retry = [...view.root.querySelectorAll("button")].find(
      (button) => button.textContent === "Повторить",
    );
    expect(retry).toBeInstanceOf(HTMLButtonElement);
  });

  it("retry reloads the hypothesis list", async () => {
    // Given: первая попытка проваливается, повтор успешен.
    let calls = 0;
    const hypotheses = vi.fn(async (): Promise<CursorPage<HypothesisRecord>> => {
      calls += 1;
      if (calls === 1) throw new Error("offline");
      return { items: [RECORD], next_cursor: null };
    });
    const view = new HypothesisView({ client: mockClient(hypotheses) });
    document.body.append(view.root);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(calls).toBe(1);

    // When: оператор нажимает «Повторить».
    const retry = [...view.root.querySelectorAll("button")].find(
      (button) => button.textContent === "Повторить",
    ) as HTMLButtonElement;
    expect(retry).toBeInstanceOf(HTMLButtonElement);
    retry.click();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    // Then: список загружен и отображён, ошибка ушла.
    expect(calls).toBe(2);
    expect(view.root.textContent ?? "").toContain(RECORD.statement);
    expect(view.root.querySelector("ul.lnt-exp-hypothesis-list")).not.toBeNull();
    const retries = [...view.root.querySelectorAll("button")].filter(
      (button) => button.textContent === "Повторить",
    );
    expect(retries).toHaveLength(0);
  });
});
