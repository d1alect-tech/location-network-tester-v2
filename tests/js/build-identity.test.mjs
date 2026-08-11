import assert from "node:assert/strict";
import { test } from "node:test";

import { buildIdentityMatches } from "../../src/lnt/ui/static/build-identity.js";

test("buildIdentityMatches detects backend/frontend mismatch", () => {
  assert.equal(buildIdentityMatches("frontend-a", { build_id: "backend-b" }), false);
  assert.equal(buildIdentityMatches("same", { build_id: "same" }), true);
});
