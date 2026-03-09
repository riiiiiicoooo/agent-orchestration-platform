# Agent Orchestration Platform

**Production-Grade Multi-Agent Orchestration for Mid-Market Enterprises**

A supervisor-pattern agent orchestration platform that coordinates specialized AI agents across enterprise workflows. Built for Apex Financial Services, a 300-person insurance TPA managing claims processing, underwriting support, and customer service across 12 carrier partnerships. Unified 7 siloed AI tools into a single orchestration layer with centralized cost tracking, shared memory, and production-grade guardrails — reducing combined LLM spend from $47K/month to $19K/month while increasing task completion rates from 67% to 94%.

---

## Modern Stack (Production Infrastructure)

This project includes comprehensive modern tooling infrastructure for production-grade deployment:

### AI & Observability
- **LangSmith Tracing** — Distributed tracing for all agent workflows with @traceable decorators
- **Custom Evaluators** — Task completion accuracy (target ≥ 90%), cost efficiency (target ≤ $0.12/task), hallucination detection, guardrail effectiveness
- **Evaluation Datasets** — 200+ labeled agent interactions across claims, underwriting, and customer service domains
- **Cost Attribution** — Per-agent, per-task, per-user token tracking with budget enforcement and anomaly alerts

### Async Job Processing
- **Trigger.dev** — Long-running agent workflows (30s-5min) with checkpointing between orchestration stages
- **Multi-Agent Pipelines** — Fan-out task decomposition, parallel agent execution, fan-in result aggregation
- **Error Handling** — Per-agent circuit breakers, exponential backoff retry, dead-letter queue for failed tasks

### Workflow Automation
- **n8n Workflows** — Two production workflows:
  - **agent_task_router.json** — Inbound request webhook → intent classification → agent selection → execution → response
  - **cost_anomaly_monitor.json** — Hourly LangSmith cost audit → per-agent budget check → Slack/email alerts (>20% budget spike)

### Authentication & Authorization
- **Clerk Integration** — SSO, SAML, passwordless auth with role-based middleware
- **Next.js Middleware** — Route protection, role-based access control (Admin/Manager/Analyst)
- **Tenant Isolation** — Organization-based agent access boundaries enforced at middleware + database level

### Database & Migrations
- **Supabase PostgreSQL** — Managed PostgreSQL with pgvector, RLS policies, and storage buckets
- **Migration System** — Supabase-compatible DDL with tenant-level RLS policies for each table
- **Vector Search** — HNSW indexes for semantic memory retrieval across agent conversation history
- **Three-Tier Memory** — Redis (session state, <1ms) → PostgreSQL (conversation history) → pgvector (long-term knowledge)

### Email & Notifications
- **React Email Templates** — TypeScript/JSX email components:
  - `AgentAlertEmail` — Critical agent failure notifications with error context
  - `CostAlertEmail` — Budget threshold warnings with spend breakdown
  - `EscalationEmail` — Human-in-the-loop approval requests with action context

### Deployment & CI/CD
- **GitHub Actions** — Automated testing, linting, and deployment pipeline
- **Docker Compose** — Full local development environment (FastAPI + PostgreSQL + Redis + pgvector)
- **Vercel** — Dashboard frontend deployment with preview environments

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway (FastAPI)                      │
│              Authentication · Rate Limiting · Routing         │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
    ┌──────────▼──────────┐         ┌─────────▼──────────┐
    │   Supervisor Agent   │         │   Guardrail Layer   │
    │   (LangGraph Core)   │◄───────►│  PII · Budget · Auth │
    │                      │         │  Schema · Compliance  │
    └──────┬───────────────┘         └──────────────────────┘
           │
    ┌──────┼──────────┬──────────────┬──────────────┐
    ▼      ▼          ▼              ▼              ▼
