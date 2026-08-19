import { strict as assert } from "node:assert";
import { centiDegreesToDegrees } from "../src/ardupilot-angle.js";
assert.equal(centiDegreesToDegrees(1234), 12.34);
