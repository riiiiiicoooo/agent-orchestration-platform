-- ============================================================================
-- Row-Level Security Policies — Tenant isolation at the database level
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE cost_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_cost_summary ENABLE ROW LEVEL SECURITY;

-- Organization isolation: users can only see data from their org
CREATE POLICY org_isolation_users ON users
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

CREATE POLICY org_isolation_agents ON agents
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

CREATE POLICY org_isolation_sessions ON sessions
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

CREATE POLICY org_isolation_tasks ON tasks
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

CREATE POLICY org_isolation_conversations ON conversations
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

CREATE POLICY org_isolation_knowledge_docs ON knowledge_documents
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

CREATE POLICY org_isolation_knowledge_chunks ON knowledge_chunks
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

CREATE POLICY org_isolation_token_usage ON token_usage
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

CREATE POLICY org_isolation_budgets ON budgets
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

CREATE POLICY org_isolation_cost_alerts ON cost_alerts
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

CREATE POLICY org_isolation_daily_cost ON daily_cost_summary
    USING (org_id = (SELECT org_id FROM users WHERE clerk_id = current_setting('app.current_user_id', true)));

-- Role-based: only admins and managers can modify budgets
CREATE POLICY budget_write_policy ON budgets
    FOR ALL
    USING (
        (SELECT role FROM users WHERE clerk_id = current_setting('app.current_user_id', true))
        IN ('admin', 'manager')
    );
