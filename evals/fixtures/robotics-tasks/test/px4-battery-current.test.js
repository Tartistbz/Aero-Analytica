import { strict as assert } from "node:assert";
import { normalizedBatteryCurrent } from "../src/px4-battery-current.js";
assert.equal(normalizedBatteryCurrent(-3.2), 0);
assert.equal(normalizedBatteryCurrent(5.1), 5.1);
