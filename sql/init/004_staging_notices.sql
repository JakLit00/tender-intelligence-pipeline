\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE staging.notices (
    publication_number text PRIMARY KEY,
    notice_id uuid NOT NULL,
    notice_version text NOT NULL,
    procedure_id uuid,
    notice_type text NOT NULL,
    publication_date date NOT NULL,

    changed_notice_identifier_raw text,
    reference_type text NOT NULL,
    previous_publication_number text,
    previous_notice_id uuid,
    previous_notice_version text,
    change_reason_code text,

    parsed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT staging_notices_source_fk
        FOREIGN KEY (publication_number)
        REFERENCES raw.notices (publication_number),

    CONSTRAINT staging_notices_version_check
        CHECK (notice_version ~ '^[0-9]{2}$'),

    CONSTRAINT staging_notices_previous_version_check
        CHECK (
            previous_notice_version IS NULL
            OR previous_notice_version ~ '^[0-9]{2}$'
        ),

    CONSTRAINT staging_notices_type_check
        CHECK (btrim(notice_type) <> ''),

    CONSTRAINT staging_notices_reference_type_check
        CHECK (
            reference_type IN (
                'missing',
                'publication_number',
                'notice_version',
                'unresolved'
            )
        ),

    -- Each reference format must populate only its own identifying fields.
    CONSTRAINT staging_notices_reference_fields_check
        CHECK (
            (
                reference_type IN ('missing', 'unresolved')
                AND previous_publication_number IS NULL
                AND previous_notice_id IS NULL
                AND previous_notice_version IS NULL
            )
            OR
            (
                reference_type = 'publication_number'
                AND previous_publication_number IS NOT NULL
                AND btrim(previous_publication_number) <> ''
                AND previous_notice_id IS NULL
                AND previous_notice_version IS NULL
            )
            OR
            (
                reference_type = 'notice_version'
                AND previous_publication_number IS NULL
                AND previous_notice_id IS NOT NULL
                AND previous_notice_version IS NOT NULL
            )
        ),

    CONSTRAINT staging_notices_raw_reference_check
        CHECK (
            (
                reference_type = 'missing'
                AND (
                    changed_notice_identifier_raw IS NULL
                    OR btrim(changed_notice_identifier_raw) = ''
                )
            )
            OR
            (
                reference_type <> 'missing'
                AND changed_notice_identifier_raw IS NOT NULL
                AND btrim(changed_notice_identifier_raw) <> ''
            )
        )
);

-- Support predecessor lookup by UUID and version without assuming uniqueness yet.
CREATE INDEX staging_notices_identity_idx
    ON staging.notices (notice_id, notice_version);

GRANT SELECT, INSERT, UPDATE
    ON staging.notices
    TO tender_app;

COMMIT;