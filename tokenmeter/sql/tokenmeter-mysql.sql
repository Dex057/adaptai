-- ============================================================================
--  tokenmeter — criação das tabelas (MySQL 8 / Railway)
--
--  Cole no console: serviço MySQL → aba Database → Data → campo de query.
--  Substitui o `tokenmeter migrate`. Só CREATE — não toca em nada existente.
--
--  Desfazer:  DROP TABLE tm_usage_event_tag;  DROP TABLE tm_usage_event;
-- ============================================================================

CREATE TABLE tm_usage_event (
    event_id VARCHAR(36) NOT NULL,
    schema_version SMALLINT NOT NULL,
    occurred_at DATETIME NOT NULL,
    recorded_at DATETIME NOT NULL,
    occurred_date DATE NOT NULL,
    service VARCHAR(64) NOT NULL,
    environment VARCHAR(32) NOT NULL,
    sdk_version VARCHAR(32) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(128) NOT NULL,
    model_family VARCHAR(64),
    operation VARCHAR(32) NOT NULL,
    feature VARCHAR(128) NOT NULL,
    feature_source VARCHAR(16) NOT NULL,
    run_id VARCHAR(36),
    input_tokens BIGINT NOT NULL,
    output_tokens BIGINT NOT NULL,
    cache_write_tokens BIGINT NOT NULL,
    cache_read_tokens BIGINT NOT NULL,
    total_tokens BIGINT NOT NULL,
    cost_usd NUMERIC(20, 10),
    priced SMALLINT NOT NULL,
    pricing_version VARCHAR(64),
    status VARCHAR(16) NOT NULL,
    error_type VARCHAR(64),
    duration_ms INTEGER,
    provider_request_id VARCHAR(128),
    tags_json TEXT,
    PRIMARY KEY (event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE tm_usage_event_tag (
    event_id VARCHAR(36) NOT NULL,
    tag_key VARCHAR(64) NOT NULL,
    tag_value VARCHAR(255) NOT NULL,
    PRIMARY KEY (event_id, tag_key),
    FOREIGN KEY(event_id) REFERENCES tm_usage_event (event_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX ix_tm_ue_feature_date ON tm_usage_event (feature, occurred_date);
CREATE INDEX ix_tm_ue_occurred ON tm_usage_event (occurred_at);
CREATE INDEX ix_tm_uet_lookup ON tm_usage_event_tag (tag_key, tag_value, event_id);

-- Conferência:
--   SHOW TABLES LIKE 'tm_%';
--   SELECT COUNT(*) FROM tm_usage_event;
