function normalizeText(value) {
  return String(value ?? "")
    .normalize("NFC")
    .toLocaleLowerCase("pl");
}

export function filterObservations(
  observations,
  { dateFrom = "", dateTo = "", search = "" } = {},
) {
  const query = normalizeText(search.trim());

  return observations.filter((row) => {
    if (dateFrom && row.publication_date < dateFrom) {
      return false;
    }

    if (dateTo && row.publication_date > dateTo) {
      return false;
    }

    if (!query) {
      return true;
    }

    return [row.publication_number, row.notice_title, row.buyer_names].some((value) =>
      normalizeText(value).includes(query),
    );
  });
}

function percentage(numerator, denominator) {
  if (denominator === 0) {
    return null;
  }

  return Math.round(((100 * numerator) / denominator) * 100) / 100;
}

function median(values) {
  if (values.length === 0) {
    return null;
  }

  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);

  if (sorted.length % 2 === 1) {
    return sorted[middle];
  }

  return (sorted[middle - 1] + sorted[middle]) / 2;
}

export function summarizeObservations(observations) {
  let matched = 0;
  let comparable = 0;
  let extended = 0;
  let shortened = 0;
  let unchanged = 0;
  let qualityIssues = 0;
  let missingDeadlines = 0;
  const extensionHours = [];

  for (const row of observations) {
    if (
      row.predecessor_match_status === "matched" &&
      row.predecessor_lot_found === true
    ) {
      matched += 1;
    }

    if (Number.isFinite(row.deadline_change_hours)) {
      comparable += 1;
    }

    switch (row.deadline_change_status) {
      case "extended":
        extended += 1;
        if (Number.isFinite(row.deadline_change_hours)) {
          extensionHours.push(row.deadline_change_hours);
        }
        break;
      case "shortened":
        shortened += 1;
        break;
      case "unchanged":
        unchanged += 1;
        break;
      case "quality_issue":
        qualityIssues += 1;
        break;
      case "missing_exact_deadline":
        missingDeadlines += 1;
        break;
    }
  }

  return {
    total_lot_observations: observations.length,
    matched_lot_observations: matched,
    comparable_lot_observations: comparable,
    extended_lot_observations: extended,
    shortened_lot_observations: shortened,
    unchanged_lot_observations: unchanged,
    quality_issue_lot_observations: qualityIssues,
    missing_deadline_lot_observations: missingDeadlines,
    comparison_coverage_pct: percentage(comparable, matched),
    extension_rate_pct: percentage(extended, comparable),
    median_extension_hours: median(extensionHours),
  };
}
