from __future__ import annotations

import os
from openai import OpenAI

_client: OpenAI | None = None


def has_openai_key() -> bool:
    return bool(os.getenv('OPENAI_API_KEY', '').strip())


def get_openai_model() -> str:
    return os.getenv('OPENAI_MODEL', 'gpt-5.4-mini').strip() or 'gpt-5.4-mini'


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv('OPENAI_API_KEY', '').strip()
        if not api_key:
            raise RuntimeError('OPENAI_API_KEY is not set')
        _client = OpenAI(api_key=api_key)
    return _client
