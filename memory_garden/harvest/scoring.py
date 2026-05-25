"""第三层 Stage 3C：规则版采摘打分（确定性、可解释；无排序、不调外部生成式模型）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from memory_garden.harvest.models import HarvestQuery, HarvestScore, MemoryCandidate
from memory_garden.runtime_config import (
    HarvestPenaltyConfig,
    HarvestScoreWeights,
    RecencyDecayConfig,
    default_garden_runtime_config,
)


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _resolve_score_now(query: HarvestQuery) -> datetime:
    parsed = _parse_timestamp(query.metadata.get("score_now"))
    return parsed or datetime.now(timezone.utc)


def _half_life_days(src: dict[str, Any], recency: RecencyDecayConfig) -> float:
    memory_type = str(src.get("memory_type") or "").strip().lower()
    tags = {str(tag).strip().lower() for tag in src.get("tags", []) if isinstance(tag, str)}
    maturity = str(src.get("maturity") or "").strip().lower()
    if "canonical" in tags or maturity in {"stable", "canonical"}:
        return recency.canonical_half_life_days
    if memory_type in {"project", "task"}:
        return recency.project_half_life_days
    return recency.default_half_life_days


def _compute_recency(
    src: dict[str, Any],
    now: datetime,
    *,
    recency: RecencyDecayConfig,
    weights: HarvestScoreWeights,
) -> tuple[float, list[str]]:
    ts = _parse_timestamp(src.get("updated_at")) or _parse_timestamp(src.get("created_at"))
    if ts is None:
        return weights.recency_neutral, [f"recency:missing_timestamp;neutral={weights.recency_neutral}"]
    age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
    half_life = _half_life_days(src, recency)
    if half_life >= 1000.0:
        recency_val = max(recency.canonical_recency_floor, 0.5 ** (age_days / half_life))
    else:
        recency_val = 0.5 ** (age_days / half_life)
    recency_val = _clamp01(recency_val)
    return recency_val, [
        "recency:computed",
        f"recency:age_days={age_days:.2f}",
        f"recency:half_life_days={half_life:.1f}",
        f"recency:value={recency_val:.4f}",
    ]


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _source_dict(c: MemoryCandidate) -> dict[str, Any]:
    raw = c.metadata.get("source_memory")
    return raw if isinstance(raw, dict) else {}


def _lifecycle_value(src: dict[str, Any]) -> str:
    v = src.get("lifecycle")
    return v if isinstance(v, str) else ""


def _lifecycle_penalty_mult(lifecycle: str, penalties: HarvestPenaltyConfig) -> tuple[float, list[str]]:
    """返回 (0~1] 乘子与说明行。"""
    reasons: list[str] = []
    lc = lifecycle.strip().lower() if lifecycle else ""
    if not lc:
        return 1.0, reasons
    configured = penalties.lifecycle_multipliers.get(lc)
    if configured is not None:
        label = "lifecycle_ok" if configured == 1.0 else "lifecycle_penalty"
        if lc == "fading":
            label = "lifecycle_weight"
        reasons.append(f"{label}:{lc}={configured:g}")
        return configured, reasons
    reasons.append(f"lifecycle_default:{lc or 'unknown'}")
    return penalties.unknown_lifecycle_multiplier, reasons


def _thorns_penalty_mult(thorns: str, penalties: HarvestPenaltyConfig) -> tuple[float, list[str]]:
    if not isinstance(thorns, str):
        return 1.0, []
    size = len(thorns.strip())
    tiers = sorted(penalties.thorns_tiers, key=lambda tier: tier.min_chars, reverse=True)
    for tier in tiers:
        if size >= tier.min_chars:
            return tier.multiplier, [f"thorns_len_penalty:{tier.label}(n={size})"]
    return 1.0, []


def _score_one(
    query: HarvestQuery,
    c: MemoryCandidate,
    *,
    weights: HarvestScoreWeights,
    recency: RecencyDecayConfig,
    penalties: HarvestPenaltyConfig,
) -> HarvestScore:
    """单候选打分；不修改 ``c``。"""
    now = _resolve_score_now(query)
    src = _source_dict(c)
    channels = c.metadata.get("hit_channels")
    if not isinstance(channels, list):
        channels = []
    channels_norm = [str(x) for x in channels if isinstance(x, (str, int, float))]

    matched = c.metadata.get("matched_lenses")
    n_lens = len(matched) if isinstance(matched, list) else 0

    lexical_hit = "lexical_text" in channels_norm
    tag_hit = "tag_metadata" in channels_norm

    comp_lexical = weights.lexical if lexical_hit else 0.0
    comp_tag = weights.tag if tag_hit else 0.0
    comp_lens = weights.lens * float(min(max(n_lens, 0), weights.max_lens_hits))

    importance = src.get("importance")
    try:
        imp = float(importance) if importance is not None else 0.5
    except (TypeError, ValueError):
        imp = 0.5
    imp = _clamp01(imp)
    comp_importance = weights.importance * imp

    confidence = src.get("confidence")
    try:
        conf = float(confidence) if confidence is not None else 0.5
    except (TypeError, ValueError):
        conf = 0.5
    conf = _clamp01(conf)
    comp_confidence = weights.confidence * conf

    if not lexical_hit and not tag_hit:
        raw_additive = weights.base_weak + comp_importance * 0.5 + comp_confidence * 0.4
    else:
        raw_additive = comp_lexical + comp_tag + comp_lens + comp_importance + comp_confidence

    lc_mult, lc_notes = _lifecycle_penalty_mult(_lifecycle_value(src), penalties)
    thorns_raw = src.get("thorns", "")
    th_mult, th_notes = _thorns_penalty_mult(
        thorns_raw if isinstance(thorns_raw, str) else "",
        penalties,
    )

    combined_mult = lc_mult * th_mult
    adjusted = raw_additive * combined_mult
    total = _clamp01(adjusted)
    recency_val, recency_notes = _compute_recency(src, now, recency=recency, weights=weights)

    notes: list[str] = [
        f"total_score={total:.4f}",
        f"memory_id={c.memory_id}",
        *recency_notes,
        f"confidence:source_memory_value={conf:.4f},weighted_contribution={comp_confidence:.4f}(w={weights.confidence})",
        "components:"
        + ",".join(
            [
                f"lexical={comp_lexical:.4f}",
                f"tag_metadata={comp_tag:.4f}",
                f"matched_lenses={comp_lens:.4f}(n={n_lens})",
                f"importance={comp_importance:.4f}",
                f"confidence_weight={comp_confidence:.4f}",
            ]
        ),
        f"channel_hits={'+'.join(channels_norm) if channels_norm else 'none'}",
    ]
    notes.extend(lc_notes)
    notes.extend(th_notes)

    if _lifecycle_value(src) == "greenhouse":
        notes.append("risk:greenhouse_candidate_heavily_downweighted")

    policy_diag = combined_mult - 1.0
    if policy_diag < -0.999:
        policy_diag = -0.999
    if policy_diag > 0.999:
        policy_diag = 0.999

    return HarvestScore(
        candidate_id=c.candidate_id,
        relevance=total,
        recency=recency_val,
        policy_boost=policy_diag,
        notes=notes,
    )


class RuleBasedHarvestScorer:
    """规则版打分器：输出与输入候选同序，每条目一条 ``HarvestScore``。"""

    def __init__(
        self,
        *,
        weights: HarvestScoreWeights | None = None,
        recency: RecencyDecayConfig | None = None,
        penalties: HarvestPenaltyConfig | None = None,
    ) -> None:
        harvest = default_garden_runtime_config().harvest
        self._weights = weights or harvest.scoring
        self._recency = recency or harvest.recency
        self._penalties = penalties or harvest.penalties

    def score(self, query: HarvestQuery, candidates: list[MemoryCandidate]) -> list[HarvestScore]:
        return [
            _score_one(
                query,
                c,
                weights=self._weights,
                recency=self._recency,
                penalties=self._penalties,
            )
            for c in candidates
        ]
