-- ============================================================================
-- Memory Tables — Three-tier memory architecture
-- ============================================================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Knowledge base documents
CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,           -- claims, underwriting, customer_service, etc.
    source TEXT NOT NULL,           -- file_upload, resolved_case, policy_excerpt, faq
    title TEXT,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Knowledge chunks with embeddings (Layer 3)
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),         -- text-embedding-3-small dimension
    chunk_index INTEGER NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast vector similarity search
CREATE INDEX idx_knowledge_chunks_embedding ON knowledge_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- BM25 full-text search index
ALTER TABLE knowledge_chunks ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX idx_knowledge_chunks_fts ON knowledge_chunks USING gin(search_vector);

-- Domain filtering index
CREATE INDEX idx_knowledge_chunks_domain ON knowledge_chunks(domain);
CREATE INDEX idx_knowledge_documents_domain ON knowledge_documents(domain);

-- Agent memory (per-agent persistent context)
CREATE TABLE agent_memory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id TEXT NOT NULL,
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    ttl_seconds INTEGER,            -- NULL = persistent
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    UNIQUE(agent_id, org_id, key)
);

CREATE INDEX idx_agent_memory_agent ON agent_memory(agent_id, org_id);
CREATE INDEX idx_agent_memory_expires ON agent_memory(expires_at) WHERE expires_at IS NOT NULL;
