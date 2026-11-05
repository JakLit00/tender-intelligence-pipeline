SELECT
    changes.publication_number,
    changes.lot_id,
    scope.procedure_id,
    scope.publication_date,
    context.notice_title,
    context.buyer_names,
    context.notice_url,
    changes.predecessor_publication_number,
    changes.predecessor_match_status,
    changes.predecessor_lot_found,
    changes.previous_deadline_date,
    changes.current_deadline_date,
    changes.previous_deadline_at,
    changes.current_deadline_at,
    changes.previous_quality_issue,
    changes.current_quality_issue,
    changes.deadline_change_status,
    changes.deadline_change_hours
FROM {{ ref('fct_lot_deadline_changes') }} AS changes
INNER JOIN {{ ref('int_scope_notices') }} AS scope
    ON changes.publication_number = scope.publication_number
LEFT JOIN {{ ref('int_notice_business_context') }} AS context
    ON changes.publication_number = context.publication_number