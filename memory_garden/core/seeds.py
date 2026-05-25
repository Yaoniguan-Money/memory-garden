"""规则版种子观察：从文本生成候选 Seed（pending），经仓储与日志持久化。"""

from __future__ import annotations

from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import (
    GardenEventType,
    GardenObjectType,
    Seed,
    SeedSignalType,
    SeedStatus,
)
from memory_garden.core.policies import (
    CONSTRAINT_MARKERS,
    NEGATIVE_SELF_TALK_MARKERS,
    PREFERENCE_MARKERS,
    SENSITIVE_MARKERS,
    text_matches_forget_or_control,
    text_matches_marker_set,
)
from memory_garden.storage.base import GardenRepository


def _confidence_for(signal: SeedSignalType, text: str) -> float:
    """粗粒度置信度：略随文本长度与信号类型调整，限定在 [0.55, 0.92]。"""
    base = {
        SeedSignalType.preference: 0.74,
        SeedSignalType.constraint: 0.70,
        SeedSignalType.sensitive_info: 0.78,
        SeedSignalType.negative_self_talk: 0.62,
    }.get(signal, 0.60)
    bump = min(0.12, len(text.strip()) / 800.0)
    return round(min(0.92, base + bump), 3)


def _tags_for(signal: SeedSignalType, text: str) -> list[str]:
    tags = [signal.value]
    if signal == SeedSignalType.preference and text_matches_marker_set(text, ("以后", "从现在起")):
        tags.append("temporal")
    if signal == SeedSignalType.constraint:
        tags.append("boundary_hint")
    return tags


def _classify_signal(text: str) -> SeedSignalType | None:
    """敏感与安全优先，其次负面自评，再次偏好与约束。

    偏好词若在否定语境中（"我不喜欢"、"别喜欢"）不会被误判为偏好，
    而是继续检查约束标记。
    """
    if text_matches_marker_set(text, SENSITIVE_MARKERS):
        return SeedSignalType.sensitive_info
    if text_matches_marker_set(text, NEGATIVE_SELF_TALK_MARKERS):
        return SeedSignalType.negative_self_talk
    if text_matches_marker_set(text, PREFERENCE_MARKERS):
        # 检查是否为否定语境中的偏好词
        lower = text.casefold()
        negated = False
        for marker in PREFERENCE_MARKERS:
            if marker.casefold() in lower:
                idx = lower.index(marker.casefold())
                prefix = lower[max(0, idx - 4):idx]
                if any(neg in prefix for neg in ("不", "别", "没", "勿", "莫", "休")):
                    negated = True
                    break
        if not negated:
            return SeedSignalType.preference
    if text_matches_marker_set(text, CONSTRAINT_MARKERS):
        return SeedSignalType.constraint
    return None


class SeedExtractor:
    """纯规则种子抽取器：只产出列表，不写库。"""

    def extract(self, text: str) -> list[Seed]:
        stripped = text.strip()
        if not stripped:
            return []
        if text_matches_forget_or_control(stripped):
            return []

        signal = _classify_signal(stripped)
        if signal is None:
            return []

        excerpt = stripped if len(stripped) <= 320 else stripped[:320]
        seed = Seed(
            content=stripped,
            source_excerpt=excerpt,
            context={
                "observer": "rule_based_seed_extractor",
                "input_char_len": len(stripped),
            },
            tags=_tags_for(signal, stripped),
            signal_type=signal,
            confidence=_confidence_for(signal, stripped),
            status=SeedStatus.pending,
        )
        return [seed]


class SeedObserver:
    """轻量观察入口：抽取 Seed，写入仓储并记录 seed_created 领域事件。"""

    def __init__(
        self,
        repository: GardenRepository,
        journal: GardenJournal | None = None,
    ) -> None:
        self._repository = repository
        self._journal = journal if journal is not None else GardenJournal(repository)
        self._extractor = SeedExtractor()

    def observe(self, text: str) -> list[Seed]:
        seeds = self._extractor.extract(text)
        for seed in seeds:
            self._repository.save_seed(seed)
            self._journal.record_event(
                event_type=GardenEventType.seed_created,
                object_type=GardenObjectType.seed,
                object_id=seed.id,
                summary=f"规则观察生成候选种子（{seed.signal_type.value}）",
                metadata={
                    "signal_type": seed.signal_type.value,
                    "tags": list(seed.tags),
                    "confidence": seed.confidence,
                },
            )
        return seeds
