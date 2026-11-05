WITH metadata AS (
    SELECT
        scope.publication_number,
        raw_notice.search_metadata
    FROM {{ ref('int_scope_notices') }} AS scope
    INNER JOIN {{ source('ingestion', 'notices') }} AS raw_notice
        ON scope.publication_number = raw_notice.publication_number
)

SELECT
    metadata.publication_number,
    NULLIF(
        BTRIM(metadata.search_metadata #>> '{notice-title,pol}'),
        ''
    ) AS notice_title,
    buyers.buyer_names,
    NULLIF(
        BTRIM(metadata.search_metadata #>> '{links,html,POL}'),
        ''
    ) AS notice_url
FROM metadata
-- Aggregate buyers before joining to preserve one row per publication.
LEFT JOIN LATERAL (
    SELECT
        STRING_AGG(
            DISTINCT NULLIF(BTRIM(buyer.name), ''),
            '; ' ORDER BY NULLIF(BTRIM(buyer.name), '')
        ) AS buyer_names
    FROM JSONB_ARRAY_ELEMENTS_TEXT(
        CASE
            WHEN JSONB_TYPEOF(
                metadata.search_metadata #> '{buyer-name,pol}'
            ) = 'array'
                THEN metadata.search_metadata #> '{buyer-name,pol}'
            ELSE '[]'::JSONB
        END
    ) AS buyer(name)
) AS buyers ON TRUE