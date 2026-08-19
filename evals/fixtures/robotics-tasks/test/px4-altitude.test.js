import { strict as assert } from "node:assert";
import { isValidAltitude } from "../src/px4-altitude.js";
assert.equal(isValidAltitude(Number.NaN), false);
assert.equal(isValidAltitude(120), true);
