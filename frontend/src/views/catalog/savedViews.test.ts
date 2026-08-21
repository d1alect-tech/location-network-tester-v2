import { describe, expect, it } from "vitest";
import { type SavedView, loadSavedViews, parseSavedViews, saveSavedViews } from "./savedViews";

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const map = new Map<string, string>(Object.entries(initial));
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key) => (map.has(key) ? (map.get(key) as string) : null),
    key: () => null,
    removeItem: (key) => void map.delete(key),
    setItem: (key, value) => void map.set(key, value),
  };
}

describe("savedViews", () => {
  it("returns an empty list for missing or corrupted storage", () => {
    expect(loadSavedViews(memoryStorage())).toEqual([]);
    expect(parseSavedViews(null)).toEqual([]);
    expect(parseSavedViews("не JSON")).toEqual([]);
    expect(parseSavedViews(JSON.stringify({ name: "не массив" }))).toEqual([]);
  });

  it("round-trips named filter sets and drops invalid entries", () => {
    const storage = memoryStorage();
    const views: SavedView[] = [
      { name: "Самошум стенд-А", filters: { health: "ok", label: "самошум" } },
      { name: "Повреждённые", filters: { health: "corrupt_manifest" } },
    ];
    saveSavedViews(storage, views);
    expect(loadSavedViews(storage)).toEqual(views);
    // Порча хранилища не роняет чтение.
    saveSavedViews(storage, views);
    const broken = memoryStorage({
      "lnt.catalog.savedViews.v1": JSON.stringify([
        { name: "", filters: {} },
        { filters: { health: "ok" } },
        views[0],
      ]),
    });
    expect(loadSavedViews(broken)).toEqual([views[0]]);
  });

  it("caps the number of stored views", () => {
    const many: SavedView[] = Array.from({ length: 40 }, (_, index) => ({
      name: `вид-${String(index)}`,
      filters: {},
    }));
    const parsed = parseSavedViews(JSON.stringify(many));
    expect(parsed.length).toBeLessThanOrEqual(20);
    expect(parsed.at(-1)?.name).toBe("вид-19");
  });
});
