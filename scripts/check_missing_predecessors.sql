\set ON_ERROR_STOP on
\pset pager off

SELECT
    current_notice.publication_number,
    current_notice.reference_type,
    current_notice.changed_notice_identifier_raw,
    current_notice.previous_publication_number,
    current_notice.previous_notice_id,
    current_notice.previous_notice_version
FROM staging.notices AS current_notice
WHERE current_notice.reference_type IN (
    'publication_number',
    'notice_version'
)
AND NOT EXISTS (
    SELECT 1
    FROM staging.notices AS predecessor
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
)
ORDER BY
    current_notice.reference_type,
    current_notice.publication_number
LIMIT 15;