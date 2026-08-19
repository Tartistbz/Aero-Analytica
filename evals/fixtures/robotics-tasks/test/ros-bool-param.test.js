import { strict as assert } from "node:assert";
import { parseBoolParameter } from "../src/ros-bool-param.js";
assert.equal(parseBoolParameter(true), true);
assert.equal(parseBoolParameter(false), false);
assert.equal(parseBoolParameter("true"), true);
