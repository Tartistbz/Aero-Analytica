import { strict as assert } from "node:assert";
import { normalizeTopicName } from "../src/px4-topic-name.js";
assert.equal(normalizeTopicName("vehicle_local_position_0"), "vehicle_local_position");
