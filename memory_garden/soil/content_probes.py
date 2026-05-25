"""Hard forget 内容探针：在删除前采集，证明时不保存敏感明文。"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from typing import Any

from memory_garden.core.models import MemoryCard
from memory_garden.soil.index import DB_FILENAME, _open_db
from memory_garden.soil.models import ContentHashProbe, ContentProbeSet

_MAX_TOKEN_PROBES = 8
_MIN_TOKEN_LEN = 4
_ESSENCE_HASH_CHARS = 64

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "have", "user",
        "prefer", "memory", "card", "test", "about", "into", "your", "their",
        "用户", "偏好", "记忆", "喜欢", "需要", "应该", "可以", "我们", "他们",
        "一个", "这种", "那些", "已经", "进行", "通过", "以及", "或者",
        "remember", "explicit_remember",
    }
)

_SYSTEM_TAG_PREFIXES = ("scope:", "layer:", "source:", "visibility:")


def _normalize_fragment(text: str) -> str:
    return " ".join(text.strip().split())


def _tokenize(text: str) -> list[str]:
    raw = text.replace("/", " ").replace("\n", " ").replace("，", " ").replace("。", " ")
    tokens: list[str] = []
    for part in raw.split():
        token = part.strip(".,;:!?()[]{}\"'").casefold()
        if len(token) >= _MIN_TOKEN_LEN and token not in _STOPWORDS and token not in tokens:
            if any(token.startswith(prefix) for prefix in _SYSTEM_TAG_PREFIXES):
                continue
            tokens.append(token)
    return tokens


def redact_token(token: str) -> str:
    """将 token 转为可读 redacted 形式，不含完整明文。"""
    if len(token) <= 4:
        return "***"
    if len(token) <= 6:
        return f"{token[:2]}***"
    return f"{token[:3]}***{token[-2:]}"


def _salted_hash(salt: bytes, fragment: str) -> str:
    normalized = _normalize_fragment(fragment)
    return hmac.new(salt, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_content_probes_from_card(card: MemoryCard, *, salt: bytes | None = None) -> ContentProbeSet:
    """从 MemoryCard 构建内容探针（含运行时 match token，持久化时用 safe_dump）。"""
    salt = salt or secrets.token_bytes(32)
    salt_id = uuid.uuid4().hex

    blob_parts = [card.title, card.essence, *card.tags]
    ranked: list[tuple[int, str]] = []
    for part in blob_parts:
        for token in _tokenize(part):
            ranked.append((len(token), token))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    seen: set[str] = set()
    match_tokens: list[str] = []
    memory_needle = card.id.casefold()
    for _score, token in ranked:
        if token in seen:
            continue
        if token in memory_needle:
            continue
        seen.add(token)
        match_tokens.append(token)
        if len(match_tokens) >= _MAX_TOKEN_PROBES:
            break

    hash_probes: list[ContentHashProbe] = []
    title_norm = _normalize_fragment(card.title)
    if title_norm:
        hash_probes.append(
            ContentHashProbe(
                label="title",
                hash_hex=_salted_hash(salt, title_norm),
                fragment_length=len(title_norm),
            )
        )
    essence_norm = _normalize_fragment(card.essence)
    if essence_norm:
        fragment = essence_norm[:_ESSENCE_HASH_CHARS]
        hash_probes.append(
            ContentHashProbe(
                label="essence_prefix",
                hash_hex=_salted_hash(salt, fragment),
                fragment_length=len(fragment),
            )
        )

    safe_meta = {
        "salt_id": salt_id,
        "hash_probes": [item.model_dump(mode="json") for item in hash_probes],
        "token_probe_count": len(match_tokens),
    }
    fingerprint = _fingerprint(safe_meta)

    return ContentProbeSet(
        probe_fingerprint=fingerprint,
        token_probe_count=len(match_tokens),
        hash_probe_count=len(hash_probes),
        salt_id=salt_id,
        hash_probes=hash_probes,
        match_tokens=match_tokens,
        redacted_tokens=[redact_token(token) for token in match_tokens],
    )


def build_content_probes_from_db(garden_home: str, memory_id: str) -> ContentProbeSet | None:
    """从 garden.db 读取 MemoryCard 并构建探针；不存在则返回 None。"""
    from pathlib import Path

    db = Path(garden_home).resolve() / DB_FILENAME
    if not db.is_file():
        return None
    conn = _open_db(garden_home)
    try:
        row = conn.execute("SELECT payload FROM memory_cards WHERE id = ?", (memory_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload"])
        card = MemoryCard.model_validate(payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return build_content_probes_from_card(card)


def probe_safe_dump(probes: ContentProbeSet) -> dict[str, Any]:
    """持久化用：不含 match token 明文。"""
    return probes.model_dump(mode="json", exclude={"match_tokens"})


def proof_json_contains_probe_plaintext(
    proof_payload: str,
    probes: ContentProbeSet,
    *,
    memory_id: str = "",
    min_token_len: int = _MIN_TOKEN_LEN,
) -> list[str]:
    """检查 proof JSON 是否泄露探针明文；返回命中的 redacted 标签列表。"""
    lowered = proof_payload.casefold()
    if memory_id:
        lowered = lowered.replace(memory_id.casefold(), "")
    hits: list[str] = []
    for token, redacted in zip(probes.match_tokens, probes.redacted_tokens, strict=False):
        if len(token) < min_token_len:
            continue
        if token and token.casefold() in lowered:
            hits.append(redacted)
    return hits
