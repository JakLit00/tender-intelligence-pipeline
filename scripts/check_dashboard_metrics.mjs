import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { summarizeObservations } from "../dashboard/analytics.mjs";

const dataUrl = new URL("../dashboard/data/dashboard.json", import.meta.url);
const data = JSON.parse(await readFile(dataUrl, "utf8"));

const actual = summarizeObservations(data.observations);
const expected = data.summary;

for (const [name, expectedValue] of Object.entries(expected)) {
  assert.ok(Object.hasOwn(actual, name), `Missing metric: ${name}`);

  const actualValue = actual[name];

  if (expectedValue === null) {
    assert.equal(actualValue, null, `${name}: expected null`);
  } else {
    assert.equal(
      typeof actualValue,
      "number",
      `${name}: expected a number`,
    );

    // PostgreSQL and JavaScript may differ slightly in floating-point results.
    const tolerance = Math.max(1, Math.abs(expectedValue)) * 1e-9;
    assert.ok(
      Math.abs(actualValue - expectedValue) <= tolerance,
      `${name}: dbt=${expectedValue}, dashboard=${actualValue}`,
    );
  }

  console.log(`${name}: OK`);
}

console.log("Dashboard metrics match the dbt summary");