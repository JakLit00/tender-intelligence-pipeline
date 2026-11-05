import { summarizeObservations } from "./analytics.mjs";

function requireValue(condition, path, message = "invalid value") {
  if (!condition) throw new Error(`${path}: ${message}`);
}

const text = (value) => typeof value === "string" && value.trim().length > 0;
const nullable = (check) => (value) => value === null || check(value);
const count = (value) => Number.isSafeInteger(value) && value >= 0;
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const oneOf =
  (...values) =>
  (value) =>
    values.includes(value);
const publication = (value) =>
  typeof value === "string" && /^[1-9]\d{0,7}-\d{4}$/.test(value);
const uuid = (value) =>
  typeof value === "string" &&
  /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value);

function calendarDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return (
    Number(value.slice(0, 4)) > 0 &&
    Number.isFinite(parsed.getTime()) &&
    parsed.toISOString().slice(0, 10) === value
  );
}

function utcTimestamp(value) {
  return (
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value) &&
    calendarDate(value.slice(0, 10)) &&
    Number(value.slice(11, 13)) < 24 &&
    Number(value.slice(14, 16)) < 60 &&
    Number(value.slice(17, 19)) < 60
  );
}

function tedUrl(value) {
  if (!text(value)) return false;
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      url.hostname === "ted.europa.eu" &&
      !url.username &&
      !url.password &&
      !url.port
    );
  } catch {
    return false;
  }
}

function object(value, fields, path) {
  requireValue(
    value !== null && typeof value === "object" && !Array.isArray(value),
    path,
  );
  const keys = Object.keys(value);
  requireValue(
    keys.length === Object.keys(fields).length &&
      keys.every((key) => Object.hasOwn(fields, key)),
    path,
    "missing or unknown fields",
  );
  for (const [key, check] of Object.entries(fields)) {
    requireValue(check(value[key]), `${path}.${key}`);
  }
}

const matchStatus = oneOf(
  "no_reference",
  "unsupported_reference",
  "not_found",
  "ambiguous",
  "self_reference",
  "procedure_mismatch",
  "matched",
);
const changeStatus = oneOf(
  "no_reference",
  "unresolved_predecessor",
  "missing_predecessor_lot",
  "quality_issue",
  "missing_exact_deadline",
  "extended",
  "shortened",
  "unchanged",
);
const quality = nullable(oneOf("conflicting_timezone_offsets"));
const observationFields = {
  publication_number: publication,
  lot_id: text,
  procedure_id: nullable(uuid),
  publication_date: calendarDate,
  notice_title: nullable(text),
  buyer_names: nullable(text),
  notice_url: nullable(tedUrl),
  predecessor_publication_number: nullable(publication),
  predecessor_match_status: matchStatus,
  predecessor_lot_found: (value) => typeof value === "boolean",
  previous_deadline_date: nullable(calendarDate),
  current_deadline_date: nullable(calendarDate),
  previous_deadline_at: nullable(utcTimestamp),
  current_deadline_at: nullable(utcTimestamp),
  previous_quality_issue: quality,
  current_quality_issue: quality,
  deadline_change_status: changeStatus,
  deadline_change_hours: nullable(finite),
};
const percentage = nullable((value) => finite(value) && value >= 0 && value <= 100);
const summaryFields = {
  total_lot_observations: count,
  matched_lot_observations: count,
  comparable_lot_observations: count,
  extended_lot_observations: count,
  shortened_lot_observations: count,
  unchanged_lot_observations: count,
  quality_issue_lot_observations: count,
  missing_deadline_lot_observations: count,
  comparison_coverage_pct: percentage,
  extension_rate_pct: percentage,
  median_extension_hours: nullable((value) => finite(value) && value > 0),
};

function closeEnough(actual, expected) {
  return Math.abs(actual - expected) <= Math.max(1, Math.abs(expected)) * 1e-9;
}

function microseconds(value) {
  // Date truncates fractions beyond milliseconds; SQL retains microseconds.
  const seconds = BigInt(Date.parse(`${value.slice(0, 19)}Z`)) * 1000n;
  const fraction = value.includes(".") ? value.slice(20, -1) : "";
  return seconds + BigInt(fraction.padEnd(6, "0"));
}

