SELECT
    current_lot.publication_number,
    current_lot.lot_id,
    link.match_status AS predecessor_match_status,
    link.predecessor_publication_number,
    previous_lot.lot_id IS NOT NULL AS predecessor_lot_found,
    current_lot.submission_deadline_local_date AS current_deadline_date,
    previous_lot.submission_deadline_local_date AS previous_deadline_date,
    current_lot.submission_deadline_at AS current_deadline_at,
    previous_lot.submission_deadline_at AS previous_deadline_at,
    current_lot.submission_deadline_quality_issue AS current_quality_issue,
    previous_lot.submission_deadline_quality_issue AS previous_quality_issue
FROM {{ ref('int_notice_predecessors') }} AS link
INNER JOIN {{ source('prepared', 'notice_lots') }} AS current_lot
    ON current_lot.publication_number = link.publication_number
LEFT JOIN {{ source('prepared', 'notice_lots') }} AS previous_lot
    ON previous_lot.publication_number = link.predecessor_publication_number
    AND previous_lot.lot_id = current_lot.lot_id