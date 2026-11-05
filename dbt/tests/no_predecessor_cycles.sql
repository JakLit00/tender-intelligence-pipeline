WITH RECURSIVE eligible AS (
    SELECT notice.*
    FROM {{ source('prepared', 'notices') }} AS notice
    JOIN {{ source('ingestion', 'notices') }} AS raw_notice
        USING (publication_number)
    WHERE raw_notice.processing_status = 'succeeded'
),
edges AS (
    SELECT
        current_notice.publication_number AS current_publication,
        predecessor.publication_number AS previous_publication
    FROM eligible AS current_notice
    JOIN eligible AS predecessor
        ON (
            current_notice.reference_type = 'publication_number'
            AND predecessor.publication_number
                = current_notice.previous_publication_number
        ) OR (
            current_notice.reference_type = 'notice_version'
            AND predecessor.notice_id = current_notice.previous_notice_id
            AND predecessor.notice_version = current_notice.previous_notice_version
        )
),
walk AS (
    SELECT
        current_publication AS start_publication,
        previous_publication,
        ARRAY[current_publication, previous_publication] AS path,
        current_publication = previous_publication AS has_cycle
    FROM edges

    UNION ALL

    SELECT
        walk.start_publication,
        edges.previous_publication,
        array_append(walk.path, edges.previous_publication),
        edges.previous_publication = ANY(walk.path)
    FROM walk
    JOIN edges ON edges.current_publication = walk.previous_publication
    WHERE NOT walk.has_cycle
)
SELECT start_publication, path
FROM walk
WHERE has_cycle
