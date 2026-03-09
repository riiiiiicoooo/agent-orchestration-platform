"""
Application Settings — Environment-based configuration with validation.
"""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    """Application configuration loaded from environment variables."""

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/agent_orchestration",
    )

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Session
    SESSION_TTL_SECONDS: int = 1800  # 30 minutes

    # LLM Providers
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Embeddings
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Auth (Clerk)
    CLERK_SECRET_KEY: str = os.getenv("CLERK_SECRET_KEY", "")
    CLERK_PUBLISHABLE_KEY: str = os.getenv("CLERK_PUBLISHABLE_KEY", "")

    # Observability
    LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY", "")
    LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "agent-orchestration")

    # CORS
    ALLOWED_ORIGINS: list[str] = field(default_factory=lambda: [
        "http://localhost:3000",
        "https://agent-orchestration.vercel.app",
    ])

    # Budget defaults
    DEFAULT_DAILY_BUDGET: float = 500.0
    DEFAULT_PER_REQUEST_LIMIT: float = 5.0
    BUDGET_ALERT_THRESHOLD: float = 0.8


settings = Settings()
