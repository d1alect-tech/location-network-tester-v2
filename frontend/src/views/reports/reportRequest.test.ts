import { describe, expect, it } from "vitest";
import { groupedInProtocolOrder } from "./reportRequest";

describe("groupedInProtocolOrder", () => {
  it("preserves an empty declared condition so later protocol roles cannot shift", () => {
    const groups = groupedInProtocolOrder({ orderedConditions: ["a1", "b", "a2"] }, [
      { session_id: "session-a1", condition_id: "a1", order: 1 },
      { session_id: "session-a2", condition_id: "a2", order: 2 },
    ]);

    expect(groups).toEqual([["session-a1"], [], ["session-a2"]]);
  });
});
