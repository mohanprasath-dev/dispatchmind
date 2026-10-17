import asyncio
import functools
import inspect
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Any, Optional, Dict
from core.models import Degraded, Event
from core.store import BaseStore, store as global_store


def log_resilience_event(
    event_type: str,
    source: str,
    reason: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: str = "medium",
    store: Optional[BaseStore] = None,
) -> Event:
    target_store = store or global_store
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    event = Event(
        event_id=event_id,
        event_type=event_type,
        source=source,
        reason=reason or event_type,
        severity=severity,
        details=details or {},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    target_store.set("events", event_id, event)
    return event


def escalate_to_human(
    source: str,
    reason: str,
    details: Optional[Dict[str, Any]] = None,
    store: Optional[BaseStore] = None,
) -> Event:
    return log_resilience_event(
        event_type="needs_human",
        source=source,
        reason=reason,
        details=details or {},
        severity="high",
        store=store,
    )


def resilient(
    fallback: Optional[Callable[..., Any]] = None,
    retries: int = 3,
    base_delay: float = 0.05,
    backoff: str = "exp",
    escalate: bool = False,
    store: Optional[BaseStore] = None,
):
    """
    Self-healing resilience decorator:
    call -> fail -> retry up to `retries` times -> fallback -> log event -> escalate if requested.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func_name = getattr(func, "__name__", "anonymous_func")

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            target_store = store or global_store
            last_err = None
            total_attempts = 1 + retries

            for attempt in range(total_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_err = exc
                    if attempt < total_attempts - 1:
                        multiplier = (2 ** attempt) if backoff == "exp" else 1.0
                        time.sleep(base_delay * multiplier)

            # All attempts failed
            reason = f"{func_name} failed after {retries} retries"
            error_str = str(last_err)

            log_resilience_event(
                event_type="call_failed",
                source=func_name,
                reason=reason,
                details={"error": error_str, "retries": retries},
                severity="medium",
                store=target_store,
            )

            if escalate:
                escalate_to_human(
                    source=func_name,
                    reason=f"Escalated: {reason}",
                    details={"error": error_str, "args_repr": str(args)[:150]},
                    store=target_store,
                )

            fallback_val = None
            if fallback is not None:
                try:
                    fallback_val = fallback(*args, **kwargs)
                except Exception as fb_exc:
                    fallback_val = f"Fallback failed: {fb_exc}"

            return Degraded(
                is_degraded=True,
                fallback_result=fallback_val,
                reason=reason,
                error=error_str,
                source=func_name,
            )

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            target_store = store or global_store
            last_err = None
            total_attempts = 1 + retries

            for attempt in range(total_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_err = exc
                    if attempt < total_attempts - 1:
                        multiplier = (2 ** attempt) if backoff == "exp" else 1.0
                        await asyncio.sleep(base_delay * multiplier)

            # All attempts failed
            reason = f"{func_name} failed after {retries} retries"
            error_str = str(last_err)

            log_resilience_event(
                event_type="call_failed",
                source=func_name,
                reason=reason,
                details={"error": error_str, "retries": retries},
                severity="medium",
                store=target_store,
            )

            if escalate:
                escalate_to_human(
                    source=func_name,
                    reason=f"Escalated: {reason}",
                    details={"error": error_str, "args_repr": str(args)[:150]},
                    store=target_store,
                )

            fallback_val = None
            if fallback is not None:
                try:
                    if inspect.iscoroutinefunction(fallback):
                        fallback_val = await fallback(*args, **kwargs)
                    else:
                        fallback_val = fallback(*args, **kwargs)
                except Exception as fb_exc:
                    fallback_val = f"Fallback failed: {fb_exc}"

            return Degraded(
                is_degraded=True,
                fallback_result=fallback_val,
                reason=reason,
                error=error_str,
                source=func_name,
            )

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
