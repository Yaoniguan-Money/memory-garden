"""Local rules-only candidate collection for Harvest."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re
from typing import Any

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard
from memory_garden.harvest.models import (
    CandidateMatchType,
    HarvestQuery,
    MemoryCandidate,
    MemoryLens,
)
from memory_garden.runtime_config import HarvestCollectorConfig


@dataclass(frozen=True)
class _QueryMatchContext:
    raw_user_text: str
    tokens: list[str]
    stripped_query: str
    folded_query: str
    config: HarvestCollectorConfig


@dataclass
class _FieldMatch:
    reasons: list[str]
    terms: list[str]
    excerpts: list[str]


def _casefold_if_ascii(token: str) -> str:
    """Normalize ASCII case while leaving non-ASCII text intact."""
    if not token:
        return token
    if _is_ascii(token):
        return token.casefold()
    return token


def _tokenize_raw_text(text: str) -> list[str]:
    """Split CJK spans, ASCII words, and numbers into distinct query tokens."""
    if not text or not text.strip():
        return []
    parts = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+|\d+", text.strip())
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        token = part.strip()
        if not token:
            continue
        key = _casefold_if_ascii(token)
        if key not in seen:
            seen.add(key)
            out.append(token)
        if len(token) >= 2 and _has_cjk(token):
            for idx in range(len(token) - 1):
                bigram = token[idx : idx + 2]
                if bigram not in seen:
                    seen.add(bigram)
                    out.append(bigram)
    return out


def _normalize_list_tags(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    norm: list[str] = []
    for value in tags:
        if isinstance(value, str):
            tag = value.strip()
            if tag:
                norm.append(tag.casefold())
    return norm


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _snippet_from_field(value: str, *, max_chars: int) -> str:
    text = (value or "").strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _is_ascii(text: str) -> bool:
    return all(ord(ch) < 128 for ch in text)


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _token_matches_field(token: str, field_text: str, field_fold: str) -> bool:
    if _is_ascii(token):
        folded = _casefold_if_ascii(token)
        return bool(folded and folded in field_fold)
    return bool(token and token in field_text)


def _match_str_field(field_name: str, raw: str, ctx: _QueryMatchContext) -> _FieldMatch:
    if not raw:
        return _FieldMatch([], [], [])

    field_text = raw.strip()
    if not field_text:
        return _FieldMatch([], [], [])

    field_fold = field_text.casefold()
    terms: list[str] = []
    hit = False

    if (
        ctx.folded_query
        and len(ctx.folded_query) >= ctx.config.min_full_query_chars
        and ctx.folded_query in field_fold
    ):
        hit = True
        terms.append(ctx.stripped_query[:64])

    for token in ctx.tokens:
        token_key = _casefold_if_ascii(token)
        if len(token_key) < ctx.config.min_ascii_token_chars and not _has_cjk(token):
            continue
        if _token_matches_field(token, field_text, field_fold):
            hit = True
            terms.append(token)

    if not hit:
        return _FieldMatch([], [], [])

    return _FieldMatch(
        reasons=[f"lexical_text:field:{field_name}"],
        terms=_dedupe_preserve_order(terms),
        excerpts=[
            f"{field_name}:{_snippet_from_field(field_text, max_chars=ctx.config.max_snippet_chars)}"
        ],
    )


def _memory_text_fields(memory: MemoryCard) -> list[tuple[str, str]]:
    fields = [
        ("title", memory.title),
        ("essence", memory.essence),
        ("fragrance", memory.fragrance),
        ("thorns", memory.thorns),
    ]
    fields.extend((f"roots[{idx}]", root) for idx, root in enumerate(memory.roots) if isinstance(root, str))
    fields.extend(
        (f"branches[{idx}]", branch)
        for idx, branch in enumerate(memory.branches)
        if isinstance(branch, str)
    )
    return fields


def _lens_tag_path_hit(lens: MemoryLens, shared_query_memory_tags: set[str]) -> bool:
    if not shared_query_memory_tags:
        return False
    facets = {f.strip().casefold() for f in lens.facet_keys if isinstance(f, str) and f.strip()}
    if facets & shared_query_memory_tags:
        return True
    name = lens.name.strip()
    if not name:
        return False
    name_fold = name.casefold() if _is_ascii(name) else name
    return bool(name_fold in shared_query_memory_tags)


def _lens_text_path_hit(lens: MemoryLens, raw_user_text: str, tokens: list[str]) -> bool:
    text = raw_user_text or ""
    haystack = text.casefold()
    name = lens.name.strip()
    if name:
        if _is_ascii(name):
            if name.casefold() in haystack:
                return True
        elif name in text:
            return True
    for facet in lens.facet_keys:
        if not isinstance(facet, str):
            continue
        facet_text = facet.strip()
        if not facet_text:
            continue
        if _is_ascii(facet_text):
            facet_key = facet_text.casefold()
            if facet_key and facet_key in haystack:
                return True
            for token in tokens:
                if _is_ascii(token) and facet_key == _casefold_if_ascii(token):
                    return True
        else:
            if facet_text in text:
                return True
            for token in tokens:
                if facet_text in token or token in facet_text:
                    return True
    return False


def _resolve_matched_lens_ids(
    lenses: list[MemoryLens],
    *,
    has_tag_hit: bool,
    has_lexical_hit: bool,
    shared_query_memory_tags: set[str],
    raw_user_text: str,
    tokens: list[str],
) -> list[str]:
    matched: list[str] = []
    seen: set[str] = set()
    for lens in lenses:
        ok = False
        if has_tag_hit and _lens_tag_path_hit(lens, shared_query_memory_tags):
            ok = True
        if has_lexical_hit and _lens_text_path_hit(lens, raw_user_text, tokens):
            ok = True
        if ok and lens.lens_id not in seen:
            seen.add(lens.lens_id)
            matched.append(lens.lens_id)
    return matched


class LocalCandidateCollector:
    """Collect MemoryCandidate objects from MemoryCard lists with local rules."""

    def __init__(self, config: HarvestCollectorConfig | None = None) -> None:
        self._config = config or HarvestCollectorConfig()

    def collect(self, query: HarvestQuery, memories: list[MemoryCard]) -> list[MemoryCandidate]:
        allow_greenhouse = bool(query.metadata.get("allow_greenhouse", False))
        query_tags_norm = _normalize_list_tags(query.metadata.get("tags"))
        query_lens_ids = [lens.lens_id for lens in query.lenses]

        results: list[MemoryCandidate] = []
        tokens = _tokenize_raw_text(query.raw_user_text)
        stripped_query = query.raw_user_text.strip()
        ctx = _QueryMatchContext(
            raw_user_text=query.raw_user_text,
            tokens=tokens,
            stripped_query=stripped_query,
            folded_query=stripped_query.casefold() if stripped_query else "",
            config=self._config,
        )

        for memory in memories:
            if memory.lifecycle == MemoryLifecycle.greenhouse and not allow_greenhouse:
                continue

            reasons: list[str] = []
            terms_hit: list[str] = []
            excerpts: list[str] = []
            hit_channels: list[str] = []

            mem_tags_fold = {t.strip().casefold() for t in memory.tags if isinstance(t, str) and t.strip()}
            tag_inter = [tag for tag in query_tags_norm if tag in mem_tags_fold]
            shared_tags: set[str] = set(tag_inter)

            if tag_inter:
                reasons.append("tags_intersection")
                reasons.append("tag_metadata:intersection")
                hit_channels.append("tag_metadata")
                terms_hit.extend(tag_inter)

            for field_name, raw in _memory_text_fields(memory):
                match = _match_str_field(field_name, raw, ctx)
                reasons.extend(match.reasons)
                terms_hit.extend(match.terms)
                excerpts.extend(match.excerpts)

            if not reasons:
                continue

            has_lexical_hit = any(reason.startswith("lexical_text:field:") for reason in reasons)
            has_tag_hit = bool(tag_inter)

            hit_channels_clean = _dedupe_preserve_order(hit_channels)
            if has_lexical_hit and "lexical_text" not in hit_channels_clean:
                hit_channels_clean.append("lexical_text")

            terms_hit = _dedupe_preserve_order(terms_hit)
            excerpt = self._resolve_excerpt(excerpts, tag_inter, memory)

            matched_lens = _resolve_matched_lens_ids(
                query.lenses,
                has_tag_hit=has_tag_hit,
                has_lexical_hit=has_lexical_hit,
                shared_query_memory_tags=shared_tags,
                raw_user_text=query.raw_user_text,
                tokens=tokens,
            )

            meta: dict[str, Any] = {
                "query_lenses": list(query_lens_ids),
                "matched_lenses": list(matched_lens),
                "matched_terms": terms_hit[: self._config.max_matched_terms],
                "match_reasons": _dedupe_preserve_order(reasons),
                "hit_channels": hit_channels_clean,
                "source_memory": memory.model_dump(mode="json"),
            }

            results.append(
                MemoryCandidate(
                    memory_id=memory.id,
                    excerpt=excerpt,
                    match_type=CandidateMatchType.LEXICAL_STUB,
                    lens_id=matched_lens[0] if matched_lens else None,
                    metadata=meta,
                )
            )

        return results

    def _resolve_excerpt(self, excerpts: list[str], tag_inter: list[str], memory: MemoryCard) -> str:
        if excerpts:
            excerpt = excerpts[0]
            if len(excerpt) > self._config.max_snippet_chars:
                return excerpt[: self._config.max_snippet_chars - 3] + "..."
            return excerpt
        if tag_inter:
            tags_text = ",".join(memory.tags)
            return f"tags:{_snippet_from_field(tags_text, max_chars=self._config.max_snippet_chars)}"
        return ""
