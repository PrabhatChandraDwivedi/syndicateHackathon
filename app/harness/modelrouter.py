import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class ProviderConfig:
    name: str
    model: str
    api_key_env: str
    base_url: Optional[str] = None
    context_limit: int = 32768
    token_param: str = 'max_tokens'
    min_output_tokens: int = 0
    reasoning_effort: Optional[str] = None

PROVIDERS = {
    # Reasoning costs about 0.6s a call here and buys better planning: it works
    # through cases one at a time, recalling rules and checking policy, rather
    # than reporting totals and stopping. Worth it at this speed.
    'groq': ProviderConfig('groq', 'openai/gpt-oss-120b', 'GROQ_API_KEY', 'https://api.groq.com/openai/v1', 131072, token_param='max_completion_tokens', min_output_tokens=0, reasoning_effort='medium'),
    'openai': ProviderConfig('openai', 'gpt-5-nano', 'OPENAI_API_KEY', None, 400000, token_param='max_completion_tokens', min_output_tokens=4000, reasoning_effort='low'),
    'tensormux': ProviderConfig('tensormux', 'glm-4-7-flash', 'TENSORMUX_API_KEY', 'https://api.tensormux.com/v1', 32768, token_param='max_tokens', min_output_tokens=0),
}

# Groq first when its key is present: same class of model, an order of magnitude
# faster, and a 131k window that an agent transcript will not outgrow.
# OpenAI is the dependable fallback. GLM is last -- it is quick on a short prompt
# but an agent transcript passes its 32k window within a couple of steps, and it
# answers with an empty completion rather than an error.
DEFAULT_ORDER = ['groq', 'openai', 'tensormux']

class ModelRouter:
    def __init__(self, order=None, client_factory=None):
        self.order = order or DEFAULT_ORDER
        self.client_factory = client_factory

    def _make_client(self, cfg):
        if self.client_factory:
            return self.client_factory(cfg)
        from openai import OpenAI
        return OpenAI(api_key=os.environ[cfg.api_key_env], base_url=cfg.base_url)

    def available(self) -> list[str]:
        names = []
        for name in self.order:
            cfg = PROVIDERS[name]
            if os.environ.get(cfg.api_key_env):
                names.append(name)
        return names

    def complete(self, prompt, max_tokens=1000) -> dict:
        errors = []
        for i, name in enumerate(self.order, 1):
            cfg = PROVIDERS[name]
            # Skip providers with no key rather than spending an attempt on them.
            # A default factory is injected in tests, so only skip for the real one.
            if self.client_factory is None and not os.environ.get(cfg.api_key_env):
                errors.append(f'{name}: no {cfg.api_key_env} set')
                continue
            client = self._make_client(cfg)
            try:
                budget = max(max_tokens, cfg.min_output_tokens)
                kwargs = {
                    'model': cfg.model,
                    'messages': [{'role': 'user', 'content': prompt}]
                }
                kwargs[cfg.token_param] = budget
                # Latency on the gpt-5 family is mostly reasoning tokens, and
                # "pick the next tool" does not need deep deliberation. Low effort
                # cuts the wait substantially without changing which tool it picks.
                if cfg.reasoning_effort:
                    kwargs['reasoning_effort'] = cfg.reasoning_effort
                resp = client.chat.completions.create(**kwargs)
                text = None
                try:
                    text = resp.choices[0].message.content
                except (AttributeError, IndexError, TypeError):
                    text = None
                if not isinstance(text, str) or text.strip() == '':
                    fr = None
                    try:
                        fr = resp.choices[0].message.finish_reason
                    except Exception:
                        fr = None
                    if isinstance(fr, str):
                        errors.append(f'{name}: empty completion (finish_reason={fr})')
                    else:
                        errors.append(f'{name}: empty completion')
                    continue
                return {
                    'provider': cfg.name,
                    'model': cfg.model,
                    'text': text,
                    'attempts': i
                }
            except Exception as e:
                errors.append(f'{name}: {e}')
        raise RuntimeError('all providers failed: ' + '; '.join(errors))
