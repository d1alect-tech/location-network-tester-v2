import { describe, expect, it } from "vitest";
import {
  DEFAULT_ROUTE,
  RouteStore,
  WORKSPACE_ROUTES,
  type WorkspaceLocation,
  parseHash,
  serializeLocation,
} from "./routeState";

describe("parseHash", () => {
  it("parses route and query params", () => {
    expect(parseHash("#/inspect?session=abc&tab=spectrum")).toEqual({
      route: "inspect",
      params: { session: "abc", tab: "spectrum" },
    });
  });

  it("parses a bare route without query", () => {
    expect(parseHash("#/catalog")).toEqual({ route: "catalog", params: {} });
  });

  it("returns null for unknown routes and non-hash strings", () => {
    expect(parseHash("#/unknown")).toBeNull();
    expect(parseHash("#/prepare/extra")).toBeNull();
    expect(parseHash("")).toBeNull();
    expect(parseHash("#no-slash")).toBeNull();
  });
});

describe("serializeLocation", () => {
  it("round-trips a location with filters", () => {
    const loc: WorkspaceLocation = {
      route: "inspect",
      params: { session: "abc", health: "ok" },
    };
    expect(parseHash(serializeLocation(loc))).toEqual(loc);
  });

  it("omits the question mark when there are no params", () => {
    expect(serializeLocation({ route: "capture", params: {} })).toBe("#/capture");
  });

  it("never serializes secret keys (nonce/token) into the URL", () => {
    const out = serializeLocation({
      route: "inspect",
      params: { session: "abc", nonce: "leak", token: "leak", mutation_nonce: "leak" },
    });
    expect(out).not.toContain("leak");
    expect(out).not.toContain("nonce");
    expect(out).not.toContain("token");
    expect(out).toBe("#/inspect?session=abc");
  });
});

describe("RouteStore reload safety", () => {
  it("restores route and filters from the URL on reload (fresh construction)", () => {
    window.location.hash = "#/inspect?session=abc&health=ok";
    const store = new RouteStore(window);
    expect(store.get()).toEqual({
      route: "inspect",
      params: { session: "abc", health: "ok" },
    });
  });

  it("falls back to the safe default route for unknown hashes", () => {
    window.location.hash = "#/garbage";
    const store = new RouteStore(window);
    expect(store.get().route).toBe(DEFAULT_ROUTE);
    expect(WORKSPACE_ROUTES).toContain(DEFAULT_ROUTE);
  });

  it("navigate() updates the hash and notifies subscribers", () => {
    window.location.hash = "#/prepare";
    const store = new RouteStore(window);
    const seen: WorkspaceLocation[] = [];
    store.subscribe((loc) => seen.push(loc));
    store.navigate({ route: "experiments", params: { id: "e1" } });
    expect(window.location.hash).toBe("#/experiments?id=e1");
    // syncFromUrl is bound to hashchange; invoke deterministically here.
    store.syncFromUrl();
    expect(store.get()).toEqual({ route: "experiments", params: { id: "e1" } });
    expect(seen.at(-1)).toEqual({ route: "experiments", params: { id: "e1" } });
  });

  it("reacts to a real hashchange event", () => {
    window.location.hash = "#/prepare";
    const store = new RouteStore(window);
    window.location.hash = "#/reports";
    window.dispatchEvent(new Event("hashchange"));
    expect(store.get().route).toBe("reports");
  });

  it("does not notify when the parsed location is unchanged", () => {
    window.location.hash = "#/prepare";
    const store = new RouteStore(window);
    let calls = 0;
    store.subscribe(() => {
      calls += 1;
    });
    store.syncFromUrl();
    expect(calls).toBe(0);
  });

  it("replaceParams merges filters without losing the route", () => {
    window.location.hash = "#/inspect?session=abc";
    const store = new RouteStore(window);
    store.syncFromUrl();
    store.replaceParams({ health: "ok" });
    store.syncFromUrl();
    expect(store.get()).toEqual({
      route: "inspect",
      params: { session: "abc", health: "ok" },
    });
  });
});
