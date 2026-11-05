SELECT
    publication_number,
    lot_id
FROM {{ ref('int_lot_deadline_pairs') }}
GROUP BY publication_number, lot_id
HAVING COUNT(*) > 1