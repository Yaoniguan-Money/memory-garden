"""Shared text tokenization and MemoryCard text helpers."""

from __future__ import annotations

import re

from memory_garden.core.models import MemoryCard
from memory_garden.soil.cjk_ngram import contains_cjk, jieba_tokenize


def tokenize_text(text: str, *, min_token_len: int = 2) -> list[str]:
    """Tokenize mixed CJK/ASCII text for product retrieval rules.

    ASCII keeps the original casefolded token behavior. CJK spans emit the
    full span, optional jieba tokens, and overlapping bigrams so Product-layer
    rules share the same searchable units as the FTS5 CJK ngram path.
    """
    if min_token_len < 1:
        raise ValueError("min_token_len must be >= 1")
    if not text or not text.strip():
        return []

    tokens: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        cleaned = token.strip(".,;:!?()[]{}\"'").strip()
        if len(cleaned) < min_token_len:
            return
        key = cleaned.casefold() if all(ord(ch) < 128 for ch in cleaned) else cleaned
        if key in seen:
            return
        seen.add(key)
        tokens.append(key)

    for part in re.findall(r"[\u3400-\u9fff\uf900-\ufaff]+|[a-zA-Z0-9_+/-]+", text):
        if contains_cjk(part):
            add(part)
            for tok in jieba_tokenize(part):
                add(tok)
            if len(part) >= 2:
                for index in range(len(part) - 1):
                    add(part[index : index + 2])
        else:
            for tok in part.replace("/", " ").split():
                add(tok)

    return tokens


def card_text(card: MemoryCard) -> str:
    """Join MemoryCard text fields for retrieval and conflict detection."""
    return "\n".join(
        str(part)
        for part in [
            card.title or "",
            card.essence or "",
            card.fragrance or "",
            card.thorns or "",
            " ".join(card.tags or []),
        ]
        if str(part).strip()
    )
