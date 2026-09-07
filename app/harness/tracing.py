import os
import uuid
import time
import functools
import logging
from typing import Any, Callable, Dict, List, Optional
from contextlib import contextmanager

_STATE: Dict[str, Any] = {
    "initialized": False,
    "enabled": False,
    "run_id": None,
}

SPANS: List[Dict[str, Any]] = []
EVENTS: List[Dict[str, Any]] = []


def init_tracing(run_id: Optional[str] = None, tags: Optional[List[str]] = None) -> bool:
    if run_id is None:
        run_id = "run_" + uuid.uuid4().hex[:12]

    api_key = os.environ.get("NEATLOGS_API_KEY")
    if not api_key:
        _STATE["initialized"] = True
        _STATE["enabled"] = False
        _STATE["run_id"] = run_id
        return False

    try:
        import neatlogs

        neatlogs.init(api_key=api_key, tags=(tags or []) + ["reconcileos", run_id])
    except Exception as e:
        logging.warning(f"Neatlogs initialization failed: {e}")
        _STATE["initialized"] = True
        _STATE["enabled"] = False
        _STATE["run_id"] = run_id
        return False

    _STATE["initialized"] = True
    _STATE["enabled"] = True
    _STATE["run_id"] = run_id
    return True


def is_enabled() -> bool:
    return _STATE["enabled"]


def current_run_id() -> Optional[str]:
    return _STATE["run_id"]


def trace_id() -> str:
    return "trace_" + uuid.uuid4().hex[:12]


def span(name: str, kind: str = "TOOL"):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            success = True
            result = None

            try:
                # Attempt to execute with Neatlogs tracing
                if _STATE["enabled"]:
                    try:
                        import neatlogs
                        with neatlogs.trace(name=name, kind=kind):
                            result = func(*args, **kwargs)
                            return result
                    except Exception:
                        # Fallback: Neatlogs failed, proceed without it
                        pass
                # Direct execution (either disabled or fallback)
                result = func(*args, **kwargs)
                return result

            except Exception:
                success = False
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)
                SPANS.append(
                    {
                        "name": name,
                        "kind": kind,
                        "duration_ms": duration_ms,
                        "ok": success,
                        "run_id": _STATE["run_id"],
                    }
                )

        return wrapper

    return decorator


def reset_spans() -> None:
    global SPANS
    SPANS.clear()


def flush() -> bool:
    if not is_enabled():
        return False
    try:
        import neatlogs
        neatlogs.flush()
        return True
    except Exception:
        return False


def event(message: str, level: str = "info", **data) -> None:
    # Record locally
    EVENTS.append(
        {
            "message": message,
            "level": level,
            "data": dict(data),
            "run_id": _STATE["run_id"],
        }
    )
    # Forward to Neatlogs when enabled
    if not is_enabled():
        return
    try:
        import neatlogs
        neatlogs.log(message, level=level, **data)
    except Exception:
        # Swallow forwarding failures to keep local observability intact
        pass


def detect(message: str, **data) -> None:
    event(message, level="error", **data)


def reset_events() -> None:
    EVENTS.clear()


@contextmanager
def child_span(name: str, kind: str = "TOOL", **attributes):
    start_time = time.time()
    ok = True
    try:
        if is_enabled():
            import neatlogs
            with neatlogs.trace(name=name, kind=kind, **attributes):
                yield
        else:
            yield
    except Exception:
        ok = False
        raise
    finally:
        duration_ms = int((time.time() - start_time) * 1000)
        SPANS.append(
            {
                "name": name,
                "kind": kind,
                "duration_ms": duration_ms,
                "ok": ok,
                "run_id": _STATE["run_id"],
            }
        )
