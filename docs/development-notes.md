# Development Notes

## Purpose and development sequence

This document records implementation decisions and operational knowledge. The [public dashboard](https://jaklit00.github.io/tender-intelligence-pipeline/) serves the latest published snapshot independently of the local database. A manual refresh and publication trial spanning 5–10 November 2026 was checked against published snapshots and the latest dbt results. Daily execution is not automated.

1. **Inspect real TED data.** Examine search metadata and XML before defining the relational model. Distinguish publication numbers, notice UUIDs, versions, procedures and lot identifiers. Verify submission deadline paths with real change chains.
2. **Build preparation functions.** Separate extraction from normalization and business classification. Cover publication-number references and UUID-version references with focused tests.
3. **Introduce PostgreSQL storage.** Separate operational tracking, source payloads and prepared entities. Add constraints and integration tests before connecting a larger ingestion run.
4. **Implement ingestion and history.** Add pagination, pandas-based search-result preparation, XML download and repeatable processing. Resolve missing predecessors in bounded batches.
5. **Exercise real failures.** A run with 132 publications initially failed for ten publications because deadline dates and times contained conflicting offsets. Preserve those observations with a quality flag and no exact deadline instead of discarding them or inventing a timezone. Retry successfully processed all ten; twelve lots carried the conflict flag.
6. **Add incremental coverage.** Use successful coverage and an overlap window, rather than simply selecting the largest observed publication date. Repeated runs skip unchanged prepared payloads.
7. **Build dbt analytics.** Resolve predecessor matches, pair lots, classify deadline changes and calculate summary metrics. Enrich reporting with notice titles, buyer names and TED links.
8. **Build the static dashboard and refresh command.** Export with a read-only role, support filtering and details in the browser, and validate JavaScript metrics against dbt before replacing the snapshot.
9. **Standardize quality and verify portability.** Add Ruff and Prettier checks to CI. Verify a complete refresh from an empty, isolated database on Ubuntu under WSL2 in addition to Windows operation.

## Storage and transformations

| Layer | Responsibility |
| --- | --- |
| `ops.pipeline_runs` | Run mode, date window, timing, completion status and error context. |
| `ops.run_notices` | Publication outcomes associated with each run. |
| `raw.notices` | Search metadata, original XML, discovery flags and processing state. |
| `staging.notices` | Prepared identities, publication dates and predecessor references. |
| `staging.notice_lots` | Lot-level deadline source values, normalized values and quality flags. |
| `analytics` | dbt views serving comparisons, business context and reporting. |

```mermaid
flowchart TD
    A["int_scope_notices"] --> B["int_notice_predecessors"]
    B --> C["int_lot_deadline_pairs"]
    C --> D["fct_lot_deadline_changes"]
    D --> E["mart_deadline_change_summary"]
    D --> F["mart_lot_deadline_changes"]
    A --> G["int_notice_business_context"]
    G --> F
    A --> F
```

The diagram shows the main model dependencies; source tables also provide the prepared notices, lots and metadata used by these models. Views keep the small analytical layer transparent and avoid introducing incremental dbt materialization before it is needed.

## Key decisions and tradeoffs

**Python and pandas.** Python owns networking, parsing, validation and orchestration. pandas prepares tabular search results, including publication-number normalization, date handling and uniqueness checks. XML traversal and transactional writes do not require DataFrames. SQL/dbt owns analytical joins and metrics.

**Identity before convenience.** UUID-version references are supported alongside publication numbers. A procedure ID groups related publications but is not a substitute for an explicit predecessor link. Matching requires checks for ambiguity, self-reference and procedure consistency.

**Atomic prepared writes.** Notice and lot changes belong in one transaction. If any part fails, rollback prevents a partially updated prepared record. Raw payloads and processing errors retain diagnostic context. Analytics selects successfully prepared data.

**Repeatability.** Unchanged XML already processed successfully is skipped. Failed payloads remain eligible for retry. This limits duplicate work but does not make the entire multi-stage refresh one database transaction.

**History boundaries.** A history run processes a bounded selection of unresolved references. Both referring notices and candidate predecessors must have `raw.processing_status = 'succeeded'`; retained staging rows for pending/failed XML do not count as prepared. History-only notices remain eligible to reveal deeper links, while the reporting cohort still requires scope-search discovery. Newly discovered predecessors may themselves refer to older notices, so several batches can be required. The refresh orchestrator checks remaining work, detects lack of progress and enforces a batch limit. The `no_predecessor_cycles` dbt test checks all eligible history, including self-references and UUID-version links. A cycle makes build fail and prevents refresh from replacing the snapshot; the SQL diagnostic also remains available for inspection.

**Incremental coverage.** Successful backfill/incremental coverage determines the next search window, with overlap to revisit recent publications. Retry/history runs are not substitutes for complete date-window ingestion. Overlap reduces missed late changes but does not guarantee discovery of every arbitrarily late correction; a historical backfill remains necessary in that situation.

Backfill rejects ranges ending today or later in UTC, both in the CLI and in the domain function before creating a run. Previously recorded invalid coverage is not rewritten automatically. If an older run claimed incomplete/future days, review that run before explicitly correcting its coverage record; a new successful run does not invalidate the old one.

**Retry and network limits.** `retry_failed_processing.py --source-run-id ID` retries failed items using stored XML. It rejects unfinished and history source runs. A missing XML item remains failed with download guidance; other items continue. Source outcomes are retained. Backfill/incremental recover downloads, and history retrieval is retried through `run_history.py`. The TED client allows three attempts for selected HTTP failures and transient transport failures (timeouts, connection interruptions/refusals, temporary DNS and incomplete bodies), with backoff. Certificate errors, permanent DNS errors and unclassified failures are not retried. Retry-After values above the configured delay limit stop the request. Each response is limited to 20 MiB of actually read bytes, regardless of Content-Length; an oversized response fails without retry.

**Timezone conflicts.** The source can supply a date ending in `Z` and a time with a different offset. The system does not silently favor one. Local date, raw values and a quality issue remain available, while exact comparison is withheld.

**Separate reporting role.** The exporter connects as `tender_reporter`, with SELECT access to analytics. Default privileges for models created by `tender_dbt` preserve this access when models are recreated. Application, dbt and reporting credentials are separate.

**Consistent export.** Summary, scope and detail rows are read in a repeatable-read, read-only transaction. Serialization handles dates, UTC timestamps, decimals and UUIDs; unsupported values fail explicitly. A candidate JSON file is checked before same-filesystem replacement of the final snapshot.

The shared [dashboard contract](dashboard-contract.md) rejects missing/unknown fields, invalid types and dates, inconsistent statuses and duplicate publication-lot pairs. It also recalculates summary metrics. It runs in refresh, ZIP building and the browser; contract validation is not a freshness guarantee. The standalone `export_dashboard.py` writes JSON without invoking Node; validate that output before using it as a public snapshot.

**Static delivery.** HTML, CSS, JavaScript and JSON can present a frozen result without a running database or Python server in production. Browser code does not need database credentials. Local preview uses Python's HTTP server. GitHub Pages publication is a separate step, not an effect of ingestion.

**Lightweight orchestration.** One Python command is proportionate to this manually operated portfolio pipeline. It runs configuration checks, ingestion, history, dbt, export and metric validation sequentially. There is no scheduler or concurrent-run lock; operate one refresh at a time.

## Validation evidence and boundaries

The manual trial covered refresh, analytical output, JSON validation and publication to `gh-pages`. Four historical snapshots passed the real JavaScript contract and metric consistency validator:

| Generated (UTC, 2026) | Commit | Notices | Lot observations |
| --- | --- | ---: | ---: |
| 5 Nov, 22:53 | `d6da029126` | 204 | 401 |
| 6 Nov, 10:54 | `57e324df4c` | 217 | 427 |
| 10 Nov, 00:25 | `9ae114b773` | 250 | 480 |
| 10 Nov, 13:18 | `2b8ec41ab2` | 250 | 480 |

No earlier publication–lot keys disappeared. The final two snapshots retained identical counts and summary metrics. The latest local dbt build on 10 November completed with **7 successful models and 29 passing tests**. These are dated observations, not fixed expectations for future runs. This check did not inspect every database run, TED retrieval completeness or Pages deployment logs, and does not establish uninterrupted daily execution.

The GitHub Actions workflow uses Ubuntu 24.04 and installs Python, Node.js, application dependencies and dbt from a clean checkout. It starts an isolated PostgreSQL test service, runs Python and dashboard tests, builds/tests dbt and checks Ruff/Prettier. The workflow does not run the full live TED ingestion scenario.

Earlier full refreshes were verified on Windows and Ubuntu 26.04 under WSL2 with Python 3.13.18 on 5 November 2026. Both produced the same cohort counts; equal counts alone do not prove byte-identical datasets.

Mocked orchestration tests exercise stage failures and preservation of the previous snapshot. Database integration tests exercise actual transactions and constraints. dbt unit tests use controlled inputs to check classification; data tests check built relations. Passing tests do not constitute a complete security audit or a guarantee of source completeness.

Integration tests now build dbt views using a temporary profile fixed to the test database, exercise a nonempty SQL → reporting-role export → real JavaScript validator flow, reject cycles through real dbt build, and check denied role permissions. Install `.venv-dbt` and Node before running them. Publisher tests use temporary local bare remotes and cover dry runs, history preservation, malformed ZIPs, unexpected branch files, concurrent updates and safe diagnostics. They never contact the real publishing remote.

From the project root with the application environment active, start the separate test database before running checks:

```bash
docker compose -p tender-intelligence-tests -f compose.yaml -f compose.test.yaml up -d --wait postgres
python -m pytest -q
python scripts/run_dbt.py build --target test
python -m ruff check src scripts tests
python -m ruff format src scripts tests --check
node --test tests/dashboard/*.test.mjs
npm run format:check
```

Use `npm.cmd` instead of `npm` if PowerShell blocks the npm script. Test database data is disposable. Integration tests use a dedicated temporary dbt profile and do not load `.env`.

## Fresh setup and environment isolation

Follow the [README](../README.md) for installation. Python is constrained to `>=3.13,<3.14`; an installed Python 3.14 does not satisfy that declaration. Create `.venv` for the application and `.venv-dbt` for dbt using Python 3.13. Windows environments cannot be reused on Linux.

The WSL verification used a separate checkout in the Linux filesystem, separate native Python/Node installations and a Compose project named `tender-intelligence-linux-check`, with port 5436 and its own volume. These were isolation measures for the existing development machine, not additional requirements for a new user.

Normal working and test databases use ports 5434 and 5435. `docker compose -p ...` selects the project; a port override is also necessary when starting a second working database on the same Docker engine. Test overrides use `!override` so ports are replaced rather than appended.

SQL files in `sql/init/` initialize a fresh volume. They are not an automatic migration runner for an existing volume. Apply reviewed changes explicitly to existing databases and keep fresh initialization equivalent. Changing an environment password alone does not update the corresponding existing PostgreSQL role.

## Daily operating procedure

From the project root, activate the application environment, start Docker and ensure native Node.js is on PATH:

```bash
docker compose up -d --wait postgres
python scripts/refresh_dashboard.py
```

Run one refresh at a time. Before publishing:

1. Require exit code zero and the final `Local dashboard refreshed successfully` message, following successful dbt build and JSON/metric validation.
2. Record the printed `Incremental run`, `History runs`, `Scope notices` and `Lot observations`. Check the counts against the previous run; unchanged counts can be legitimate on a day with no matching publications.
3. Inspect `generated_at`, the scope date range and public fields in `dashboard/data/dashboard.json`. Preview the dashboard with `python -m http.server 8000 --bind 127.0.0.1 --directory dashboard`; check filters and a sample TED link at `http://127.0.0.1:8000`.
4. After those checks succeed, run `python scripts/publish_dashboard.py --publish` with repository write access. Keep the reviewed snapshot and page files unchanged until publication completes.
5. Check the GitHub Pages deployment result for the new `gh-pages` commit, then open the public dashboard. Compare its generation time, scope and unfiltered counts with the reviewed local snapshot. A successful push alone does not prove Pages has finished deploying.

**Stop publication after a failed refresh.** The previous valid JSON is deliberately retained and can still pass the publisher's contract and metric checks. Those checks establish consistency, not freshness or success of the latest ingestion. Fix the failed stage and repeat the refresh and review first.

### Build, dry run and publication

The optional local build is useful for inspecting the package; it is not required as a separate step in daily operation:

```bash
python scripts/build_dashboard.py
```

It creates `dist/dashboard.zip` with only `index.html`, `styles.css`, `app.js`, `analytics.mjs`, `contract.mjs`, `data/dashboard.json` and `.nojekyll`. The copied JSON must satisfy the [dashboard contract](dashboard-contract.md), and JavaScript recalculates metrics from its observations and compares them with the exported dbt summary. Validation occurs before atomic replacement of an older ZIP. Building does not contact GitHub or refresh the database.

Both publisher modes require a clean Git working tree, configured Git `user.name` and `user.email`, and Git authentication with appropriate repository access. Configure credentials through Git's credential mechanism; do not embed tokens in commands or documentation. The destination is fixed to **JakLit00/tender-intelligence-pipeline** in `scripts/publish_dashboard.py`, rather than inferred from a fork's `origin`. Commit reviewed code changes before publishing; the local snapshot and ZIP are ignored by Git.

```bash
python scripts/publish_dashboard.py
```

Without `--publish`, this is a **networked dry run**: it rebuilds and validates the ZIP, contacts GitHub, and reads the existing `gh-pages` branch into a temporary Git repository. If content changed, it creates a local deployment commit identifying the source code commit and executes `git push --dry-run`. The remote branch is unchanged, but authentication may be required and the local ZIP is replaced.

```bash
python scripts/publish_dashboard.py --publish
```

Actual publication rebuilds and validates the package again; it does not reuse an immutable artifact approved by the dry run. Preserve the same snapshot and site files between inspection and publication. A normal push appends the deployment commit to `gh-pages` history, rejects concurrent remote updates and skips identical content. Unexpected tracked files on that branch or unexpected archive entries stop publication. Git failures report the operation and a safe diagnostic category without echoing credential-bearing stderr.

The temporary repository is removed afterwards; it does not switch the source checkout's branch. The script updates `gh-pages` but does not configure GitHub Pages. Pages serves the branch's root directory, and its deployment must be checked separately. The project's CI workflow runs tests and has no daily refresh or publication step.

### Comparing runs across days

`ops.pipeline_runs` stores run modes, statuses, date ranges and timing; `ops.run_notices` records each publication's outcome for a run. Use the run IDs printed by refresh to inspect failures or skips. A successful ingestion run alone does not establish that later dbt, export or publication stages succeeded.

The `gh-pages` history preserves the published `data/dashboard.json` versions. Compare snapshots between deployment commits to inspect changes in generation time, scope, observations and metrics; record the deployment commit alongside the run IDs when investigating daily differences.

To inspect recent runs:

```sql
SELECT run_id, run_mode, date_from, date_to, status,
       started_at, finished_at, error_message
FROM ops.pipeline_runs
ORDER BY run_id DESC
LIMIT 10;
```

Diagnostic scripts `scripts/check_predecessor_matches.sql`, `scripts/check_missing_predecessors.sql` and `scripts/check_predecessor_cycles.sql` help distinguish absent references, unavailable referenced notices and cycles. Inspect their results after changes to history handling or when investigating unexpected comparisons.

## Failure handling and troubleshooting

| Symptom | Check or action |
| --- | --- |
| Docker connection fails | Start Docker and confirm the intended context and engine. |
| Port already allocated | Inspect existing containers; choose an isolated override rather than stopping unrelated projects. |
| Role authentication fails after editing `.env` | Existing role passwords have not changed automatically. Apply an explicit credential update or use the correct original local credentials. |
| dbt executable missing | Install `requirements-dbt.txt` inside `.venv-dbt` for the current OS. |
| Node missing in WSL but npm exists | Check both executable paths; Windows npm on PATH is not a native Linux Node installation. |
| History batch limit reached | Review progress and unresolved links; rerun to continue, or deliberately adjust the limit after inspection. |
| Refresh fails after ingestion | Database progress may already be committed; the previous final JSON remains until a successful validated replacement. Fix the failed stage and rerun. |
| Dashboard fetch fails when opening an HTML file | Serve the dashboard through the local HTTP preview command, not `file://`. |
| Tests import two modules with the same basename | Use distinct test module names or an intentional package/import configuration. |
| dbt dependency download fails with HTTP 504 | Distinguish an external installation failure from a test failure; inspect the failing step before rerunning. |

Do not run `docker compose down --volumes` on the working project as routine cleanup. It removes stored data. The test configuration is disposable; scope cleanup commands to the intended test project.

## Repository practice and remaining release work

Feature branches and pull requests keep changes reviewable. CI checks precede merging; merge commits preserve feature boundaries. Ruff handles Python import ordering, linting and formatting. Prettier formats dashboard HTML/CSS/JavaScript. Neither is a security scanner.

Secrets, local payloads, generated snapshots and virtual environments stay out of Git. The current static UI creates text content through DOM APIs and constructs TED links from publication identifiers; these choices still require review alongside dependency, export and workflow configuration.

Use the [README daily commands](../README.md#daily-use) and [publication checks](#build-dry-run-and-publication) for subsequent runs; retain run IDs and deployment commits when extending the recorded trial.

The audit fixes require no table or role migration. Deploy the Python/JavaScript changes together and run the normal dbt build to execute the additional cycle check. Review any existing failed source records or previously invalid coverage separately; no automatic repair of historical operational records is performed.

Actions are pinned to commits verified against the official repositories. Full Python dependency locking and a lightweight Windows CI job remain separate proposals; neither is introduced by these fixes.
