import {
  filterObservations,
  summarizeObservations,
} from "./analytics.mjs";

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
  setText(
    "comparison-coverage",
    formatNumber(summary.comparison_coverage_pct, "%"),
  );
  setText("extension-rate", formatNumber(summary.extension_rate_pct, "%"));
  setText(
    "median-extension",
    formatNumber(summary.median_extension_hours, " h"),
  );
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

    fragment.appendChild(row);
  }

  if (sorted.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.textContent = "No observations match the selected filters.";
    row.appendChild(cell);
    fragment.appendChild(row);
  }

  document.getElementById("observations").replaceChildren(fragment);
  setText("row-count", `${formatNumber(observations.length)} observations`);
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

loadDashboard();