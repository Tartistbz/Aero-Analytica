import { strict as assert } from "node:assert";
import { displayMode } from "../src/ardupilot-mode.js";
assert.equal(displayMode(""), "UNKNOWN");
assert.equal(displayMode("AUTO"), "AUTO");