function validateObservation(row, path) {
  object(row, observationFields, path);
  const matched = row.predecessor_match_status === "matched";
  requireValue(
    matched === (row.predecessor_publication_number !== null),
    path,
    "inconsistent predecessor",
  );
  requireValue(
    !row.predecessor_lot_found || matched,
    path,
    "inconsistent predecessor lot",
  );
  requireValue(
    !matched || row.predecessor_publication_number !== row.publication_number,
    path,
    "self reference",
  );
  for (const side of ["previous", "current"]) {
    if (row[`${side}_deadline_at`] !== null || row[`${side}_quality_issue`] !== null) {
      requireValue(row[`${side}_deadline_date`] !== null, path, "missing source date");
    }
    if (row[`${side}_quality_issue`] !== null) {
      requireValue(
        row[`${side}_deadline_at`] === null,
        path,
        "quality issue has an exact deadline",
      );
    }
  }
  if (!row.predecessor_lot_found) {
    requireValue(
      row.previous_deadline_date === null &&
        row.previous_deadline_at === null &&
        row.previous_quality_issue === null,
      path,
      "deadline values without a predecessor lot",
    );
  }

  let status;
  let hours = null;
  if (row.predecessor_match_status === "no_reference") status = "no_reference";
  else if (!matched) status = "unresolved_predecessor";
  else if (!row.predecessor_lot_found) status = "missing_predecessor_lot";
  else if (row.current_quality_issue !== null || row.previous_quality_issue !== null)
    status = "quality_issue";
  else if (row.current_deadline_at === null || row.previous_deadline_at === null)
    status = "missing_exact_deadline";
  else {
    const difference =
      microseconds(row.current_deadline_at) - microseconds(row.previous_deadline_at);
    status = difference > 0n ? "extended" : difference < 0n ? "shortened" : "unchanged";
    hours = Number(difference) / 3_600_000_000;
  }
  requireValue(
    row.deadline_change_status === status,
    path,
    "inconsistent change status",
  );
  if (hours !== null) {
    requireValue(
      status === "extended"
        ? row.deadline_change_hours > 0
        : status === "shortened"
          ? row.deadline_change_hours < 0
          : row.deadline_change_hours === 0,
      path,
      "inconsistent change sign",
    );
  }
  requireValue(
    hours === null
      ? row.deadline_change_hours === null
      : row.deadline_change_hours !== null &&
          closeEnough(row.deadline_change_hours, hours),
    path,
    "inconsistent change hours",
  );
}

export function validateDashboardSnapshot(data) {
  object(
    data,
    {
      schema_version: (value) => value === 1,
      generated_at: utcTimestamp,
      scope: (value) => value !== null,
      summary: (value) => value !== null,
      observations: Array.isArray,
    },
    "dashboard",
  );
  object(
    data.scope,
    {
      notice_count: count,
      first_publication_date: nullable(calendarDate),
      last_publication_date: nullable(calendarDate),
    },
    "scope",
  );
  object(data.summary, summaryFields, "summary");
  const scope = data.scope;
  requireValue(
    scope.notice_count === 0
      ? scope.first_publication_date === null && scope.last_publication_date === null
      : scope.first_publication_date !== null &&
          scope.last_publication_date !== null &&
          scope.first_publication_date <= scope.last_publication_date,
    "scope",
    "inconsistent publication range",
  );
  const pairs = new Set();
  const publications = new Set();
  data.observations.forEach((row, index) => {
    const path = `observations[${index}]`;
    validateObservation(row, path);
    const pair = JSON.stringify([row.publication_number, row.lot_id]);
    requireValue(!pairs.has(pair), path, "duplicate publication-lot pair");
    pairs.add(pair);
    publications.add(row.publication_number);
    requireValue(
      scope.notice_count > 0 &&
        row.publication_date >= scope.first_publication_date &&
        row.publication_date <= scope.last_publication_date,
      path,
      "publication date outside scope",
    );
  });
  // Notices without lots can belong to the scope without producing observations.
  requireValue(publications.size <= scope.notice_count, "scope.notice_count");

  const actual = summarizeObservations(data.observations);
  for (const [name, expected] of Object.entries(data.summary)) {
    const value = actual[name];
    requireValue(
      expected === null || value === null || name.endsWith("_observations")
        ? value === expected
        : closeEnough(value, expected),
      `summary.${name}`,
      "dashboard and dbt metrics differ",
    );
  }
}
