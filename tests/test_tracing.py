import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import types
import sys
import pytest

import app.harness.tracing as tracing


# Helper: install a minimal Neatlogs stub to observe forwards
def _install_neatlogs_stub():
    mod = types.ModuleType("neatlogs")
    mod.init_args = None
    mod.logs = []
    mod._trace_args = None

    class _TraceCtx:
        def __init__(self, name, kind, attrs):
            self.name = name
            self.kind = kind
            self.attrs = attrs

        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    def trace(name, kind='TOOL', **attrs):
        mod._trace_args = {'name': name, 'kind': kind, 'attrs': attrs}
        return _TraceCtx(name, kind, attrs)

    def init(api_key=None, tags=None):
        mod.init_args = {'api_key': api_key, 'tags': tags}

    def log(msg_template, level='info', **data):
        mod.logs.append((msg_template, level, data))

    mod.trace = trace
    mod.init = init
    mod.log = log

    mod.logs = []
    mod.init_args = None
    mod._trace_args = None

    sys.modules['neatlogs'] = mod
    return mod


@pytest.fixture(autouse=True)
def _reset_state_and_events(monkeypatch):
    # Reset internal tracing state
    tracing._STATE["initialized"] = False
    tracing._STATE["enabled"] = False
    tracing._STATE["run_id"] = None
    tracing.reset_spans()
    tracing.reset_events()
    # Ensure environment is clean for each test unless test sets it explicitly
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    yield
    # Cleanup after test
    monkeypatch.undo()


def test_event_records_and_neatlogs_forwarding(monkeypatch):
    neatlogs = _install_neatlogs_stub()
    monkeypatch.setenv("NEATLOGS_API_KEY", "test-key")
    ok = tracing.init_tracing(run_id="run123", tags=["custom"])
    assert ok is True
    assert tracing.is_enabled() is True
    tracing.event("hello world", level="info", foo="bar")

    # Local event should be recorded
    assert tracing.EVENTS[-1] == {
        "message": "hello world",
        "level": "info",
        "data": {"foo": "bar"},
        "run_id": "run123",
    }

    # Neatlogs should have been forwarded
    assert neatlogs.init_args == {"api_key": "test-key", "tags": ["custom", "reconcileos", "run123"]}
    assert neatlogs._trace_args is None
    assert neatlogs.logs[-1] == ("hello world", "info", {"foo": "bar"})


def test_event_disabled_forwarding_not_called(monkeypatch):
    # Ensure Neatlogs is not used when API key is absent
    _install_neatlogs_stub()  # install stub to observe that it's not used
    tracing.reset_events()
    tracing.reset_spans()

    # Do not set API key
    ok = tracing.init_tracing(run_id="run_noapi", tags=[])
    assert ok is False
    assert tracing.is_enabled() is False

    tracing.event("event_without_neat", level="warning", x=1)
    # When disabled, there should be no attempt to forward
    # No new log should be produced by neatlogs
    mod = sys.modules.get("neatlogs")
    if mod is not None and hasattr(mod, "logs"):
        assert len(mod.logs) == 0


def test_detect_and_reset_events(monkeypatch):
    _install_neatlogs_stub()
    tracing.reset_events()
    monkeypatch.setenv("NEATLOGS_API_KEY", "key")
    tracing.init_tracing(run_id="det_run", tags=[])
    tracing.detect("guardrail", reason="guarded")
    # Ensure event recorded as an error
    last = tracing.EVENTS[-1]
    assert last["message"] == "guardrail"
    assert last["level"] == "error"
    assert last["run_id"] == "det_run"


def test_reset_events_clears_events():
    _install_neatlogs_stub()
    tracing.event("msg1")
    tracing.event("msg2")
    assert len(tracing.EVENTS) == 2
    tracing.reset_events()
    assert tracing.EVENTS == []


def test_child_span_records_ok_and_returns(monkeypatch):
    neatlogs = _install_neatlogs_stub()
    monkeypatch.setenv("NEATLOGS_API_KEY", "key")
    tracing.init_tracing(run_id="child_ok_run", tags=[])

    with tracing.child_span("child1", kind="TOOL", extra="val"):
        pass

    assert len(tracing.SPANS) == 1
    span = tracing.SPANS[0]
    assert span["name"] == "child1"
    assert span["kind"] == "TOOL"
    assert span["ok"] is True
    assert span["run_id"] == "child_ok_run"


def test_child_span_records_ok_false_and_raises(monkeypatch):
    _install_neatlogs_stub()
    monkeypatch.setenv("NEATLOGS_API_KEY", "key2")
    tracing.init_tracing(run_id="child_fail_run", tags=[])

    import pytest

    with pytest.raises(ValueError):
        with tracing.child_span("child_error", kind="TOOL"):
            raise ValueError("boom")

    assert len(tracing.SPANS) == 1
    span = tracing.SPANS[0]
    assert span["name"] == "child_error"
    assert span["ok"] is False
    assert span["run_id"] == "child_fail_run"


def test_child_span_disabled(monkeypatch):
    # Ensure Neatlogs is disabled
    _install_neatlogs_stub()
    tracing.reset_events()
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    tracing.init_tracing(run_id="no_trace_run", tags=[])
    with tracing.child_span("child_no_trace", extra="x"):
        pass
    assert len(tracing.SPANS) == 1
    span = tracing.SPANS[0]
    assert span["name"] == "child_no_trace"
    assert span["ok"] is True
    assert tracing.is_enabled() is False
