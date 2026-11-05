# Dashboard JSON contract, version 1

`dashboard/contract.mjs` validates the public snapshot in the browser and in `scripts/check_dashboard_metrics.mjs`. Refresh and ZIP creation run that same validator before replacing their previous output. No schema framework is required.

Every listed field is required, including nullable fields. Unknown fields are rejected at the root, in scope and summary, and in each observation. Objects or arrays cannot substitute for scalar fields. Errors identify the location and rule, without printing source values.

## Root and scope

| Field | Contract |
| --- | --- |
| `schema_version` | Integer `1`. |
| `generated_at` | UTC timestamp ending in `Z`. |
| `scope` | Object containing exactly the three scope fields below. |
| `summary` | Object containing exactly the metrics below. |
| `observations` | Array of observation objects. Empty is allowed. |
| `scope.notice_count` | Non-negative safe integer. Counts notices, including notices without lots. |
| `scope.first_publication_date` | Calendar date; null only for an empty scope. |
| `scope.last_publication_date` | Calendar date; null only for an empty scope. Must not precede the first date. |

Dates use valid `YYYY-MM-DD` calendar values, with years from 0001 to 9999. Timestamps use `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`, with one to six optional fractional digits. The exporter converts aware timestamps to UTC. Microseconds remain significant when checking deadline differences.

Each observation's publication date must lie within the inclusive scope range. Its publication number contributes to the distinct notice count, which may be smaller than `scope.notice_count` when some notices have no lots.

## Observations

| Fields | Contract |
| --- | --- |
| `publication_number` | Normalized number-year string: 1–8 digits, no leading zero, then `-` and four year digits. |
| `lot_id` | Non-empty string; `(publication_number, lot_id)` must be unique. |
| `procedure_id` | Canonical lowercase UUID string or null. |
| `publication_date` | Calendar date. |
| `notice_title`, `buyer_names` | Non-empty string or null. Source text is rendered as text, not HTML. |
| `notice_url` | HTTPS URL on `ted.europa.eu`, without credentials or a non-default port, or null. The UI constructs its own TED link from the publication number. |
| `predecessor_publication_number` | Normalized publication number only for a matched predecessor; otherwise null. Cannot equal the current publication for a matched pair. |
| `predecessor_match_status` | `no_reference`, `unsupported_reference`, `not_found`, `ambiguous`, `self_reference`, `procedure_mismatch` or `matched`. |
| `predecessor_lot_found` | Boolean; true requires a matched predecessor. |
| `previous_deadline_date`, `current_deadline_date` | Calendar date or null. An exact deadline or a quality flag requires the corresponding source date. |
| `previous_deadline_at`, `current_deadline_at` | UTC timestamp or null. |
| `previous_quality_issue`, `current_quality_issue` | Null or `conflicting_timezone_offsets`; a flagged deadline must have a null exact timestamp. |
| `deadline_change_status` | `no_reference`, `unresolved_predecessor`, `missing_predecessor_lot`, `quality_issue`, `missing_exact_deadline`, `extended`, `shortened` or `unchanged`. |
| `deadline_change_hours` | Finite number for extended/shortened/unchanged, otherwise null. Must agree with the exact timestamp difference and classification. |

Classification follows the same precedence as SQL, described in [business logic](business-logic.md). A valid shape alone is insufficient: contradictory status, predecessor and deadline values are rejected.

## Summary

The eight counts are non-negative safe integers: `total_lot_observations`, `matched_lot_observations`, `comparable_lot_observations`, `extended_lot_observations`, `shortened_lot_observations`, `unchanged_lot_observations`, `quality_issue_lot_observations`, `missing_deadline_lot_observations`.

`comparison_coverage_pct` and `extension_rate_pct` are finite numbers in `[0, 100]`, or null when their denominators are zero. `median_extension_hours` is a positive finite number, or null without extensions.

All summary metrics are recalculated from observations and compared with the exported SQL summary. Counts must match exactly; floating-point metrics use relative tolerance `1e-9` with an absolute floor of `1e-9`. This checks implementation agreement, not source completeness or freshness.
