# Business Logic

## Problem and intended use

An IT services bid team needs to discover relevant procurement publications and understand whether an update changes the time available to prepare an offer. Reviewing isolated notices can hide earlier deadlines or confuse a correction with a new opportunity.

The pipeline links explicit publication history and compares submission deadlines for corresponding lots. The dashboard supports retrospective analysis and investigation of individual changes. It is not an authoritative register of currently open tenders, a bid recommendation engine, or an automated alerting service.

## Scope and cohort

The search selects TED notices with buyer country `POL`, CPV prefix `72`, notice type `cn-standard`, and a publication date inside the requested window. It does not cover the entire Polish procurement market or every IT-related procurement classification.

Two discovery flags distinguish notices retrieved by the scope search from those retrieved as predecessors. A notice may have both flags. Successfully prepared scope-search publications form the analytics cohort. History-only publications supply previous values but are not independently added to that cohort.

Publication date, XML issue date, retrieval time and dashboard generation time have different meanings. Dashboard date filters select the publication date of the current observation, not its deadline date. Normal incremental ingestion ends at the previous UTC calendar day and rechecks an overlap window.

Backfill also accepts only completed UTC days. A requested range ending today or in the future is rejected before a pipeline run is created.

## Entities and grain

| Entity | Meaning |
| --- | --- |
| Publication number | Identifier of a TED publication, normalized from the source representation. |
| Notice UUID and version | An alternative reference identity; a version alone is not globally unique. |
| Procedure ID | Groups notices belonging to a procurement procedure. |
| Lot ID | Identifies a part of a procurement within its notice; it is not a globally unique identifier. |
| Dashboard observation | One `(publication_number, lot_id)` pair from the reporting cohort. |

A procedure may generate multiple publications, and a publication may contain multiple lots. Repeated changes to the same procedure or lot produce multiple observations. A notice title describes the procurement; it is not a structured catalogue of individual products. Buyer names preserve the source's multiple buyers, displayed together; they do not identify a single lead buyer.

## Predecessor resolution

Use the explicit changed-notice reference, parsed as either a publication number or a notice UUID plus version. Candidate predecessors must be successfully prepared. Validate the match rather than inferring it from similar titles or publication dates.

History retrieval uses that same processing-status requirement for referring notices and predecessors. Older staging rows retained after failed reprocessing are ineligible. History-only notices may reveal further predecessors without becoming reporting observations. Cycles among successfully prepared notices fail dbt build and block replacement of the dashboard snapshot.

| Match status | Interpretation |
| --- | --- |
| `no_reference` | No explicit predecessor reference; not an incomplete-history error by itself. It does not prove this is the first publication of the procedure. |
| `unsupported_reference` | Reference format cannot be resolved by the implemented rules. |
| `not_found` | Reference exists but the corresponding prepared notice is unavailable. |
| `ambiguous` | More than one candidate matches. |
| `self_reference` | The reference points to the current publication. |
| `procedure_mismatch` | The candidate belongs to a different procedure. |
| `matched` | One eligible predecessor passes the matching checks. |

Lots are paired using the same lot ID within the matched predecessor. A renamed or reorganized lot cannot safely be matched using its title alone. The analysis compares adjacent linked publications, not necessarily the first and latest notice in a procedure.

## Deadline handling

Extract deadlines from the lot's tender submission deadline period, not other date fields that may describe contract duration. Preserve the raw date and time, the local calendar date and, when safely derivable, a timezone-aware timestamp.

When date and time specify conflicting UTC offsets, retain the raw values and local date, set the exact timestamp to null, and flag `conflicting_timezone_offsets`. Do not choose an offset silently. A local date alone is insufficient for an exact elapsed-hour comparison.

Elapsed hours use the difference between exact instants. Daylight-saving changes can therefore make a calendar-day interval differ from a multiple of 24 hours. For example, 22 October 2026 at 09:00 +02:00 to 3 November 2026 at 09:00 +01:00 is **289 hours**, not 288.

## Classification order

The first applicable rule wins:

1. No predecessor reference → `no_reference`.
2. Predecessor status other than matched → `unresolved_predecessor`.
3. Predecessor notice exists but corresponding lot does not → `missing_predecessor_lot`.
4. Either deadline has a recorded quality issue → `quality_issue`.
5. Either exact deadline is missing → `missing_exact_deadline`.
6. Current deadline is later → `extended`.
7. Current deadline is earlier → `shortened`.
8. Equal exact deadlines → `unchanged`.

For the last three classes:

`deadline_change_hours = (current_deadline_at - previous_deadline_at) in seconds / 3600`

Other classes have a null change value. Null means unavailable or not comparable, never zero. Fractional hours are retained.

## Metrics

All counts below refer to publication–lot observations after the applicable dashboard filters.

| Exported metric | Definition |
| --- | --- |
| `total_lot_observations` | All selected observations. |
| `matched_lot_observations` | Matched predecessor notice and corresponding predecessor lot found. Includes pairs whose deadlines are not comparable. |
| `comparable_lot_observations` | Observations with a numeric deadline change: extended, shortened or unchanged. |
| `extended_lot_observations` | Positive deadline changes. |
| `shortened_lot_observations` | Negative deadline changes. |
| `unchanged_lot_observations` | Zero deadline changes. |
| `quality_issue_lot_observations` | Observations classified as `quality_issue`. |
| `missing_deadline_lot_observations` | Observations classified as `missing_exact_deadline`. |
| `comparison_coverage_pct` | `100 × comparable / matched`. |
| `extension_rate_pct` | `100 × extended / comparable`. |
| `median_extension_hours` | Median positive change among extended observations only. |

Zero denominators produce null percentages. No extensions produce a null median. Percentages are rounded to two decimal places. For an even number of extensions, the median is the average of the two middle sorted values.

The comparison coverage denominator is matched lot pairs, not all observations. It therefore does not measure overall predecessor resolution. The status distribution provides the complementary view of excluded observations.

The headline extension rate is not the percentage of all Polish IT tenders whose deadlines were extended. The sample is restricted by search criteria, publication dates, explicit references and deadline completeness. Procedures with repeated amendments contribute repeatedly.

## Dashboard interpretation

Date boundaries are inclusive. Text search checks publication numbers, notice titles and buyer names. Metrics and status counts are recalculated for the filtered observations. Snapshot metadata describes the full exported cohort and its generation time.

The detail view provides current and previous deadlines, reference context and a link to TED. Displayed exact timestamps use UTC; preserved local dates retain the source's calendar-date context. The public dashboard changes only after a new snapshot is published. The [5–10 November 2026 trial](development-notes.md#validation-evidence-and-boundaries) confirmed growth in published observations and consistent summary metrics across four snapshots.

The browser calculates metrics from the exported rows. Before replacing the local snapshot, the refresh command verifies the unfiltered JavaScript metrics against the dbt summary. Agreement checks implementation consistency; it does not prove the source data is complete or correct.

## Limitations

- No exhaustive market coverage, procurement outcome analysis, spend estimation or award-value metrics.
- No guarantee that missing references mean an original notice, or that matching lot IDs capture reorganized lots.
- No inference of cancelled, closed or currently open opportunity status from deadline changes alone.
- No current buyer-ranking, CPV-distribution chart or CSV export is claimed by this documentation.
- Historical results can change when late publications, missing predecessors or corrected source content are retrieved.
