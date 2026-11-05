SELECT
    notice.publication_number,
    notice.notice_id,
    notice.notice_version,
    notice.procedure_id,
    notice.notice_type,
    notice.publication_date,
    notice.reference_type,
    notice.previous_publication_number,
    notice.previous_notice_id,
    notice.previous_notice_version,
    notice.change_reason_code
FROM {{ source('prepared', 'notices') }} AS notice
INNER JOIN {{ source('ingestion', 'notices') }} AS raw_notice
    ON notice.publication_number = raw_notice.publication_number
WHERE raw_notice.discovered_by_scope_search
  AND raw_notice.processing_status = 'succeeded'