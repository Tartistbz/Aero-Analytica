import { strict as assert } from "node:assert";
import { has3dGpsFix } from "../src/ardupilot-gps-fix.js";
assert.equal(has3dGpsFix(2), false);
assert.equal(has3dGpsFix(3), true);
