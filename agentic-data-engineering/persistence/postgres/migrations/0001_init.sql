-- Metadata plane: the transactional system of record.
--
-- Holds versioned entity state for both twins, the durable relationship log the
-- graph plane is projected from, gate assessments, and an append-only
-- hash-chained audit ledger.
--
-- Entities are stored as JSONB rather than one table per type. The metamodel
-- has 66 entity types and will gain more; a table per type would make every
-- additive change a migration, which is exactly the coupling ADR-0002 exists to
-- avoid. Identity, version, type and twin are promoted to real columns so the
-- parts that are queried are indexed.

BEGIN;

CREATE TABLE IF NOT EXISTS metamodel_entity (
    entity_type        TEXT        NOT NULL,
    entity_id          TEXT        NOT NULL,
    version            TEXT        NOT NULL,
    metamodel_version  TEXT        NOT NULL,
    twin               TEXT        NOT NULL DEFAULT 'SHARED',
    payload            JSONB       NOT NULL,
    content_hash       TEXT        NOT NULL,
    is_current         BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ,
    PRIMARY KEY (entity_type, entity_id, version),

    CONSTRAINT entity_twin_valid CHECK (twin IN ('TECHNICAL', 'DELIVERY', 'SHARED'))
);

-- Exactly one version of an entity may be current at a time.
CREATE UNIQUE INDEX IF NOT EXISTS metamodel_entity_current_uidx
    ON metamodel_entity (entity_type, entity_id)
    WHERE is_current;

CREATE INDEX IF NOT EXISTS metamodel_entity_type_idx ON metamodel_entity (entity_type);
CREATE INDEX IF NOT EXISTS metamodel_entity_twin_idx ON metamodel_entity (twin);
CREATE INDEX IF NOT EXISTS metamodel_entity_payload_gin ON metamodel_entity USING GIN (payload);

COMMENT ON TABLE metamodel_entity IS
    'Versioned entity state across both twins. Every row records the metamodel '
    'version it was written under so old rows stay interpretable.';


