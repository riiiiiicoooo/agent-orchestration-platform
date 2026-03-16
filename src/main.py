"""
Agent Orchestration Platform — FastAPI Application Entry Point

Production-grade multi-agent orchestration for Apex Financial Services.
Coordinates specialized AI agents across claims, underwriting, customer service,
document processing, and analytics workflows.
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as api_router
from src.api.websocket import router as ws_router
from src.middleware.auth import ClerkAuthMiddleware
from src.middleware.rate_limit import RateLimitMiddleware
from src.middleware.cost_tracking import CostTrackingMiddleware
from src.config.settings import settings
from src.memory.session import RedisSessionStore
from src.memory.conversation import ConversationStore
from src.memory.knowledge import KnowledgeStore
from src.orchestrator.supervisor import SupervisorAgent
from src.providers.router import ModelRouter
from src.db import DatabaseManager, RedisManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialize and teardown shared resources."""
    logger.info("Starting Agent Orchestration Platform...")

    # Initialize database with QueuePool connection pooling
    db_manager = DatabaseManager(database_url=settings.DATABASE_URL)
    await db_manager.initialize()
    app.state.db_manager = db_manager

    # Initialize Redis for cache layer (rate limits, cost tracking)
    redis_manager = RedisManager(redis_url=settings.REDIS_URL)
    await redis_manager.initialize()
    app.state.redis_manager = redis_manager

    # Initialize memory stores
    app.state.session_store = RedisSessionStore(
        url=settings.REDIS_URL,
        default_ttl=settings.SESSION_TTL_SECONDS,
    )
    app.state.conversation_store = ConversationStore(
        database_url=settings.DATABASE_URL,
    )
    app.state.knowledge_store = KnowledgeStore(
        database_url=settings.DATABASE_URL,
        embedding_model=settings.EMBEDDING_MODEL,
    )

    # Initialize model router with Redis cost tracking
    app.state.model_router = ModelRouter(
        primary_provider="anthropic",
        fallback_provider="openai",
        routing_provider="anthropic",  # Haiku for fast classification
        redis_manager=redis_manager,
    )

    # Initialize supervisor agent
    app.state.supervisor = SupervisorAgent(
        model_router=app.state.model_router,
        session_store=app.state.session_store,
        conversation_store=app.state.conversation_store,
        knowledge_store=app.state.knowledge_store,
        db_manager=db_manager,
    )

    await app.state.session_store.connect()
    await app.state.supervisor.initialize()

    logger.info(
        "Platform ready — %d agents registered, %d tools available",
        len(app.state.supervisor.agents),
        len(app.state.supervisor.tool_registry),
    )

    yield

    # Teardown
    await app.state.session_store.disconnect()
    await app.state.supervisor.shutdown()
    await redis_manager.close()
    await db_manager.close()
    logger.info("Agent Orchestration Platform stopped.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Agent Orchestration Platform",
        description="Multi-agent orchestration for Apex Financial Services",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middleware (order matters: outermost first)
    app.add_middleware(CostTrackingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(ClerkAuthMiddleware)

    # Routes
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/ws")

    return app


app = create_app()
