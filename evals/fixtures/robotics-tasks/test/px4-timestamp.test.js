import { strict as assert } from "node:assert";
import { microsecondsToSeconds } from "../src/px4-timestamp.js";
assert.equal(microsecondsToSeconds(2_500_000), 2.5);
