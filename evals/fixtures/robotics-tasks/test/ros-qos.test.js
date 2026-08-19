import { strict as assert } from "node:assert";
import { reliabilityPolicy } from "../src/ros-qos.js";
assert.equal(reliabilityPolicy(undefined), "reliable");
assert.equal(reliabilityPolicy("best_effort"), "best_effort");
