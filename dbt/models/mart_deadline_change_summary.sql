SELECT
    COUNT(*) AS total_lot_observations,

    COUNT(*) FILTER (
        WHERE predecessor_match_status = 'matched'
          AND predecessor_lot_found
    ) AS matched_lot_observations,

    COUNT(deadline_change_hours) AS comparable_lot_observations,

    COUNT(*) FILTER (
        WHERE deadline_change_status = 'extended'
    ) AS extended_lot_observations,

    COUNT(*) FILTER (
        WHERE deadline_change_status = 'shortened'
    ) AS shortened_lot_observations,

    COUNT(*) FILTER (
        WHERE deadline_change_status = 'unchanged'
    ) AS unchanged_lot_observations,

    COUNT(*) FILTER (
        WHERE deadline_change_status = 'quality_issue'
    ) AS quality_issue_lot_observations,

    COUNT(*) FILTER (
        WHERE deadline_change_status = 'missing_exact_deadline'
    ) AS missing_deadline_lot_observations,

    ROUND(
        100.0 * COUNT(deadline_change_hours)
        / NULLIF(
            COUNT(*) FILTER (
                WHERE predecessor_match_status = 'matched'
                  AND predecessor_lot_found
            ),
            0
        ),
        2
    ) AS comparison_coverage_pct,

    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE deadline_change_status = 'extended'
        )
        / NULLIF(COUNT(deadline_change_hours), 0),
        2
    ) AS extension_rate_pct,

    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY deadline_change_hours::double precision
    ) FILTER (
        WHERE deadline_change_status = 'extended'
    ) AS median_extension_hours

FROM {{ ref('fct_lot_deadline_changes') }}