WITH eligible_predecessors AS (
    SELECT notice.*
    FROM {{ source('prepared', 'notices') }} AS notice
    INNER JOIN {{ source('ingestion', 'notices') }} AS raw_notice
        ON notice.publication_number = raw_notice.publication_number
    WHERE raw_notice.processing_status = 'succeeded'
),
candidates AS (
    SELECT
        current_notice.publication_number,
        current_notice.procedure_id,
        current_notice.reference_type,
        predecessor.publication_number AS candidate_publication_number,
        predecessor.procedure_id AS candidate_procedure_id
    FROM {{ ref('int_scope_notices') }} AS current_notice
    LEFT JOIN eligible_predecessors AS predecessor
        ON (
            current_notice.reference_type = 'publication_number'
            AND predecessor.publication_number
                = current_notice.previous_publication_number
        )
        OR (
            current_notice.reference_type = 'notice_version'
            AND predecessor.notice_id
                = current_notice.previous_notice_id
            AND predecessor.notice_version
                = current_notice.previous_notice_version
        )
),
matches AS (
    SELECT
        publication_number,
        procedure_id,
        reference_type,
        COUNT(candidate_publication_number) AS match_count,
        MIN(candidate_publication_number) AS candidate_publication_number,
        BOOL_OR(
            candidate_publication_number = publication_number
        ) AS has_self_reference,
        BOOL_OR(
            procedure_id IS NOT NULL
            AND candidate_procedure_id IS NOT NULL
            AND procedure_id <> candidate_procedure_id
        ) AS has_procedure_mismatch
    FROM candidates
    GROUP BY publication_number, procedure_id, reference_type
),
classified AS (
    SELECT
        *,
        CASE
            WHEN reference_type = 'missing' THEN 'no_reference'
            WHEN reference_type = 'unresolved' THEN 'unsupported_reference'
            WHEN match_count = 0 THEN 'not_found'
            WHEN match_count > 1 THEN 'ambiguous'
            WHEN has_self_reference THEN 'self_reference'
            WHEN has_procedure_mismatch THEN 'procedure_mismatch'
            ELSE 'matched'
        END AS match_status
    FROM matches
)
SELECT
    publication_number,
    reference_type,
    match_count,
    match_status,
    CASE
        WHEN match_status = 'matched'
            THEN candidate_publication_number
    END AS predecessor_publication_number
FROM classified