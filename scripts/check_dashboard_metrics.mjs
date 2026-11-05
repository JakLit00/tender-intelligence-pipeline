import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { summarizeObservations } from "../dashboard/analytics.mjs";

assert.ok(
  process.argv.length <= 3,
  "Usage: node scripts/check_dashboard_metrics.mjs [json-path]",
);

const inputPath = process.argv[2]
  ? resolve(process.argv[2])
  : new URL("../dashboard/data/dashboard.json", import.meta.url);

const data = JSON.parse(await readFile(inputPath, "utf8"));

assert.equal(data.schema_version, 1, "Unsupported dashboard data version");
assert.ok(Array.isArray(data.observations), "Observations must be an array");
assert.ok(
  data.summary !== null &&
    typeof data.summary === "object" &&
    !Array.isArray(data.summary),
  "Summary must be an object",
);

const actual = summarizeObservations(data.observations);
const expected = data.summary;

assert.deepEqual(
  Object.keys(expected).sort(),
  Object.keys(actual).sort(),
  "Dashboard and dbt summary must contain the same metrics",
);

for (const [name, actualValue] of Object.entries(actual)) {
  const expectedValue = expected[name];

  if (expectedValue === null || actualValue === null) {
    assert.equal(actualValue, expectedValue, `${name}: null mismatch`);
  } else {
    assert.ok(
      Number.isFinite(expectedValue) && Number.isFinite(actualValue),
      `${name}: expected finite numbers`,
    );

    if (name.endsWith("_observations")) {
      assert.ok(
        Number.isSafeInteger(expectedValue) && expectedValue >= 0,
        `${name}: expected a non-negative integer`,
      );
      assert.equal(actualValue, expectedValue, `${name}: count mismatch`);
    } else {
      // PostgreSQL and JavaScript may differ slightly in floating-point results.
      const tolerance = Math.max(1, Math.abs(expectedValue)) * 1e-9;
      assert.ok(
        Math.abs(actualValue - expectedValue) <= tolerance,
        `${name}: dbt=${expectedValue}, dashboard=${actualValue}`,
      );
    }
  }

  console.log(`${name}: OK`);
}

console.log("Dashboard metrics match the dbt summary");
