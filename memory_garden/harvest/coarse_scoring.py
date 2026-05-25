"""粗召回词法评分（product retrieve 与 candidate source 共享）。"""

from __future__ import annotations

from memory_garden.core.models import MemoryCard
from memory_garden.core.text_utils import card_text, tokenize_text
from memory_garden.runtime_config import CoarseScoreWeights, default_garden_runtime_config


def compute_coarse_lexical_score(
    query: str,
    card: MemoryCard,
    *,
    weights: CoarseScoreWeights | None = None,
) -> float:
    """词法重叠 + 标签 + 子串匹配；权重来自 ``CoarseScoreWeights``。"""
    w = weights or default_garden_runtime_config().harvest.coarse
    query_tokens = set(tokenize_text(query))
    text = card_text(card)
    card_tokens = set(tokenize_text(text))
    score = float(len(query_tokens & card_tokens)) * w.token_overlap_unit
    if any(tag.casefold() in query.casefold() for tag in card.tags):
        score += w.tag_match_bonus
    if query.strip().casefold() in text.casefold():
        score += w.substring_match_bonus
    return score
