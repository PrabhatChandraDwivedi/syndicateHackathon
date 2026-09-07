import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.harness import modelrouter
from app.harness.modelrouter import PROVIDERS, ModelRouter

def test_min_output_tokens_defaults_and_values():
    assert PROVIDERS['openai'].min_output_tokens == 4000
    assert PROVIDERS['tensormux'].min_output_tokens == 0

class FakeMessage:
    def __init__(self, content, finish_reason=None):
        self.content = content
        self.finish_reason = finish_reason

class FakeChoice:
    def __init__(self, message):
        self.message = message

class FakeResp:
    def __init__(self, content, finish_reason=None):
        self.choices = [FakeChoice(FakeMessage(content, finish_reason))]

class RecordingClientFactory:
    def __init__(self):
        self.calls = []  # list of dicts with 'provider' and 'kwargs'

    def __call__(self, cfg):
        return FakeClient(cfg, self)

class FakeClient:
    def __init__(self, cfg, factory):
        self.cfg = cfg
        self.factory = factory
        self.chat = type('Chat', (), {'completions': type('Completions', (), {'create': self.create})})()

    def create(self, **kwargs):
        # Record the call
        self.factory.calls.append({'provider': self.cfg.name, 'kwargs': dict(kwargs), 'model': self.cfg.model})
        # Simulate responses per provider
        if self.cfg.name == 'tensormux':
            # Empty completion to simulate fallback
            return FakeResp('', finish_reason='length')
        else:
            # Non-empty completion
            return FakeResp('Stable Text')

def test_complete_floor_and_fallback():
    factory = RecordingClientFactory()
    router = ModelRouter(order=['tensormux', 'openai'], client_factory=factory)
    result = router.complete("Hello", max_tokens=100)

    assert result['provider'] == 'openai'
    assert result['model'] == PROVIDERS['openai'].model
    assert result['text'] == 'Stable Text'
    assert result['attempts'] == 2

    calls = factory.calls
    assert len(calls) == 2
    # First provider tensormux receives budget max(100, min_output_tokens=0) = 100
    first = calls[0]
    assert first['provider'] == 'tensormux'
    assert 'max_tokens' in first['kwargs']
    assert first['kwargs']['max_tokens'] == 100
    # Second provider openai receives budget max(100, min_output_tokens=4000) = 4000
    second = calls[1]
    assert second['provider'] == 'openai'
    assert 'max_completion_tokens' in second['kwargs']
    assert second['kwargs']['max_completion_tokens'] == 4000

def test_complete_budget_above_floor_results_in_openai_budget():
    factory = RecordingClientFactory()
    router = ModelRouter(order=['tensormux', 'openai'], client_factory=factory)
    result = router.complete("Hello", max_tokens=9000)

    assert result['provider'] == 'openai'
    assert result['model'] == PROVIDERS['openai'].model
    assert result['text'] == 'Stable Text'
    assert result['attempts'] == 2

    calls = factory.calls
    # tensormux called with budget 9000 due to floor
    assert len(calls) == 2
    first = calls[0]
    second = calls[1]
    assert first['provider'] == 'tensormux'
    assert 'max_tokens' in first['kwargs']
    assert first['kwargs']['max_tokens'] == 9000
    assert second['provider'] == 'openai'
    assert 'max_completion_tokens' in second['kwargs']
    assert second['kwargs']['max_completion_tokens'] == 9000
