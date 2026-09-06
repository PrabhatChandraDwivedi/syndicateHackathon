import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest.mock import Mock
from app.harness.modelrouter import ModelRouter, PROVIDERS

def make_fake_client(val):
    client = Mock()
    if val is True:
        client.chat.completions.create.side_effect = ValueError("Simulated error")
    else:
        client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=val))]
        )
    return client

def test_first_provider_succeeds():
    client_factory = Mock()
    client_factory.side_effect = lambda cfg: make_fake_client("from tensormux") if cfg.name == 'tensormux' else make_fake_client(True)
    router = ModelRouter(client_factory=client_factory)
    result = router.complete("hello")
    assert result['provider'] == 'tensormux'
    assert result['attempts'] == 1
    assert result['text'] == "from tensormux"

def test_first_raises_second_succeeds():
    client_factory = Mock()
    client_factory.side_effect = lambda cfg: make_fake_client(True) if cfg.name == 'tensormux' else make_fake_client("from openai")
    router = ModelRouter(client_factory=client_factory)
    result = router.complete("hello")
    assert result['provider'] == 'openai'
    assert result['attempts'] == 2

def test_all_raise():
    client_factory = Mock()
    client_factory.side_effect = lambda cfg: make_fake_client(True)
    router = ModelRouter(client_factory=client_factory)
    with pytest.raises(RuntimeError) as exc:
        router.complete("hello")
    assert 'all providers failed' in str(exc.value)

def test_available(monkeypatch):
    router = ModelRouter(order=['tensormux', 'openai'])
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('TENSORMUX_API_KEY', raising=False)
    assert router.available() == []
    
    monkeypatch.setenv('TENSORMUX_API_KEY', 'key')
    assert router.available() == ['tensormux']
    
    monkeypatch.setenv('OPENAI_API_KEY', 'key')
    assert router.available() == ['tensormux', 'openai']
    
    monkeypatch.delenv('TENSORMUX_API_KEY', raising=False)
    assert router.available() == ['openai']

def test_context_limit():
    assert PROVIDERS['tensormux'].context_limit == 32768
