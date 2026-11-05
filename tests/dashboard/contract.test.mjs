import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { summarizeObservations } from "../../dashboard/analytics.mjs";
import { validateDashboardSnapshot } from "../../dashboard/contract.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("../fixtures/dashboard.json", import.meta.url), "utf8"),
);

test("accepts the exported contract", () => {
  validateDashboardSnapshot(structuredClone(fixture));
});

for (const [name, mutate] of [
  ["missing scope", (data) => delete data.scope],
  ["missing generated_at", (data) => delete data.generated_at],
  [
    "empty observation",
    (data) => {
      data.observations = [{}];
    },
  ],
  [
    "unknown root field",
    (data) => {
      data.internal_debug = "private";
    },
  ],
  [
    "unknown scope field",
    (data) => {
      data.scope.internal_debug = "private";
    },
  ],
  [
    "unknown summary field",
    (data) => {
      data.summary.internal_debug = "private";
    },
  ],
  [
    "unknown row field",
    (data) => {
      data.observations[0].internal_debug = "private";
    },
  ],
  [
    "nested object instead of source text",
    (data) => {
      data.observations[0].notice_title = { internal_debug: "private" };
    },
  ],
  [
    "array scope",
    (data) => {
      data.scope = [];
    },
  ],
  [
    "string count",
    (data) => {
      data.scope.notice_count = "1";
    },
  ],
  [
    "boolean count",
    (data) => {
      data.summary.total_lot_observations = true;
    },
  ],
  [
    "null identity",
    (data) => {
      data.observations[0].publication_number = null;
    },
  ],
  [
    "non-normalized identity",
    (data) => {
      data.observations[0].publication_number = "00123-2026";
    },
  ],
  [
    "invalid UUID",
    (data) => {
      data.observations[0].procedure_id = "invalid";
    },
  ],
  [
    "empty lot",
    (data) => {
      data.observations[0].lot_id = " ";
    },
  ],
  [
    "nonexistent date",
    (data) => {
      data.observations[0].publication_date = "2026-02-30";
    },
  ],
  [
    "non-leap February",
    (data) => {
      data.scope.first_publication_date = "2025-02-29";
    },
  ],
  [
    "invalid timestamp",
    (data) => {
      data.generated_at = "2026-11-05T24:00:00Z";
    },
  ],
  [
    "timestamp without timezone",
    (data) => {
      data.generated_at = "2026-11-05T12:00:00";
    },
  ],
  [
    "unknown status",
    (data) => {
      data.observations[0].deadline_change_status = "unknown";
    },
  ],
  [
    "unknown predecessor status",
    (data) => {
      data.observations[0].predecessor_match_status = "unknown";
    },
  ],
  [
    "unknown quality flag",
    (data) => {
      data.observations[0].current_quality_issue = "unknown";
    },
  ],
  [
    "non-boolean match",
    (data) => {
      data.observations[0].predecessor_lot_found = 1;
    },
  ],
  [
    "missing predecessor identity",
    (data) => {
      data.observations[0].predecessor_publication_number = null;
    },
  ],
  [
    "self reference",
    (data) => {
      data.observations[0].predecessor_publication_number = "123-2026";
    },
  ],
  [
    "wrong change sign",
    (data) => {
      data.observations[0].deadline_change_hours = -24;
    },
  ],
  [
    "non-finite change",
    (data) => {
      data.observations[0].deadline_change_hours = Infinity;
    },
  ],
  [
    "missing comparable value",
    (data) => {
      data.observations[0].deadline_change_hours = null;
    },
  ],
  [
    "contradictory status",
    (data) => {
      data.observations[0].deadline_change_status = "shortened";
    },
  ],
  [
    "duplicate publication-lot",
    (data) => {
      data.observations.push(structuredClone(data.observations[0]));
      data.summary = summarizeObservations(data.observations);
    },
  ],
  [
    "incorrect SQL summary",
    (data) => {
      data.summary.median_extension_hours = 12;
    },
  ],
  [
    "date outside scope",
    (data) => {
      data.observations[0].publication_date = "2026-11-03";
    },
  ],
  [
    "notice count too small",
    (data) => {
      data.scope.notice_count = 0;
    },
  ],
  [
    "unsafe source URL",
    (data) => {
      data.observations[0].notice_url = "https://ted.europa.eu.attacker.invalid/";
    },
  ],
]) {
  test(`rejects ${name}`, () => {
    const data = structuredClone(fixture);
    mutate(data);
    assert.throws(() => validateDashboardSnapshot(data));
  });
}

test("accepts an empty scope and notices without lots", () => {
  const data = structuredClone(fixture);
  data.observations = [];
  data.summary = summarizeObservations([]);
  validateDashboardSnapshot(data);
  data.scope = {
    notice_count: 0,
    first_publication_date: null,
    last_publication_date: null,
  };
  validateDashboardSnapshot(data);
});

test("accepts missing optional values with the matching classification", () => {
  const data = structuredClone(fixture);
  Object.assign(data.observations[0], {
    predecessor_publication_number: null,
    predecessor_match_status: "no_reference",
    predecessor_lot_found: false,
    previous_deadline_date: null,
    current_deadline_date: null,
    previous_deadline_at: null,
    current_deadline_at: null,
    notice_title: null,
    notice_url: null,
    deadline_change_status: "no_reference",
    deadline_change_hours: null,
  });
  data.summary = summarizeObservations(data.observations);
  validateDashboardSnapshot(data);
});

test("preserves microsecond differences instead of truncating them to zero", () => {
  const data = structuredClone(fixture);
  Object.assign(data.observations[0], {
    current_deadline_date: "2026-12-01",
    current_deadline_at: "2026-12-01T09:00:00.000001Z",
    deadline_change_hours: 1 / 3_600_000_000,
  });
  data.summary = summarizeObservations(data.observations);
  validateDashboardSnapshot(data);
});
