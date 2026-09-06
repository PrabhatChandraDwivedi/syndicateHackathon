import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import neatlogs

from app.harness import tracing
from app.harness.tracing import (
    _STATE,
    SPANS,
    init_tracing,
    is_enabled,
    current_run_id,
    span,
    trace_id,
    reset_spans,
    flush,
)


@pytest.fixture(autouse=True)
def _reset_tracing_state(monkeypatch):
    # Clean up Neatlogs state to prevent "already running" errors
    try:
        neatlogs.shutdown()
    except Exception:
        pass
    
    tracing._STATE["initialized"] = False
    tracing._STATE["enabled"] = False
    tracing._STATE["run_id"] = None
    tracing.reset_spans()
    yield
    tracing.reset_spans()


class TestInitTracing:
    def test_no_key_returns_false(self, monkeypatch):
        monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
        result = init_tracing()
        assert result is False
        assert is_enabled() is False
        assert current_run_id() is not None

    def test_custom_run_id(self):
        custom_id = "my_custom_run"
        result = init_tracing(run_id=custom_id)
        assert result is False
        assert current_run_id() == custom_id

    def test_enabled_returns_true(self, monkeypatch):
        monkeypatch.setenv("NEATLOGS_API_KEY", "valid_key")
        result = init_tracing()
        assert result is True
        assert is_enabled() is True
        assert current_run_id() is not None

    def test_initialized_flag_true(self, monkeypatch):
        monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
        init_tracing()
        assert _STATE["initialized"] is True


class TestDecorators:
    def test_span_success(self, monkeypatch):
        monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
        reset_spans()
        init_tracing()

        @span("test_operation", kind="WORKFLOW")
        def compute():
            return 42

        result = compute()
        assert result == 42
        assert len(SPANS) == 1
        span_record = SPANS[0]
        assert span_record["name"] == "test_operation"
        assert span_record["kind"] == "WORKFLOW"
        assert span_record["ok"] is True
        assert isinstance(span_record["duration_ms"], int)
        assert span_record["duration_ms"] >= 0
        assert span_record["run_id"] == current_run_id()

    def test_span_failure_propagates(self, monkeypatch):
        monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
        reset_spans()
        init_tracing()

        @span("failing_operation", kind="TOOL")
        def raise_error():
            raise ValueError("Something went wrong")

        with pytest.raises(ValueError, match="Something went wrong"):
            raise_error()

        assert len(SPANS) == 1
        span_record = SPANS[0]
        assert span_record["name"] == "failing_operation"
        assert span_record["kind"] == "TOOL"
        assert span_record["ok"] is False
        assert isinstance(span_record["duration_ms"], int)
        assert span_record["duration_ms"] >= 0
        assert span_record["run_id"] == current_run_id()

    def test_run_id_in_span_when_not_initialized(self, monkeypatch):
        monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
        reset_spans()

        @span("uncaptured_span")
        def dummy():
            pass

        dummy()
        assert SPANS[0]["run_id"] is None

    def test_span_disabled_no_network(self, monkeypatch):
        monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
        reset_spans()
        init_tracing()

        @span("isolated_tool")
        def isolated():
            pass

        isolated()
        assert len(SPANS) == 1
        assert SPANS[0]["name"] == "isolated_tool"


class TestTraceId:
    def test_format(self):
        tid = trace_id()
        assert isinstance(tid, str)
        assert tid.startswith("trace_")
        assert len(tid) == len("trace_") + 12


class TestResetSpans:
    def test_clears_list(self, monkeypatch):
        monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
        reset_spans()
        init_tracing()

        @span("op1")
        def op1():
            pass

        @span("op2")
        def op2():
            pass

        op1()
        op2()

        assert len(SPANS) == 2
        reset_spans()
        assert len(SPANS) == 0


class TestFlush:
    def test_returns_false_when_disabled(self, monkeypatch):
        monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
        assert flush() is False

    def test_returns_true_when_enabled_success(self, monkeypatch):
        monkeypatch.setenv("NEATLOGS_API_KEY", "valid_key")
        init_tracing()
        assert flush() is True


class TestDisabledExecution:
    def test_decorated_function_works_when_disabled(self, monkeypatch):
        monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
        reset_spans()
        init_tracing()

        @span("tool")
        def compute():
            return 123

        result = compute()
        assert result == 123
        assert len(SPANS) == 1
        assert SPANS[0]["name"] == "tool"
        # Verify local SPANS work when Neatlogs is disabled
        assert SPANS[0]["ok"] is True


class TestNeatlogsFallback:
    def test_emission_failure_returns_value(self, monkeypatch):
        # Enable tracing manually to simulate enabled state without a valid key
        monkeypatch.setitem(tracing._STATE, "enabled", True)

        import neatlogs
        # Mock neatlogs.trace to raise an error
        mock_trace_side_effect = lambda **kwargs: (_ for _ in ()).throw(Exception("neatlogs error"))
        monkeypatch.setattr(neatlogs, 'trace', mock_trace_side_effect)

        @span("my_tool")
        def my_func():
            return "success"

        # The function should run successfully using the fallback
        assert my_func() == "success"
        assert len(SPANS) == 1
        assert SPANS[0]["name"] == "my_tool"
        assert SPANS[0]["ok"] is True

        # Reset for other tests
        monkeypatch.setitem(tracing._STATE, "enabled", False)
        reset_spans()
