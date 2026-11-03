# Business Logic

## Business objective

Help an IT services company discover relevant public procurement
notices from Polish buyers and track changes that may affect
its decision to prepare a bid.

The solution supports opportunity discovery and market analysis.
Users must verify procurement requirements in the original documents.

## Target user

A sales or business development specialist who reviews new notices
and monitors updates to relevant procurement procedures.

## Data scope

- Source: Tenders Electronic Daily (TED).
- Buyer country: Poland.
- Initial selection: notices matching CPV prefix 72.
- Coverage is limited to notices available in TED and matching
  the selection criteria. It does not represent the entire Polish
  IT procurement market.

## Business questions

1. Which notices were published during a selected period?
2. Which buyers and CPV categories appear most frequently?
3. Which publications explicitly refer to earlier notices as changes?
4. How did submission deadlines change across related publications?

## Expected outputs

- A searchable and filterable list of notices with links to TED.
- A history of explicitly linked publications and deadline changes.
- Summary charts for publication activity, buyers, and CPV categories.
- CSV exports of the displayed tables.
- Visibility of data freshness and relevant data completeness issues.

## Interpretation rules

- A publication is not equivalent to a procurement procedure.
- A newly published notice is not necessarily a new bidding opportunity.
- Publication date and pipeline retrieval time are separate concepts.
- Historical backfills must be distinguishable from routine monitoring.
- Missing values must not be interpreted as zero or as a business status.
- Missing predecessor notices must be reported as incomplete history.
- Submission deadlines must be extracted from verified XML paths
  and associated with the relevant procurement lot where applicable.
- Metrics must state whether they count publications, procedures,
  or lots.

## Topics requiring source verification

- Procedure and lot identifiers and their stability across publications.
- XML paths and semantics of submission deadlines.
- Formats used to reference changed notices.
- Rules for matching lots across related publications.