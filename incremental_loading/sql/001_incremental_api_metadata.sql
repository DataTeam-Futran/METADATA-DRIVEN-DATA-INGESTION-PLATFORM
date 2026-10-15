CREATE TABLE IF NOT EXISTS ingest.incremental_runtime_config (
    mapping_version_id BIGINT PRIMARY KEY
        REFERENCES map.mapping_version(mapping_version_id) ON DELETE CASCADE,
    tenant_id BIGINT NOT NULL
        REFERENCES sec.tenant(tenant_id) ON DELETE RESTRICT,
    schema_strategy VARCHAR(32) NOT NULL DEFAULT 'STRICT'
        CHECK (schema_strategy IN ('STRICT', 'ADD_MISSING_COLUMNS')),
    duplicate_strategy VARCHAR(16) NOT NULL DEFAULT 'SKIP'
        CHECK (duplicate_strategy IN ('ALLOW', 'SKIP', 'FAIL')),
    batch_size INTEGER NOT NULL DEFAULT 5000 CHECK (batch_size > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (tenant_id > 0)
);

CREATE TABLE IF NOT EXISTS ingest.incremental_field_metadata (
    field_id BIGINT PRIMARY KEY
        REFERENCES catalog.dataset_field(field_id) ON DELETE CASCADE,
    tenant_id BIGINT NOT NULL
        REFERENCES sec.tenant(tenant_id) ON DELETE RESTRICT,
    is_primary_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_watermark BOOLEAN NOT NULL DEFAULT FALSE,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingest.incremental_execution (
    execution_id UUID PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES sec.tenant(tenant_id),
    system_id BIGINT NOT NULL,
    environment_id BIGINT NOT NULL,
    source_connection_id BIGINT NOT NULL
        REFERENCES conn.connection_profile(connection_id),
    load_type_code VARCHAR(32) NOT NULL CHECK (load_type_code = 'INCREMENTAL'),
    load_strategy_code VARCHAR(32) NOT NULL CHECK (load_strategy_code = 'APPEND'),
    execution_watermark TIMESTAMPTZ NOT NULL,
    status_code VARCHAR(16) NOT NULL
        CHECK (status_code IN ('RUNNING', 'SUCCESS', 'FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMPTZ,
    rows_read BIGINT NOT NULL DEFAULT 0 CHECK (rows_read >= 0),
    rows_inserted BIGINT NOT NULL DEFAULT 0 CHECK (rows_inserted >= 0),
    rows_skipped BIGINT NOT NULL DEFAULT 0 CHECK (rows_skipped >= 0),
    failed_table TEXT,
    failed_step TEXT,
    error_type TEXT,
    error_message TEXT,
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE TABLE IF NOT EXISTS ingest.incremental_execution_table (
    execution_id UUID NOT NULL
        REFERENCES ingest.incremental_execution(execution_id) ON DELETE CASCADE,
    mapping_version_id BIGINT NOT NULL
        REFERENCES map.mapping_version(mapping_version_id),
    tenant_id BIGINT NOT NULL REFERENCES sec.tenant(tenant_id),
    source_dataset_id BIGINT NOT NULL REFERENCES catalog.dataset(dataset_id),
    target_dataset_id BIGINT NOT NULL REFERENCES catalog.dataset(dataset_id),
    source_table TEXT NOT NULL,
    target_table TEXT NOT NULL,
    previous_watermark TEXT,
    execution_watermark TIMESTAMPTZ NOT NULL,
    source_count BIGINT NOT NULL DEFAULT 0 CHECK (source_count >= 0),
    inserted_count BIGINT NOT NULL DEFAULT 0 CHECK (inserted_count >= 0),
    duplicate_count BIGINT NOT NULL DEFAULT 0 CHECK (duplicate_count >= 0),
    schema_change_count INTEGER NOT NULL DEFAULT 0 CHECK (schema_change_count >= 0),
    status_code VARCHAR(16) NOT NULL
        CHECK (status_code IN ('RUNNING', 'SUCCESS', 'FAILED')),
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMPTZ,
    PRIMARY KEY (execution_id, mapping_version_id),
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE INDEX IF NOT EXISTS ix_incremental_execution_source_started
    ON ingest.incremental_execution
       (tenant_id, source_connection_id, started_at DESC);

CREATE INDEX IF NOT EXISTS ix_incremental_execution_table_mapping
    ON ingest.incremental_execution_table
       (tenant_id, mapping_version_id, started_at DESC);