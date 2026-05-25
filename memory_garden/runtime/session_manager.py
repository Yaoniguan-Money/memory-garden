"""第二层：GardenSession 生命周期（内存态，不接触第一层 Core）。"""

from __future__ import annotations

from datetime import datetime, timezone

from memory_garden.runtime.session import GardenSession, RuntimeFeedback
from memory_garden.runtime.interfaces import SessionLifecycleProtocol
from memory_garden.runtime.state import RuntimeState


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_FEEDBACK_HISTORY_KEY = "feedback_history"


class GardenSessionManager(SessionLifecycleProtocol):
    """管理单实例运行时会话状态：开启、关闭、读取当前会话。

    不包含口令解析（见 ``commands.parse_runtime_command``），不调用 GardenRuntime / Core。
    """

    __slots__ = ("_session",)

    def __init__(self) -> None:
        self._session = GardenSession(state=RuntimeState.CLOSED)

    def current_session(self) -> GardenSession:
        """返回当前与会管理器绑定的 ``GardenSession`` 快照（可变模型，由本类维护更新）。"""
        return self._session

    def open_session(self, metadata: dict | None = None) -> GardenSession:
        """打开会话。

        - 自 ``CLOSED`` / ``CLOSING`` 进入 ``OPEN``：新建 ``GardenSession``（新 ``session_id``），
          表示一轮「花花开→花花关」手账；``metadata`` 仅采用本次传入内容。
        - 已在 ``OPEN``：不新建、不换 id，不重置 ``opened_at`` / ``turn_count``，可合并 ``metadata``。
        """
        incoming = dict(metadata or {})
        s = self._session

        if s.state == RuntimeState.OPEN:
            if incoming:
                # 防止外部 metadata 覆盖运行时内部键
                safe_incoming = {k: v for k, v in incoming.items()
                                 if not k.startswith("last_tick_")}
                merged = {**s.metadata, **safe_incoming}
                self._session = s.model_copy(update={"metadata": merged})
            return self._session

        if s.state in (RuntimeState.CLOSED, RuntimeState.CLOSING):
            now = _utc_now()
            carried: dict = {}
            if _FEEDBACK_HISTORY_KEY in s.metadata:
                carried[_FEEDBACK_HISTORY_KEY] = list(s.metadata.get(_FEEDBACK_HISTORY_KEY, []))
            if "last_close_feedback_id" in s.metadata:
                carried["last_close_feedback_id"] = s.metadata["last_close_feedback_id"]
            carried.update(incoming)
            self._session = GardenSession(
                state=RuntimeState.OPEN,
                opened_at=now,
                closed_at=None,
                turn_count=0,
                last_user_message_at=None,
                metadata=carried,
            )
            return self._session

        return self._session

    def enter_closing(self) -> GardenSession:
        """将 ``OPEN`` 会话标为 ``CLOSING``（收尾过渡），其它状态不变。"""
        s = self._session
        if s.state == RuntimeState.OPEN:
            self._session = s.model_copy(update={"state": RuntimeState.CLOSING})
        return self._session

    def assert_session_id(self, session_id: str) -> GardenSession:
        """校验当前会话 id；不一致时抛出 ``ValueError``。"""
        s = self._session
        if s.session_id != session_id:
            raise ValueError("session_id 与当前会话管理器绑定的会话不一致")
        return s

    def increment_turn_count(self, *, last_message_at: datetime | None = None) -> GardenSession:
        """在完成一轮用户输入处理后记一次回合（更新 ``turn_count`` 与 ``last_user_message_at``）。"""
        s = self._session
        now = last_message_at or _utc_now()
        self._session = s.model_copy(
            update={
                "turn_count": s.turn_count + 1,
                "last_user_message_at": now,
            }
        )
        return self._session

    def record_tick_summary(
        self,
        *,
        court_case_ids: list[str],
        dream_record_ids: list[str],
        skipped_reasons: list[str],
        decision_reasons: list[str],
    ) -> GardenSession:
        """将本轮 tick 的可追溯 id 与理由写入 ``metadata``（不复制 CourtCase / DreamRecord 正文）。"""
        if self._session.state != RuntimeState.OPEN:
            return self._session
        meta = dict(self._session.metadata)
        meta["last_tick_court_case_ids"] = list(court_case_ids)
        meta["last_tick_dream_record_ids"] = list(dream_record_ids)
        meta["last_tick_skipped_reasons"] = list(skipped_reasons)
        meta["last_tick_decision_reasons"] = list(decision_reasons)

        acc_c = list(meta.get("accumulated_court_case_ids", []))
        for cid in court_case_ids:
            if cid not in acc_c:
                acc_c.append(cid)
        meta["accumulated_court_case_ids"] = acc_c

        acc_d = list(meta.get("accumulated_dream_record_ids", []))
        for rid in dream_record_ids:
            if rid and rid not in acc_d:
                acc_d.append(rid)
        meta["accumulated_dream_record_ids"] = acc_d

        self._session = self._session.model_copy(update={"metadata": meta})
        return self._session

    def close_session(self, feedback: RuntimeFeedback | None = None) -> GardenSession:
        """关闭会话：``OPEN`` → ``CLOSING`` → ``CLOSED`` 并写 ``closed_at``；已 ``CLOSED`` 时幂等。

        若提供 ``RuntimeFeedback``，将其 ``model_dump(mode=\"json\")`` 追加到
        ``metadata[\"feedback_history\"]``，并写入 ``last_close_feedback_id``。
        """
        s = self._session

        if s.state == RuntimeState.CLOSED:
            return self._session

        meta = dict(s.metadata)
        if feedback is not None:
            hist = list(meta.get(_FEEDBACK_HISTORY_KEY, []))
            hist.append(feedback.model_dump(mode="json"))
            meta[_FEEDBACK_HISTORY_KEY] = hist
            meta["last_close_feedback_id"] = feedback.feedback_id

        now = _utc_now()

        if s.state == RuntimeState.OPEN:
            self._session = s.model_copy(
                update={
                    "state": RuntimeState.CLOSING,
                    "metadata": meta,
                }
            )
            s = self._session
            # CLOSING 状态已携带 feedback，CLOSED 直接继承，不重复追加

        if s.state == RuntimeState.CLOSING:
            self._session = s.model_copy(
                update={
                    "state": RuntimeState.CLOSED,
                    "closed_at": now,
                    "metadata": s.metadata,
                }
            )

        return self._session
