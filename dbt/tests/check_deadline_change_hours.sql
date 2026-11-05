SELECT *
FROM {{ ref('fct_lot_deadline_changes') }}
WHERE
    (
        deadline_change_status IN ('extended', 'shortened', 'unchanged')
        AND deadline_change_hours IS NULL
    )
    OR (
        deadline_change_status NOT IN ('extended', 'shortened', 'unchanged')
        AND deadline_change_hours IS NOT NULL
    )
    OR (
        deadline_change_status = 'extended'
        AND deadline_change_hours <= 0
    )
    OR (
        deadline_change_status = 'shortened'
        AND deadline_change_hours >= 0
    )
    OR (
        deadline_change_status = 'unchanged'
        AND deadline_change_hours <> 0
    )