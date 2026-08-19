import { strict as assert } from "node:assert";
import { normalizeNamespace } from "../src/ros-namespace.js";
assert.equal(normalizeNamespace("//uav///camera/"), "/uav/camera");
