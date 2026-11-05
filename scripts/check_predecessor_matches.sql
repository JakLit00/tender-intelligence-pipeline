\set ON_ERROR_STOP on
\pset pager off

WITH eligible AS (
    SELECT notice.*
    FROM staging.notices AS notice
    JOIN raw.notices AS source USING (publication_number)
    WHERE source.processing_status = 'succeeded'
),
predecessor_matches AS (
    SELECT
        current_notice.publication_number,
        current_notice.reference_type,
        current_notice.changed_notice_identifier_raw,
        matches.candidate_count,
        matches.candidate_publications,
        matches.has_procedure_mismatch
    FROM eligible AS current_notice
    CROSS JOIN LATERAL (
        SELECT
            count(*) AS candidate_count,
            array_agg(
                predecessor.publication_number
                ORDER BY predecessor.publication_number
            ) AS candidate_publications,
            bool_or(
                current_notice.procedure_id IS NOT NULL
                AND predecessor.procedure_id IS NOT NULL
                AND current_notice.procedure_id <> predecessor.procedure_id
            ) AS has_procedure_mismatch
        FROM eligible AS predecessor
        WHERE (
            current_notice.reference_type = 'publication_number'
            AND predecessor.publication_number =
                current_notice.previous_publication_number
        )
        OR (
            current_notice.reference_type = 'notice_version'
            AND predecessor.notice_id =
                current_notice.previous_notice_id
            AND predecessor.notice_version =
                current_notice.previous_notice_version
        )
    ) AS matches
),
classified AS (
    SELECT
        *,
        CASE
            WHEN reference_type = 'missing' THEN 'no_reference'
            WHEN reference_type = 'unresolved' THEN 'unsupported_reference'
            WHEN candidate_count = 0 THEN 'not_found'
            WHEN candidate_count > 1 THEN 'ambiguous'
            WHEN publication_number = ANY(candidate_publications)
                THEN 'self_reference'
            WHEN has_procedure_mismatch THEN 'procedure_mismatch'
            ELSE 'matched'
        END AS match_status
    FROM predecessor_matches
)
SELECT
    reference_type,
    match_status,
    count(*) AS notices
FROM classified
GROUP BY reference_type, match_status
ORDER BY reference_type, match_status;
