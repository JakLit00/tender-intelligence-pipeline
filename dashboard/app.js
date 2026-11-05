import { filterObservations, summarizeObservations } from "./analytics.mjs";

const numberFormat = new Intl.NumberFormat("en-GB", {
  maximumFractionDigits: 2,
});

const timestampFormat = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

const statusLabels = {
  extended: "Extended",
  shortened: "Shortened",
  unchanged: "Unchanged",
  no_reference: "No predecessor reference",
  unresolved_predecessor: "Unresolved predecessor",
  missing_predecessor_lot: "Missing predecessor lot",
  missing_exact_deadline: "Missing exact deadline",
  quality_issue: "Quality issue",
};

function formatNumber(value, suffix = "") {
  if (value === null || value === undefined) {
    return "—";
  }

  return `${numberFormat.format(value)}${suffix}`;
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function renderSnapshotInfo(data) {
  const firstDate = data.scope.first_publication_date ?? "—";
  const lastDate = data.scope.last_publication_date ?? "—";
  const generatedAt = timestampFormat.format(new Date(data.generated_at));

  setText(
    "snapshot-info",
    `Snapshot generated: ${generatedAt} UTC · ` +
      `Publication range: ${firstDate} to ${lastDate} · ` +
      `Scope notices: ${formatNumber(data.scope.notice_count)}`,
  );
}

function renderSummary(summary) {
  setText("total-observations", formatNumber(summary.total_lot_observations));
  setText("comparison-coverage", formatNumber(summary.comparison_coverage_pct, "%"));
  setText("extension-rate", formatNumber(summary.extension_rate_pct, "%"));
  setText("median-extension", formatNumber(summary.median_extension_hours, " h"));
}

function formatDeadline(value) {
  if (!value) {
    return "—";
  }

  const timestamp = new Date(value);

  if (Number.isNaN(timestamp.getTime())) {
    return "Invalid timestamp";
  }

  return timestamp.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function showObservationDetails(observation) {
  const fields = [
    ["Publication", observation.publication_number],
    ["Publication date", observation.publication_date],
    ["Lot", observation.lot_id],
    ["Notice title", observation.notice_title],
    ["Buyers", observation.buyer_names],
    ["Procedure ID", observation.procedure_id],
    ["Previous publication", observation.predecessor_publication_number],
    ["Predecessor match status", observation.predecessor_match_status],
    [
      "Change status",
      statusLabels[observation.deadline_change_status] ??
        observation.deadline_change_status,
    ],
    ["Previous exact deadline (UTC)", formatDeadline(observation.previous_deadline_at)],
    ["Current exact deadline (UTC)", formatDeadline(observation.current_deadline_at)],
    ["Previous source local date", observation.previous_deadline_date],
    ["Current source local date", observation.current_deadline_date],
    ["Change (hours)", formatNumber(observation.deadline_change_hours)],
    ["Previous quality issue", observation.previous_quality_issue],
    ["Current quality issue", observation.current_quality_issue],
  ];

  const fragment = document.createDocumentFragment();

  for (const [label, value] of fields) {
    const term = document.createElement("dt");
    term.textContent = label;

    const description = document.createElement("dd");
    description.textContent = value ?? "—";

    fragment.append(term, description);
  }

  document.getElementById("details-fields").replaceChildren(fragment);

  const source = document.getElementById("details-source");
  source.replaceChildren();

  // Build the source URL from a validated identifier, not an arbitrary input URL.
  if (/^\d+-\d{4}$/.test(observation.publication_number)) {
    const link = document.createElement("a");
    link.href =
      "https://ted.europa.eu/pl/notice/-/detail/" +
      encodeURIComponent(observation.publication_number);
    link.textContent = "Open publication on TED";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    source.appendChild(link);
  }

  document.getElementById("notice-details").showModal();
}

function renderObservations(observations) {
  const fragment = document.createDocumentFragment();

  const sorted = [...observations].sort(
    (left, right) =>
      right.publication_date.localeCompare(left.publication_date) ||
      left.publication_number.localeCompare(right.publication_number) ||
      left.lot_id.localeCompare(right.lot_id),
  );

  for (const observation of sorted) {
    const row = document.createElement("tr");
    const values = [
      observation.publication_number,
      observation.publication_date,
      observation.notice_title,
      observation.buyer_names,
      observation.lot_id,
      statusLabels[observation.deadline_change_status] ??
        observation.deadline_change_status,
      formatNumber(observation.deadline_change_hours),
    ];

    for (const value of values) {
      const cell = document.createElement("td");
      // Source text must be displayed as text, never interpreted as HTML.
      cell.textContent = value ?? "—";
      row.appendChild(cell);
    }

    const actionCell = document.createElement("td");
    const detailsButton = document.createElement("button");

    detailsButton.type = "button";
    detailsButton.className = "details-button";
    detailsButton.textContent = "View";
    detailsButton.setAttribute(
      "aria-label",
      `View details for ${observation.publication_number}, ${observation.lot_id}`,
    );
    detailsButton.addEventListener("click", () => {
      showObservationDetails(observation);
    });

    actionCell.appendChild(detailsButton);
    row.appendChild(actionCell);

    fragment.appendChild(row);
  }

  if (sorted.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 8;
    cell.textContent = "No observations match the selected filters.";
    row.appendChild(cell);
    fragment.appendChild(row);
  }

  document.getElementById("observations").replaceChildren(fragment);
  setText("row-count", `${formatNumber(observations.length)} observations`);
}

function renderStatusChart(observations) {
  const counts = new Map(Object.keys(statusLabels).map((status) => [status, 0]));

  for (const observation of observations) {
    const status = observation.deadline_change_status;
    counts.set(status, (counts.get(status) ?? 0) + 1);
  }

  const fragment = document.createDocumentFragment();
  const maximum = Math.max(0, ...counts.values());

  if (observations.length > 0) {
    for (const [status, count] of counts) {
      const row = document.createElement("li");
      row.className = "status-row";

      const label = document.createElement("span");
      label.className = "status-label";
      label.textContent = statusLabels[status] ?? status;

      const track = document.createElement("div");
      track.className = "status-track";
      track.setAttribute("aria-hidden", "true");

      const fill = document.createElement("div");
      fill.className = "status-fill";
      fill.dataset.status = status;
      fill.style.width = `${maximum === 0 ? 0 : (100 * count) / maximum}%`;

      const value = document.createElement("span");
      value.className = "status-count";
      value.textContent = formatNumber(count);

      track.appendChild(fill);
      row.append(label, track, value);
      fragment.appendChild(row);
    }
  }

  document.getElementById("status-chart").replaceChildren(fragment);
  document.getElementById("status-chart-empty").hidden = observations.length !== 0;
}

function initializeFilters(data) {
  const dateFrom = document.getElementById("date-from");
  const dateTo = document.getElementById("date-to");
  const search = document.getElementById("search");
  const filterError = document.getElementById("filter-error");

  function applyFilters() {
    const invalidRange =
      dateFrom.value && dateTo.value && dateFrom.value > dateTo.value;

    dateFrom.setAttribute("aria-invalid", String(Boolean(invalidRange)));
    dateTo.setAttribute("aria-invalid", String(Boolean(invalidRange)));

    if (invalidRange) {
      filterError.textContent =
        "The start date must not be later than the end date. " +
        "Results below still show the last valid selection.";
      filterError.hidden = false;
      return;
    }

    filterError.hidden = true;

    const selected = filterObservations(data.observations, {
      dateFrom: dateFrom.value,
      dateTo: dateTo.value,
      search: search.value,
    });

    renderSummary(summarizeObservations(selected));
    renderStatusChart(selected);
    renderObservations(selected);

    setText(
      "selection-info",
      `Showing ${formatNumber(selected.length)} of ` +
        `${formatNumber(data.observations.length)} lot observations. ` +
        "All metrics below reflect this selection.",
    );
  }

  dateFrom.addEventListener("change", applyFilters);
  dateTo.addEventListener("change", applyFilters);
  search.addEventListener("input", applyFilters);

  document.getElementById("reset-filters").addEventListener("click", () => {
    dateFrom.value = "";
    dateTo.value = "";
    search.value = "";
    applyFilters();
  });

  applyFilters();
}

async function loadDashboard() {
  try {
    const response = await fetch("data/dashboard.json", { cache: "no-store" });

    if (!response.ok) {
      throw new Error(`Could not load dashboard data (HTTP ${response.status})`);
    }

    const data = await response.json();

    if (data.schema_version !== 1) {
      throw new Error("Unsupported dashboard data version");
    }

    if (!Array.isArray(data.observations) || !data.summary || !data.scope) {
      throw new Error("Incomplete dashboard data");
    }

    if (data.summary.total_lot_observations !== data.observations.length) {
      throw new Error("Dashboard observation counts do not match");
    }

    renderSnapshotInfo(data);
    initializeFilters(data);
    document.getElementById("dashboard-content").hidden = false;
  } catch (error) {
    console.error(error);
    document.getElementById("dashboard-content").hidden = true;
    setText("error", "The dashboard could not be loaded. Please try again later.");
    document.getElementById("error").hidden = false;
  } finally {
    document.getElementById("loading").hidden = true;
  }
}

document.getElementById("close-details").addEventListener("click", () => {
  document.getElementById("notice-details").close();
});

loadDashboard();
