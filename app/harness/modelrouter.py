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

PROVIDERS = {
    'openai': ProviderConfig('openai', 'gpt-5-nano', 'OPENAI_API_KEY', None, 400000, token_param='max_completion_tokens'),
    'tensormux': ProviderConfig('tensormux', 'glm-4-7-flash', 'TENSORMUX_API_KEY', 'https://api.tensormux.com/v1', 32768, token_param='max_tokens'),
}

DEFAULT_ORDER = ['tensormux', 'openai']

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
            client = self._make_client(cfg)
            try:
                kwargs = {
                    'model': cfg.model,
                    'messages': [{'role': 'user', 'content': prompt}]
                }
                kwargs[cfg.token_param] = max_tokens
                resp = client.chat.completions.create(**kwargs)
                text = None
                try:
                    text = resp.choices[0].message.content
                except (AttributeError, IndexError, TypeError):
                    text = None
                if not isinstance(text, str) or text.strip() == '':
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
