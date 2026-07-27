"""
Token counting. Uses tiktoken's cl100k_base as a reasonable universal
approximation — exact tokenization varies per local model/tokenizer,
but this is accurate enough for budget/inspector purposes and avoids
needing every provider's tokenizer bundled locally.
"""
from __future__ import annotations

import functools

import tiktoken


@functools.lru_cache(maxsize=1)
def _encoder():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_encoder().encode(text))
