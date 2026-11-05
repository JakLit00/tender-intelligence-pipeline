SELECT *
FROM {{ ref('mart_deadline_change_summary') }}
WHERE
    comparable_lot_observations <> (
        extended_lot_observations
        + shortened_lot_observations
        + unchanged_lot_observations
    )
    OR matched_lot_observations <> (
        comparable_lot_observations
        + quality_issue_lot_observations
        + missing_deadline_lot_observations
    )
    OR matched_lot_observations > total_lot_observations
    OR (
        matched_lot_observations = 0
        AND comparison_coverage_pct IS NOT NULL
    )
    OR (
        matched_lot_observations > 0
        AND (
            comparison_coverage_pct IS NULL
            OR comparison_coverage_pct NOT BETWEEN 0 AND 100
        )
    )
    OR (
        comparable_lot_observations = 0
        AND extension_rate_pct IS NOT NULL
    )
    OR (
        comparable_lot_observations > 0
        AND (
            extension_rate_pct IS NULL
            OR extension_rate_pct NOT BETWEEN 0 AND 100
        )
    )
    OR (
        extended_lot_observations = 0
        AND median_extension_hours IS NOT NULL
    )
    OR (
        extended_lot_observations > 0
        AND (
            median_extension_hours IS NULL
            OR median_extension_hours <= 0
        )
    )