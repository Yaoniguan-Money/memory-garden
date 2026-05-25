"""第二层：运行时用户可见反馈构建（不调用外部语言模型，仅基于会话元数据与可追溯 id）。"""

from __future__ import annotations

from enum import Enum

from memory_garden.core.models import GardenEvent
from memory_garden.runtime.policies import FeedbackMode, RuntimePolicy
from memory_garden.runtime.session import GardenSession, GardenTickResult, RuntimeFeedback


class FeedbackPhase(str, Enum):
    """反馈挂载阶段（与编排钩子语义对齐）。"""

    CLOSING = "closing"
    AFTER_REPLY = "after_reply"


class RuntimeFeedbackBuilder:
    """依据真实 ``GardenSession.metadata``、可选 ``GardenTickResult`` 与事件列表生成结构化反馈。

    不编造「已审判 / 已做梦」等结论：仅当存在对应 id 列表或非空 tick 结果时才输出相关要点。
    """

    def build_closing_feedback(
        self,
        session: GardenSession,
        tick_result: GardenTickResult | None = None,
        recent_events: list[GardenEvent] | None = None,
    ) -> RuntimeFeedback:
        md = dict(session.metadata)
        court_ids = self._court_ids(md, tick_result)
        dream_ids = self._dream_ids(md, tick_result)

        summary = f"花园手账收尾（本会话用户回合数：{session.turn_count}）。"

        bullets: list[str] = []
        if court_ids:
            bullets.append(f"开庭产生的案件 id 数：{len(court_ids)}（来自会话累计元数据或本轮 tick）。")
        else:
            bullets.append("开庭：本会话未累计到开庭案件 id（未触发或未启用自动开庭路径时不作肯定断言）。")

        if dream_ids:
            bullets.append(f"梦境记录 id 数：{len(dream_ids)}。")
        else:
            bullets.append("梦境：本会话未累计到梦境记录 id（未触发或未启用自动梦境路径时不作肯定断言）。")

        # recent_events 为仓储级样本，不与会话强绑定；仅作计数说明，避免误导
        if recent_events:
            n = len(recent_events)
            bullets.append(
                f"仓库近期事件样本：{n} 条（全局序列，未按会话过滤，不作为本会话专属断言）。"
            )

        counts_md = {
            "user_turn_count": session.turn_count,
            "court_case_id_count": len(court_ids),
            "dream_record_id_count": len(dream_ids),
            "recent_events_sample_count": len(recent_events or []),
        }

        return RuntimeFeedback(
            session_id=session.session_id,
            summary=summary.strip(),
            bullets=bullets,
            metadata={
                "phase": "closing",
                "counts": counts_md,
                "court_case_ids": list(court_ids),
                "dream_record_ids": list(dream_ids),
            },
        )

    def build_turn_feedback(
        self,
        session: GardenSession,
        tick_result: GardenTickResult | None = None,
    ) -> RuntimeFeedback | None:
        court_ids = self._court_ids(dict(session.metadata), tick_result)
        dream_rid = None
        if tick_result and tick_result.dream_record_id:
            dream_rid = tick_result.dream_record_id
        dream_n = len(self._dream_ids(dict(session.metadata), tick_result))
        if dream_rid and dream_n == 0:
            dream_n = 1

        parts: list[str] = []
        parts.append(f"回合计数={session.turn_count}")
        if court_ids:
            parts.append(f"本轮开庭案件 id 数={len(court_ids)}")
        if dream_rid or dream_n:
            parts.append(f"本轮梦境记录={'1' if dream_rid else str(dream_n)}")
        summary = "；".join(parts)
        return RuntimeFeedback(
            session_id=session.session_id,
            summary=summary,
            bullets=[],
            metadata={
                "phase": "after_reply",
                "counts": {
                    "user_turn_count": session.turn_count,
                    "tick_opened_court_n": len(court_ids),
                    "tick_dream_present": bool(dream_rid or dream_n),
                },
            },
        )

    @staticmethod
    def should_emit_feedback(policy: RuntimePolicy, phase: FeedbackPhase) -> bool:
        """是否在本阶段产生用户可见反馈（``closing_only`` 下仅收尾阶段为真）。"""
        mode = policy.feedback_mode
        if mode == FeedbackMode.off:
            return False
        # 兼容旧枚举：normal ≈ closing_only；minimal ≈ every_turn
        if mode in (FeedbackMode.closing_only, FeedbackMode.normal):
            return phase == FeedbackPhase.CLOSING
        if mode in (FeedbackMode.every_turn, FeedbackMode.minimal):
            return True
        if mode == FeedbackMode.debug_only:
            return True
        return False

    def _court_ids(
        self,
        meta: dict,
        tick_result: GardenTickResult | None,
    ) -> list[str]:
        acc = list(meta.get("accumulated_court_case_ids") or [])
        if tick_result and tick_result.opened_court_case_ids:
            merged: list[str] = []
            seen: set[str] = set()
            for x in list(acc) + list(tick_result.opened_court_case_ids):
                if x not in seen:
                    seen.add(x)
                    merged.append(x)
            return merged
        last = list(meta.get("last_tick_court_case_ids") or [])
        if acc:
            return acc
        return last

    def _dream_ids(
        self,
        meta: dict,
        tick_result: GardenTickResult | None,
    ) -> list[str]:
        acc = list(meta.get("accumulated_dream_record_ids") or [])
        extra: list[str] = []
        if tick_result:
            if tick_result.dream_record_id:
                extra.append(tick_result.dream_record_id)
        for rid in list(meta.get("last_tick_dream_record_ids") or []):
            if rid:
                extra.append(rid)
        merged: list[str] = []
        seen: set[str] = set()
        for x in acc + extra:
            if x not in seen:
                seen.add(x)
                merged.append(x)
        return merged


def summarize_recent_events_for_feedback(events: list[GardenEvent]) -> dict[str, int]:
    """对事件列表按类型计数（供测试或元数据引用，不做业务断言）。"""
    counts: dict[str, int] = {}
    for e in events:
        k = e.event_type.value
        counts[k] = counts.get(k, 0) + 1
    return counts
