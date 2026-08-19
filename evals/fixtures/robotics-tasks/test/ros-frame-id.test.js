import { strict as assert } from "node:assert";
import { normalizeFrameId } from "../src/ros-frame-id.js";
assert.equal(normalizeFrameId("/base_link"), "base_link");