┌───────┐ ┌───────┐ ┌───────────┐ ┌──────────┐ ┌─────────┐
│Claims │ │Under- │ │Customer   │ │Document  │ │Analytics│
│Agent  │ │writing│ │Service    │ │Processing│ │Agent    │
│       │ │Agent  │ │Agent      │ │Agent     │ │         │
└───┬───┘ └───┬───┘ └─────┬─────┘ └────┬─────┘ └────┬────┘
    │         │           │            │            │
    └─────────┴───────────┴────────────┴────────────┘
                          │
              ┌───────────▼───────────┐
              │     Shared Tools       │
              │  MCP · APIs · Search   │
              │  Database · Knowledge  │
              └───────────┬───────────┘
                          │
    ┌─────────┬───────────┼───────────┬─────────┐
    ▼         ▼           ▼           ▼         ▼
┌───────┐ ┌───────┐ ┌─────────┐ ┌───────┐ ┌───────┐
│Redis  │ │Postgres│ │pgvector │ │Claude │ │GPT-4o │
│State  │ │History │ │Knowledge│ │Primary│ │Fallback│
└───────┘ └───────┘ └─────────┘ └───────┘ └───────┘
```

## Agent Architecture

### Supervisor Pattern
The platform uses a supervisor agent that decomposes incoming tasks, routes to specialized agents, and aggregates results. This pattern was chosen over mesh or pipeline because:
1. **Predictable routing** — Claims tasks always go to Claims Agent
2. **Centralized cost control** — Supervisor enforces per-agent budgets
3. **Easier debugging** — Single coordination point for trace analysis
4. **Progressive autonomy** — Start supervised, gradually increase agent independence

### Specialized Agents

| Agent | Role | LLM | Avg Latency | Cost/Task |
|-------|------|-----|-------------|-----------|
| Claims Processing | Intake classification, damage estimation, coverage verification | Claude 3.5 Sonnet | 2.1s | $0.08 |
| Underwriting Support | Risk assessment, policy analysis, premium calculation | GPT-4o | 3.4s | $0.14 |
| Customer Service | Inquiry routing, FAQ response, status updates | Claude Haiku | 0.8s | $0.02 |
| Document Processing | OCR extraction, classification, data normalization | Claude 3.5 Sonnet | 4.2s | $0.11 |
| Analytics | Report generation, trend analysis, KPI computation | GPT-4o | 5.1s | $0.16 |

### Three-Tier Memory Architecture
```
Layer 1: Redis (Session State)         — TTL: 30 min — Active agent context, tool results
Layer 2: PostgreSQL (Conversation)     — TTL: 90 days — Full interaction history, decisions
Layer 3: pgvector (Long-Term Knowledge)— Persistent — Embeddings of resolved cases, policies
```

---

## Client Context

**Client:** Apex Financial Services
**Industry:** Insurance — Third Party Administrator (TPA)
**Size:** 300 employees, 12 carrier partnerships
**Annual Premium Volume:** $850M across property, casualty, and specialty lines

**Problem:**
Apex had deployed 7 separate AI tools over 18 months — each solving one workflow but running independently. A chatbot for customer inquiries (Intercom + GPT-4), a claims classifier (custom fine-tuned model), a document OCR pipeline (Azure Document Intelligence), an underwriting risk scorer, a fraud detection model, an analytics report generator, and an email response drafter. Combined LLM spend was $47K/month with 40% redundant token usage (each tool maintained its own context, often re-processing the same documents). No unified monitoring, no shared memory, and no centralized guardrails — one agent hallucinated a coverage determination that went to a policyholder before anyone caught it.

**Solution:**
Unified orchestration platform with a supervisor agent coordinating 5 specialized agents through a shared state layer. The supervisor classifies incoming requests, routes to the appropriate agent (or chains multiple agents for complex tasks), and enforces guardrails before any output reaches end users. Shared pgvector knowledge base eliminates redundant document processing. Per-agent budget caps with circuit breakers prevent cost runaway. Human-in-the-loop gates on coverage determinations and claim approvals ensure no hallucinated outputs reach policyholders.

**Results:**
- LLM spend: $47K/month → $19K/month (60% reduction)
- Task completion rate: 67% → 94%
- Mean time to resolve customer inquiry: 4.2 hours → 12 minutes
- Hallucination incidents reaching end users: 3/month → 0
- Agent coordination overhead: Manual (email chains) → Automated (<2s routing)

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Backend** | FastAPI (Python) | Native LangGraph/CrewAI support, async, auto-docs |
| **Agent Framework** | LangGraph | Production-grade state machines, checkpointing, human-in-the-loop |
| **Primary LLM** | Claude 3.5 Sonnet | Best extraction accuracy, prompt caching, MCP native |
| **Secondary LLM** | GPT-4o | Stronger on structured reasoning tasks (underwriting, analytics) |
| **Routing LLM** | Claude Haiku | Fast classification (<200ms) at 1/10th the cost |
| **Database** | Supabase PostgreSQL | Managed, pgvector built-in, RLS policies, real-time |
| **Vector Search** | pgvector (HNSW) | Unified with relational data, no separate vector DB ops |
| **Session State** | Redis | Sub-ms latency for active agent context |
| **Message Queue** | Redis Streams | Inter-agent communication, task distribution |
| **Observability** | LangSmith + Datadog | Agent tracing + infrastructure monitoring |
| **Auth** | Clerk | SSO/SAML, role-based access, tenant isolation |
| **Async Jobs** | Trigger.dev | Long-running workflows with checkpointing |
| **Workflow Automation** | n8n | Cost monitoring, alert routing, scheduled reports |
| **Frontend** | Next.js + React | Dashboard with real-time agent status |
| **Deployment** | Docker + Vercel | Containerized backend, managed frontend |

---

## Key Technical Decisions

### 1. Supervisor vs. Mesh Pattern
**Chose supervisor** because Apex's workflows have clear domain boundaries (claims ≠ underwriting ≠ customer service). Mesh would add coordination complexity without benefit for well-defined routing.

### 2. LangGraph over CrewAI
**Chose LangGraph** for production because it provides explicit state machines with checkpointing. CrewAI's role-based abstraction is elegant for prototyping but LangGraph's graph-based approach gives better control over failure handling and human-in-the-loop gates.

### 3. pgvector over Pinecone
**Chose pgvector** because Apex's knowledge base is <5M vectors (well within pgvector's sweet spot) and keeping vectors in PostgreSQL eliminates a separate operational dependency. Single query can JOIN vector similarity with relational metadata.

### 4. Multi-Model Routing
**Chose multi-model** because no single LLM excels at everything. Claude dominates extraction and document analysis. GPT-4o is stronger on structured reasoning. Haiku handles simple routing at 1/10th the cost. The provider abstraction layer enables swapping without code changes.

### 5. Deterministic Guardrails
**Chose deterministic** (regex, schema validation, budget caps) over LLM-as-judge for guardrails. Insurance regulators need to understand exactly why output was blocked. "The AI said the other AI was safe" is insufficient for compliance.

---

## Project Structure

```
agent-orchestration-platform/
├── src/
│   ├── orchestrator/          # Supervisor agent + LangGraph workflows
│   │   ├── supervisor.py      # Main supervisor agent (task decomposition + routing)
│   │   ├── graph.py           # LangGraph state machine definition
│   │   ├── state.py           # Shared state schema
│   │   └── router.py          # Intent classification + agent selection
│   ├── agents/                # Specialized domain agents
│   │   ├── base.py            # Base agent class with common interface
│   │   ├── claims.py          # Claims processing agent
│   │   ├── underwriting.py    # Underwriting support agent
│   │   ├── customer_service.py# Customer inquiry agent
│   │   ├── document.py        # Document processing agent
│   │   └── analytics.py       # Analytics and reporting agent
│   ├── tools/                 # Shared tool registry
│   │   ├── registry.py        # MCP-compatible tool registry
│   │   ├── database.py        # Database query tools
│   │   ├── search.py          # Vector + BM25 hybrid search
│   │   └── external.py        # External API integrations
│   ├── providers/             # LLM provider abstraction
│   │   ├── base.py            # Provider interface
│   │   ├── anthropic.py       # Claude integration
│   │   ├── openai.py          # GPT-4o integration
│   │   └── router.py          # Multi-model routing logic
│   ├── memory/                # Three-tier memory system
│   │   ├── session.py         # Redis session state (Layer 1)
│   │   ├── conversation.py    # PostgreSQL history (Layer 2)
│   │   └── knowledge.py       # pgvector long-term (Layer 3)
│   ├── guardrails/            # Safety and compliance layer
│   │   ├── engine.py          # Guardrail evaluation engine
│   │   ├── pii.py             # PII detection (Presidio)
│   │   ├── budget.py          # Per-agent budget enforcement
│   │   ├── schema.py          # Output schema validation
│   │   └── compliance.py      # Insurance compliance rules
│   ├── middleware/             # API middleware
│   │   ├── auth.py            # Clerk JWT validation
│   │   ├── rate_limit.py      # Per-user rate limiting
│   │   └── cost_tracking.py   # Request-level cost attribution
│   ├── api/                   # FastAPI endpoints
│   │   ├── routes.py          # API route definitions
│   │   ├── websocket.py       # Real-time agent status
│   │   └── models.py          # Pydantic request/response models
│   ├── config/                # Configuration
│   │   ├── settings.py        # Environment-based settings
│   │   └── agents.py          # Agent configuration registry
│   └── main.py                # FastAPI application entry point
├── schema/                    # Database schema
│   ├── 001_core_tables.sql    # Agents, tasks, conversations
│   ├── 002_memory_tables.sql  # Memory tiers, embeddings
│   ├── 003_cost_tables.sql    # Token usage, budgets, alerts
│   └── 004_rls_policies.sql   # Row-level security
├── evals/                     # LangSmith evaluation suite
│   ├── datasets/              # Ground-truth test data
│   ├── evaluators.py          # Custom evaluation functions
│   └── runner.py              # Evaluation pipeline
├── dashboard/                 # Next.js monitoring dashboard
├── langsmith/                 # LangSmith configuration
├── n8n/                       # n8n workflow definitions
├── trigger-jobs/              # Trigger.dev job definitions
├── clerk/                     # Auth configuration
├── mcp/                       # MCP server definitions
├── docs/                      # Documentation
├── docker-compose.yml         # Local development environment
├── Makefile                   # Development commands
├── requirements.txt           # Python dependencies
├── vercel.json                # Dashboard deployment config
└── .github/                   # CI/CD workflows
```

---

## Development

```bash
# Local setup
make setup          # Install dependencies, configure environment
make dev            # Start FastAPI + PostgreSQL + Redis via Docker Compose
make test           # Run test suite
make eval           # Run LangSmith evaluation pipeline

