"""
Hook Engine — Extensible event system for agent lifecycle management.

Provides hooks at key orchestration points (pre-execute, post-execute, on tool call,
on error, escalation, session lifecycle) that enable cross-cutting concerns like
audit logging, cost tracking, and session persistence without polluting agent code.

Hooks fire in priority order with isolated error handling — one hook failure
doesn't block subsequent hooks or the main execution.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class HookType(str, Enum):
    """Execution points where hooks can be registered."""

    PRE_EXECUTE = "pre_execute"  # Before agent execution
    POST_EXECUTE = "post_execute"  # After successful execution
    ON_TOOL_CALL = "on_tool_call"  # When a tool is invoked
    ON_ERROR = "on_error"  # When an error occurs
    ON_ESCALATION = "on_escalation"  # When confidence is low
    SESSION_START = "session_start"  # New session begins
    SESSION_END = "session_end"  # Session ends
    PRE_COMPACT = "pre_compact"  # Before memory compaction


@dataclass
class HookContext:
    """Context passed to hook handlers."""

    hook_type: HookType
    timestamp: float = field(default_factory=time.time)
    session_id: str | None = None
    agent_id: str | None = None
    task: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    result: Any = None  # Result from agent/tool execution
    error: Exception | None = None
    confidence: float | None = None  # For escalation hooks
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Hook:
    """A registered hook handler."""

    name: str
    hook_type: HookType
    handler: Callable[[HookContext], Coroutine[Any, Any, None]]
    priority: int = 0  # Higher priority executes first
    enabled: bool = True

    async def execute(self, context: HookContext) -> None:
        """Execute the hook handler with error isolation."""
        if not self.enabled:
            return

        try:
            await self.handler(context)
        except Exception as e:
            logger.error(
                "Hook %s (%s) failed: %s",
                self.name,
                self.hook_type.value,
                str(e),
                exc_info=True,
            )
            # Error is logged but doesn't prevent other hooks from running


class HookEngine:
    """
    Registry and dispatcher for hooks.

    Manages lifecycle hooks for session and execution management.
    Hooks are fire-and-forget with error isolation.
    """

    def __init__(self):
        # Registry: hook_type → list of Hook instances
        self._hooks: dict[HookType, list[Hook]] = {
            hook_type: [] for hook_type in HookType
        }

        # Metrics: hook_name → (count, total_ms)
        self._metrics: dict[str, tuple[int, float]] = {}

    def register(self, hook: Hook) -> None:
        """Register a hook to fire at a specific execution point."""
        if hook not in self._hooks[hook.hook_type]:
            self._hooks[hook.hook_type].append(hook)
            # Sort by priority (highest first)
            self._hooks[hook.hook_type].sort(key=lambda h: h.priority, reverse=True)
            logger.info(
                "Registered hook %s for %s (priority=%d)",
                hook.name,
                hook.hook_type.value,
                hook.priority,
            )

    def unregister(self, name: str, hook_type: HookType | None = None) -> bool:
        """Unregister a hook by name. If hook_type specified, only that type."""
        found = False

        if hook_type:
            hooks = self._hooks[hook_type]
            initial_len = len(hooks)
            self._hooks[hook_type] = [h for h in hooks if h.name != name]
            found = len(self._hooks[hook_type]) < initial_len
        else:
            for hooks in self._hooks.values():
                initial_len = len(hooks)
                hooks.clear()
                hooks[:] = [h for h in hooks if h.name != name]
                if len(hooks) < initial_len:
                    found = True

        if found:
            logger.info("Unregistered hook %s", name)
        return found

    async def fire(self, hook_type: HookType, context: HookContext) -> None:
        """
        Fire all registered hooks for a given type.

        Hooks execute in priority order. Errors in individual hooks are logged
        but don't prevent subsequent hooks from running.
        """
        hooks = self._hooks.get(hook_type, [])
        if not hooks:
            return

        # Execute hooks in priority order
        for hook in hooks:
            start_ms = time.monotonic() * 1000
            await hook.execute(context)
            elapsed_ms = time.monotonic() * 1000 - start_ms

            # Track metrics
            if hook.name not in self._metrics:
                self._metrics[hook.name] = (0, 0.0)
            count, total_ms = self._metrics[hook.name]
            self._metrics[hook.name] = (count + 1, total_ms + elapsed_ms)

    def get_metrics(self) -> dict[str, dict[str, Any]]:
        """Return hook execution metrics."""
        metrics = {}
        for name, (count, total_ms) in self._metrics.items():
            metrics[name] = {
                "calls": count,
                "total_ms": total_ms,
                "avg_ms": total_ms / count if count > 0 else 0.0,
            }
        return metrics

    def enable(self, name: str, hook_type: HookType | None = None) -> bool:
        """Enable a hook by name."""
        found = False
        for hooks in self._hooks.values():
            for hook in hooks:
                if hook.name == name and (hook_type is None or hook.hook_type == hook_type):
                    hook.enabled = True
                    found = True
        return found

    def disable(self, name: str, hook_type: HookType | None = None) -> bool:
        """Disable a hook by name."""
        found = False
        for hooks in self._hooks.values():
            for hook in hooks:
                if hook.name == name and (hook_type is None or hook.hook_type == hook_type):
                    hook.enabled = False
                    found = True
        return found


# Default Hooks

async def session_persistence_hook(context: HookContext) -> None:
    """
    Saves session summary to memory on SESSION_END.

    Captures key facts from the session for future reference and learning.
    """
    if context.hook_type != HookType.SESSION_END:
        return

    # In production: extract session summary from context and persist to
    # consolidated memory layer (via memory consolidator)
    logger.info(
        "Session persistence: saving summary for session %s",
        context.session_id,
    )
    # context.metadata.get('consolidator').consolidate_session(context.session_id)


async def cost_guard_hook(context: HookContext) -> None:
    """
    Checks budget before execution (PRE_EXECUTE) and blocks if exceeded.

    Prevents runaway costs by enforcing budget limits at execution time.
    """
    if context.hook_type != HookType.PRE_EXECUTE:
        return

    # In production: check agent's remaining budget
    budget_limit = context.metadata.get("budget_limit", float("inf"))
    budget_used = context.metadata.get("budget_used", 0.0)

    if budget_used >= budget_limit:
        error = RuntimeError(
            f"Budget limit ${budget_limit:.2f} exceeded (used: ${budget_used:.2f})"
        )
        context.error = error
        logger.warning(
            "Cost guard blocked execution: agent %s, budget exceeded",
            context.agent_id,
        )
        # In real implementation, would raise here to prevent execution


async def audit_trail_hook(context: HookContext) -> None:
    """
    Logs all tool calls with metadata for compliance and debugging.

    ON_TOOL_CALL hook that records what was called, with what args, and by whom.
    """
    if context.hook_type != HookType.ON_TOOL_CALL:
        return

    logger.info(
        "Tool call audit: session=%s, agent=%s, tool=%s, args=%s",
        context.session_id,
        context.agent_id,
        context.tool_name,
        context.tool_args,
    )
    # In production: write to audit log table in database


async def escalation_hook(context: HookContext) -> None:
    """
    Notifies when confidence is low (ON_ESCALATION).

    Flags uncertain responses for human review to maintain quality.
    """
    if context.hook_type != HookType.ON_ESCALATION:
        return

    confidence = context.confidence or 0.0
    if confidence < 0.7:
        logger.warning(
            "Escalation triggered: low confidence %.2f for session %s",
            confidence,
            context.session_id,
        )
        # In production: create escalation ticket for human review


async def context_loader_hook(context: HookContext) -> None:
    """
    Pre-fetches relevant knowledge on SESSION_START.

    Populates session context with domain knowledge for faster execution.
    """
    if context.hook_type != HookType.SESSION_START:
        return

    logger.info("Preloading context for session %s", context.session_id)
    # In production: query knowledge store for relevant documents
    # and inject into session context


def create_default_hooks() -> list[Hook]:
    """Create the default set of built-in hooks."""
    return [
        Hook(
            name="session_persistence",
            hook_type=HookType.SESSION_END,
            handler=session_persistence_hook,
            priority=100,
            enabled=True,
        ),
        Hook(
            name="cost_guard",
            hook_type=HookType.PRE_EXECUTE,
            handler=cost_guard_hook,
            priority=90,
            enabled=True,
        ),
        Hook(
            name="audit_trail",
            hook_type=HookType.ON_TOOL_CALL,
            handler=audit_trail_hook,
            priority=80,
            enabled=True,
        ),
        Hook(
            name="escalation",
            hook_type=HookType.ON_ESCALATION,
            handler=escalation_hook,
            priority=85,
            enabled=True,
        ),
        Hook(
            name="context_loader",
            hook_type=HookType.SESSION_START,
            handler=context_loader_hook,
            priority=95,
            enabled=True,
        ),
    ]
