import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { validateDashboardSnapshot } from "../dashboard/contract.mjs";

if (process.argv.length > 3) {
  throw new Error("Usage: node scripts/check_dashboard_metrics.mjs [json-path]");
}
const inputPath = process.argv[2]
  ? resolve(process.argv[2])
  : new URL("../dashboard/data/dashboard.json", import.meta.url);

try {
  const data = JSON.parse(await readFile(inputPath, "utf8"));
  validateDashboardSnapshot(data);
  console.log("Dashboard contract is valid and metrics match the dbt summary");
} catch (error) {
  // JSON parse errors may include source text; report only the failure category.
  console.error(
    error instanceof SyntaxError ? "Invalid dashboard JSON" : error.message,
  );
  process.exitCode = 1;
}
