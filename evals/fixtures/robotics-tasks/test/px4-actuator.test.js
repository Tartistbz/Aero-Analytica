import { strict as assert } from "node:assert";
import { clampActuator } from "../src/px4-actuator.js";
assert.equal(clampActuator(-0.3), 0);
assert.equal(clampActuator(1.2), 1);
