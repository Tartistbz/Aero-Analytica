import { strict as assert } from "node:assert";
import { retryDelayMilliseconds } from "../src/ros-retry-delay.js";
assert.equal(retryDelayMilliseconds(-2), 0);
assert.equal(retryDelayMilliseconds(1.5), 1500);
