"""Token counting used for chunk sizing.

The default counter is a fast regex approximation (words + punctuation)
that tracks sub-word tokenizers closely for English text. If
``transformers`` and the BGE-M3 tokenizer are available it can be swapped
in via :func:`set_token_counter` for exact counts.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def approx_token_count(text: str) -> int:
    count = 0
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        # long words are usually split into several sub-word pieces
        count += 1 + (len(token) - 1) // 8 if len(token) > 8 else 1
    return count


_counter: Callable[[str], int] = approx_token_count


def count_tokens(text: str) -> int:
    return _counter(text)


def set_token_counter(counter: Callable[[str], int]) -> None:
    global _counter
    _counter = counter


def try_use_hf_tokenizer(model_name: str) -> bool:
    """Use the embedding model's own tokenizer when it is installed locally."""
    try:
        from transformers import AutoTokenizer  # type: ignore

        tokenizer = AutoTokenizer.from_pretrained(model_name)
    except Exception:
        return False
    set_token_counter(lambda text: len(tokenizer.encode(text, add_special_tokens=False)))
    return True
