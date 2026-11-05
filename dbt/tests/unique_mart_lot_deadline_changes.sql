SELECT
    publication_number,
    lot_id,
    COUNT(*) AS row_count
FROM {{ ref('mart_lot_deadline_changes') }}
GROUP BY
    publication_number,
    lot_id
HAVING COUNT(*) > 1