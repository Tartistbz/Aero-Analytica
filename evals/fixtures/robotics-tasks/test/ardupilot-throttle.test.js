import { strict as assert } from "node:assert";
import { clampThrottle } from "../src/ardupilot-throttle.js";
assert.equal(clampThrottle(-5), 0);
assert.equal(clampThrottle(130), 100);
