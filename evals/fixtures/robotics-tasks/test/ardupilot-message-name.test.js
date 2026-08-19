import { strict as assert } from "node:assert";
import { normalizeMessageName } from "../src/ardupilot-message-name.js";
assert.equal(normalizeMessageName("  CTUN "), "CTUN");
