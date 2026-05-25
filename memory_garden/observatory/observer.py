"""第四层 Stage 4E：GardenObserver — 编排既有观测 adapter，不新增语义、不带状态写库。"""

from __future__ import annotations

from typing import Any

from memory_garden.core.models import GardenEvent
from memory_garden.harvest.models import HarvestTrace
from memory_garden.observatory.harvest import HarvestObservationAdapter
from memory_garden.observatory.journal import JournalObservationAdapter
from memory_garden.observatory.models import ObservationTrace, ObservationView, RedactionLevel
from memory_garden.observatory.retrieval_quality import (
    NoOpObservationSink,
    ObservationSink,
    extract_retrieval_diagnostics,
    extract_retrieval_latency_ms,
)
from memory_garden.observatory.runtime import RuntimeObservationAdapter
from memory_garden.runtime.hooks import RuntimeAfterReplyResult, RuntimeBeforeReplyResult
from memory_garden.runtime.session import (
    GardenSession,
    GardenTickResult,
    RuntimeFeedback,
    TurnContext,
)


class GardenObserver:
    """统一观察门面：对各子域仅做 ``trace_from_*`` → ``view_from_trace`` 编排。"""

    __slots__ = ("_harvest", "_journal", "_runtime", "_retrieval_sink")

    def __init__(
        self,
        *,
        harvest_adapter: HarvestObservationAdapter | None = None,
        journal_adapter: JournalObservationAdapter | None = None,
        runtime_adapter: RuntimeObservationAdapter | None = None,
        retrieval_sink: ObservationSink | None = None,
    ) -> None:
        self._harvest = harvest_adapter if harvest_adapter is not None else HarvestObservationAdapter()
        self._journal = journal_adapter if journal_adapter is not None else JournalObservationAdapter()
        self._runtime = runtime_adapter if runtime_adapter is not None else RuntimeObservationAdapter()
        self._retrieval_sink = retrieval_sink if retrieval_sink is not None else NoOpObservationSink()

    def observe_harvest(
        self,
        harvest_trace: HarvestTrace,
        *,
        redaction_level: RedactionLevel = RedactionLevel.PUBLIC,
    ) -> ObservationView:
        tr = self._harvest.trace_from_harvest(harvest_trace)
        view = self._harvest.view_from_trace(tr, redaction_level=redaction_level)
        diag = extract_retrieval_diagnostics(harvest_trace.metadata)
        if diag:
            latency_ms = extract_retrieval_latency_ms(harvest_trace.metadata)
            self._retrieval_sink.on_retrieval_quality(diag, latency_ms=latency_ms)
        return view

    def trace_harvest(self, harvest_trace: HarvestTrace) -> ObservationTrace:
        return self._harvest.trace_from_harvest(harvest_trace)

    def observe_journal(
        self,
        events: list[GardenEvent],
        *,
        redaction_level: RedactionLevel = RedactionLevel.PUBLIC,
    ) -> ObservationView:
        tr = self._journal.trace_from_events(events)
        return self._journal.view_from_trace(tr, redaction_level=redaction_level)

    def trace_journal(
        self,
        events: list[GardenEvent],
        *,
        trace_name: str = "garden_journal",
    ) -> ObservationTrace:
        return self._journal.trace_from_events(events, trace_name=trace_name)

    def observe_runtime_turn(
        self,
        *,
        redaction_level: RedactionLevel = RedactionLevel.PUBLIC,
        session: GardenSession | None = None,
        turn_context: TurnContext | None = None,
        before_result: RuntimeBeforeReplyResult | None = None,
        after_result: RuntimeAfterReplyResult | None = None,
        tick_result: GardenTickResult | None = None,
        feedback: RuntimeFeedback | None = None,
        command_result: Any | None = None,
        trace_name: str = "runtime_turn",
    ) -> ObservationView:
        tr = self.trace_runtime_turn(
            session=session,
            turn_context=turn_context,
            before_result=before_result,
            after_result=after_result,
            tick_result=tick_result,
            feedback=feedback,
            command_result=command_result,
            trace_name=trace_name,
        )
        return self._runtime.view_from_trace(tr, redaction_level=redaction_level)

    def trace_runtime_turn(
        self,
        *,
        session: GardenSession | None = None,
        turn_context: TurnContext | None = None,
        before_result: RuntimeBeforeReplyResult | None = None,
        after_result: RuntimeAfterReplyResult | None = None,
        tick_result: GardenTickResult | None = None,
        feedback: RuntimeFeedback | None = None,
        command_result: Any | None = None,
        trace_name: str = "runtime_turn",
    ) -> ObservationTrace:
        return self._runtime.trace_from_turn(
            session=session,
            turn_context=turn_context,
            before_result=before_result,
            after_result=after_result,
            tick_result=tick_result,
            feedback=feedback,
            command_result=command_result,
            trace_name=trace_name,
        )
