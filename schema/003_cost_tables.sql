-- ============================================================================
-- Cost Tracking Tables — Per-agent, per-user token budgets and spend
-- ============================================================================

-- Token usage records (per-request granularity)
CREATE TABLE token_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    agent_id TEXT NOT NULL,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cost NUMERIC(10, 6) NOT NULL DEFAULT 0,
    cached_tokens INTEGER DEFAULT 0,
    cache_savings NUMERIC(10, 6) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Budget configurations
CREATE TABLE budgets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,       -- 'agent', 'user', 'org'
    entity_id TEXT NOT NULL,
    daily_limit NUMERIC(10, 2) NOT NULL,
    per_request_limit NUMERIC(10, 2) NOT NULL DEFAULT 5.00,
    alert_threshold NUMERIC(3, 2) NOT NULL DEFAULT 0.80,
    circuit_breaker_threshold NUMERIC(3, 2) NOT NULL DEFAULT 1.00,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, entity_type, entity_id)
);

-- Cost alerts
CREATE TABLE cost_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,        -- 'threshold', 'spike', 'anomaly', 'circuit_breaker'
    severity TEXT NOT NULL DEFAULT 'warning',
    message TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Daily cost aggregation (materialized for dashboard performance)
CREATE TABLE daily_cost_summary (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    agent_id TEXT NOT NULL,
    model TEXT NOT NULL,
    total_requests INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost NUMERIC(10, 4) DEFAULT 0,
    avg_cost_per_request NUMERIC(10, 6) DEFAULT 0,
    avg_latency_ms INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    UNIQUE(org_id, date, agent_id, model)
);

-- Indexes for cost queries
CREATE INDEX idx_token_usage_agent ON token_usage(agent_id, created_at DESC);
CREATE INDEX idx_token_usage_org ON token_usage(org_id, created_at DESC);
CREATE INDEX idx_token_usage_date ON token_usage(created_at DESC);
CREATE INDEX idx_cost_alerts_org ON cost_alerts(org_id, created_at DESC);
CREATE INDEX idx_daily_cost_date ON daily_cost_summary(org_id, date DESC);
