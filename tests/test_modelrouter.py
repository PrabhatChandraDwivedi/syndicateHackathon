import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.harness.modelrouter import PROVIDERS, ModelRouter

def test_token_param_values():
    assert PROVIDERS['openai'].token_param == 'max_completion_tokens'
    assert PROVIDERS['tensormux'].token_param == 'max_tokens'

def test_complete_uses_correct_param_names_and_fallback():
    os.environ['OPENAI_API_KEY'] = 'dummy'
    os.environ['TENSORMUX_API_KEY'] = 'dummy'

    records = []

    class FakeClient:
        def __init__(self, cfg, recs):
            self.cfg = cfg
            self._recs = recs
            from types import SimpleNamespace
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            # Record the kwargs used for this provider call
            self._recs.append((self.cfg.name, dict(kwargs)))
            # Simulate failure for tensormux to exercise the fallback path
            if self.cfg.name == 'tensormux':
                raise RuntimeError("tensormux failure")
            # Simulate a successful OpenAI response
            class Message: pass
            msg = Message(); msg.content = f"{self.cfg.name}-ok"
            class C: pass
            c = C(); c.message = msg
            class R: pass
            r = R(); r.choices = [c]
            return r

    class FakeFactory:
        def __init__(self, recs):
            self.recs = recs
        def __call__(self, cfg):
            return FakeClient(cfg, self.recs)

    factory = FakeFactory(records)
    router = ModelRouter(order=None, client_factory=factory)

    result = router.complete("hello world", max_tokens=1234)

    # OpenAI should be used after tensormux fails
    assert result['provider'] == 'openai'
    assert result['model'] == PROVIDERS['openai'].model
    assert result['text'] == 'openai-ok'
    assert result['attempts'] == 2  # tensormux (failed) -> openai (succeeded)

    # Check the kwargs per provider to ensure correct token_param usage
    assert len(records) == 2

    tensormux_call = records[0]
    openai_call = records[1]

    assert tensormux_call[0] == 'tensormux'
    tensormux_kwargs = tensormux_call[1]
    assert 'max_tokens' in tensormux_kwargs
    assert 'max_completion_tokens' not in tensormux_kwargs
    assert tensormux_kwargs['max_tokens'] == 1234

    assert openai_call[0] == 'openai'
    openai_kwargs = openai_call[1]
    assert 'max_completion_tokens' in openai_kwargs
    assert 'max_tokens' not in openai_kwargs
    assert openai_kwargs['max_completion_tokens'] == 1234