# Agent operations
make agent-status   # Check all agent health
make agent-cost     # View current cost attribution
make agent-trace    # Open LangSmith trace viewer
```

---

## Metrics & Observability

### Real-Time Dashboard
- Active agent status (online/error/recovering)
- Latency percentiles (p50, p95, p99) per agent
- Token spend trending (per agent, per feature)
- Error rate trends with spike detection
- Guardrail hit rate and type breakdown
- Human escalation queue length and aging
- Task completion funnel visualization

### Anomaly Detection Rules
- Cost spike >20% daily average → Slack alert
- Error rate increase >10% from baseline → PagerDuty
- Tool success rate drops >5% → Agent circuit breaker
- Latency p95 increase >50% → Auto-scale trigger
- Loop detection (agent calling same tool >5x) → Kill switch

---

## Pivot Story

Originally designed as a pipeline pattern where each agent processed sequentially (Customer Service → Claims → Document → Underwriting → Analytics). The pipeline approach seemed clean architecturally but failed in production: 70% of requests only needed 1-2 agents, yet every request paid the full pipeline latency. A $0.02 FAQ response was routing through all 5 agents at $0.51 total.

Pivoted to a supervisor pattern with intelligent routing. The supervisor classifies intent (<200ms via Haiku) and routes to only the necessary agents. Simple queries hit one agent; complex claims chain 2-3 agents. Average cost per task dropped from $0.51 to $0.08, and mean latency from 15.2s to 2.4s. The pipeline pattern would have been correct for a batch processing use case, but Apex's workload is 80% simple queries that don't need the full agent chain.
