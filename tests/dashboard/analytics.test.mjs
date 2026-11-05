import assert from "node:assert/strict";
import test from "node:test";

import {
  filterObservations,
  summarizeObservations,
} from "../../dashboard/analytics.mjs";

function comparableRow(status, hours) {
  return {
    predecessor_match_status: "matched",
    predecessor_lot_found: true,
    deadline_change_status: status,
    deadline_change_hours: hours,
  };
}

test("calculates coverage and extension rate using different denominators", () => {
  const observations = [
    comparableRow("extended", 24),
    comparableRow("extended", 48),
    comparableRow("shortened", -12),
    comparableRow("unchanged", 0),
    comparableRow("quality_issue", null),
    comparableRow("missing_exact_deadline", null),
    {
      predecessor_match_status: "no_reference",
      predecessor_lot_found: false,
      deadline_change_status: "no_reference",
      deadline_change_hours: null,
    },
  ];

  assert.deepEqual(summarizeObservations(observations), {
    total_lot_observations: 7,
    matched_lot_observations: 6,
    comparable_lot_observations: 4,
    extended_lot_observations: 2,
    shortened_lot_observations: 1,
    unchanged_lot_observations: 1,
    quality_issue_lot_observations: 1,
    missing_deadline_lot_observations: 1,
    comparison_coverage_pct: 66.67,
    extension_rate_pct: 50,
    median_extension_hours: 36,
  });
});

test("returns null percentages and median for an empty selection", () => {
  const summary = summarizeObservations([]);

  assert.equal(summary.total_lot_observations, 0);
  assert.equal(summary.comparison_coverage_pct, null);
  assert.equal(summary.extension_rate_pct, null);
  assert.equal(summary.median_extension_hours, null);
});

test("distinguishes zero coverage from an undefined extension rate", () => {
  const summary = summarizeObservations([
    comparableRow("quality_issue", null),
  ]);

  assert.equal(summary.comparison_coverage_pct, 0);
  assert.equal(summary.extension_rate_pct, null);
});

test("calculates median for an odd number of fractional extensions", () => {
  const summary = summarizeObservations([
    comparableRow("extended", 48),
    comparableRow("extended", 1.5),
    comparableRow("extended", 12),
  ]);

  assert.equal(summary.median_extension_hours, 12);
});

test("includes both publication date boundaries", () => {
  const observations = [
    { publication_date: "2026-10-19" },
    { publication_date: "2026-10-20" },
    { publication_date: "2026-11-03" },
    { publication_date: "2026-11-04" },
  ];

  assert.deepEqual(
    filterObservations(observations, {
      dateFrom: "2026-10-20",
      dateTo: "2026-11-03",
    }),
    [observations[1], observations[2]],
  );
});

test("searches titles, buyers and publication numbers without case sensitivity", () => {
  const observations = [
    {
      publication_number: "722762-2026",
      notice_title: "Rozwój systemu SIOEZ",
      buyer_names: "Centralna Komisja Egzaminacyjna",
    },
    {
      publication_number: "123456-2026",
      notice_title: null,
      buyer_names: "Miasto Koszalin; Urząd Łódź",
    },
  ];

  for (const search of [" sioez ", "KOMISJA", "722762"]) {
    assert.deepEqual(
      filterObservations(observations, { search }),
      [observations[0]],
    );
  }

  assert.deepEqual(
    filterObservations(observations, { search: "ŁÓDŹ" }),
    [observations[1]],
  );

  assert.deepEqual(
    filterObservations(observations, { search: "nieistniejący" }),
    [],
  );
});

test("combines search and date filters", () => {
  const observations = [
    { publication_date: "2026-10-20", buyer_names: "Miasto Koszalin" },
    { publication_date: "2026-11-03", buyer_names: "Miasto Koszalin" },
    { publication_date: "2026-11-03", buyer_names: "Inny zamawiający" },
  ];

  assert.deepEqual(
    filterObservations(observations, {
      dateFrom: "2026-11-01",
      search: "Koszalin",
    }),
    [observations[1]],
  );
});