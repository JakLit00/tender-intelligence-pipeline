WITH classified AS (
    SELECT
        *,
        CASE
            WHEN predecessor_match_status = 'no_reference'
                THEN 'no_reference'
            WHEN predecessor_match_status <> 'matched'
                THEN 'unresolved_predecessor'
            WHEN NOT predecessor_lot_found
                THEN 'missing_predecessor_lot'
            WHEN current_quality_issue IS NOT NULL
                OR previous_quality_issue IS NOT NULL
                THEN 'quality_issue'
            WHEN current_deadline_at IS NULL
                OR previous_deadline_at IS NULL
                THEN 'missing_exact_deadline'
            WHEN current_deadline_at > previous_deadline_at
                THEN 'extended'
            WHEN current_deadline_at < previous_deadline_at
                THEN 'shortened'
            ELSE 'unchanged'
        END AS deadline_change_status
    FROM {{ ref('int_lot_deadline_pairs') }}
)
SELECT
    publication_number,
    lot_id,
    predecessor_publication_number,
    predecessor_match_status,
    predecessor_lot_found,
    current_deadline_date,
    previous_deadline_date,
    current_deadline_at,
    previous_deadline_at,
    current_quality_issue,
    previous_quality_issue,
    deadline_change_status,
    CASE
        WHEN deadline_change_status IN ('extended', 'shortened', 'unchanged')
            THEN TRIM_SCALE(
                EXTRACT(
                    EPOCH FROM (current_deadline_at - previous_deadline_at)
                ) / 3600.0
            )
    END AS deadline_change_hours
FROM classified