-- Durable relationship log. The graph plane is a projection of this.
CREATE TABLE IF NOT EXISTS metamodel_relationship (
    relationship_id   TEXT        PRIMARY KEY,
    rel_type          TEXT        NOT NULL,
    source_type       TEXT        NOT NULL,
    source_id         TEXT        NOT NULL,
    target_type       TEXT        NOT NULL,
    target_id         TEXT        NOT NULL,
    provenance        TEXT        NOT NULL,
    confidence        DOUBLE PRECISION,
    discovered_by     TEXT,
    discovered_at     TIMESTAMPTZ NOT NULL,
    valid_from        TIMESTAMPTZ,
    valid_until       TIMESTAMPTZ,
    human_verified_by TEXT,
    human_verified_at TIMESTAMPTZ,
    source_document   TEXT,
    source_section    TEXT,
    extraction_method TEXT,
    attributes        JSONB       NOT NULL DEFAULT '{}'::JSONB,
    payload           JSONB       NOT NULL,

    -- The provenance invariants, enforced by the database as well as the model.
    -- Application-level validation is bypassable; this is not.
    CONSTRAINT relationship_provenance_valid CHECK (
        provenance IN ('OBSERVED', 'INFERRED', 'HUMAN_VERIFIED', 'CERTIFIED')
    ),
    CONSTRAINT inferred_requires_confidence CHECK (
        provenance <> 'INFERRED' OR confidence IS NOT NULL
    ),
    CONSTRAINT observed_is_certain CHECK (
        provenance <> 'OBSERVED' OR confidence = 1.0
    ),
    CONSTRAINT verified_requires_human CHECK (
        provenance NOT IN ('HUMAN_VERIFIED', 'CERTIFIED') OR human_verified_by IS NOT NULL
    ),
    CONSTRAINT confidence_in_range CHECK (
        confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)
    ),
    -- Semantically extracted facts must be attributable to a document.
    CONSTRAINT extraction_is_attributable CHECK (
        extraction_method <> 'SEMANTIC_EXTRACTION' OR source_document IS NOT NULL
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS metamodel_relationship_natural_uidx
    ON metamodel_relationship (source_type, source_id, rel_type, target_type, target_id);

CREATE INDEX IF NOT EXISTS metamodel_relationship_source_idx
    ON metamodel_relationship (source_type, source_id);
CREATE INDEX IF NOT EXISTS metamodel_relationship_target_idx
    ON metamodel_relationship (target_type, target_id);
CREATE INDEX IF NOT EXISTS metamodel_relationship_type_idx
    ON metamodel_relationship (rel_type);


-- Append-only, hash-chained audit ledger.
CREATE TABLE IF NOT EXISTS audit_ledger (
    sequence      BIGSERIAL   PRIMARY KEY,
    decision_id   TEXT        NOT NULL,
    entry_hash    TEXT        NOT NULL UNIQUE,
    previous_hash TEXT,
    payload       JSONB       NOT NULL,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_ledger_decision_idx ON audit_ledger (decision_id);

-- Make "append-only" true rather than merely intended. A ledger a privileged
-- process can quietly rewrite is not evidence of anything.
CREATE OR REPLACE RULE audit_ledger_no_update AS
    ON UPDATE TO audit_ledger DO INSTEAD NOTHING;
CREATE OR REPLACE RULE audit_ledger_no_delete AS
    ON DELETE TO audit_ledger DO INSTEAD NOTHING;

COMMENT ON TABLE audit_ledger IS
    'Append-only decision ledger. Each entry hashes over its payload and its '
    'predecessor, so tampering breaks the chain and is detectable.';


-- Gate assessments: computed readiness at a point in time.
-- Persisted because a gate decision is an audit record -- a reviewer must be
-- able to see what the approver was shown, not just what they decided.
CREATE TABLE IF NOT EXISTS gate_assessment (
    assessment_id   TEXT        PRIMARY KEY,
    gate_key        TEXT        NOT NULL,
    subject_type    TEXT        NOT NULL,
    subject_id      TEXT        NOT NULL,
    status          TEXT        NOT NULL,
    overall_score   DOUBLE PRECISION NOT NULL,
    dimensions      JSONB       NOT NULL,
    blocking_items  JSONB       NOT NULL DEFAULT '[]'::JSONB,
    assessed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT gate_status_valid CHECK (status IN ('PASS', 'CONDITIONAL', 'BLOCKED')),
    CONSTRAINT gate_score_in_range CHECK (overall_score >= 0.0 AND overall_score <= 1.0),
    -- A BLOCKED assessment must say what blocked it. "No" without a reason is
    -- the thing that makes governance tooling get switched off.
    CONSTRAINT blocked_must_explain CHECK (
        status <> 'BLOCKED' OR jsonb_array_length(blocking_items) > 0
    )
);

CREATE INDEX IF NOT EXISTS gate_assessment_gate_idx ON gate_assessment (gate_key);
CREATE INDEX IF NOT EXISTS gate_assessment_subject_idx
    ON gate_assessment (subject_type, subject_id);


-- Checklist outcomes: the per-item record behind a gate's checklist dimension.
CREATE TABLE IF NOT EXISTS checklist_outcome (
    outcome_id     TEXT        PRIMARY KEY,
    checklist_key  TEXT        NOT NULL,
    subject_type   TEXT        NOT NULL,
    subject_id     TEXT        NOT NULL,
    complete       BOOLEAN     NOT NULL,
    completion     DOUBLE PRECISION NOT NULL,
    results        JSONB       NOT NULL,
    waived_count   INTEGER     NOT NULL DEFAULT 0,
    evaluated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT completion_in_range CHECK (completion >= 0.0 AND completion <= 1.0)
);

CREATE INDEX IF NOT EXISTS checklist_outcome_checklist_idx
    ON checklist_outcome (checklist_key);


-- Context bundles: what each agent was actually shown, for replay.
CREATE TABLE IF NOT EXISTS context_bundle (
    bundle_id      TEXT        PRIMARY KEY,
    bundle_hash    TEXT        NOT NULL,
    policy_id      TEXT        NOT NULL,
    policy_version TEXT        NOT NULL,
    agent_id       TEXT,
    task_id        TEXT,
    contract_id    TEXT,
    budget_tokens  INTEGER     NOT NULL,
    tokens_used    INTEGER     NOT NULL,
    manifest       JSONB       NOT NULL,
    assembled_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT bundle_within_budget CHECK (tokens_used <= budget_tokens)
);

CREATE INDEX IF NOT EXISTS context_bundle_hash_idx ON context_bundle (bundle_hash);
CREATE INDEX IF NOT EXISTS context_bundle_agent_idx ON context_bundle (agent_id);

COMMENT ON TABLE context_bundle IS
    'One row per context assembly. Equal bundle_hash means an agent saw exactly '
    'the same context, which is what makes a decision replayable.';


CREATE TABLE IF NOT EXISTS schema_migration (
    migration_id TEXT        PRIMARY KEY,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migration (migration_id)
VALUES ('0001_init')
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
