"""检索质量 diagnostics 观测接口（默认 no-op，无状态）。"""



from __future__ import annotations



from dataclasses import dataclass

from typing import Any, Protocol



from memory_garden.harvest.retrieval_diagnostics import RETRIEVAL_DIAGNOSTICS_KEY, RETRIEVAL_LATENCY_MS_KEY





class ObservationSink(Protocol):

    def on_retrieval_quality(self, diagnostics: dict[str, Any], *, latency_ms: float = 0.0) -> None: ...





class NoOpObservationSink:

    """默认无操作 sink，不改变运行时行为。"""



    def on_retrieval_quality(self, diagnostics: dict[str, Any], *, latency_ms: float = 0.0) -> None:

        return None





@dataclass(frozen=True)

class DiagnosticRow:

    """单条检索 diagnostics 与对应延迟（避免并行列表长度不一致）。"""



    diagnostics: dict[str, Any]

    latency_ms: float = 0.0



    @classmethod

    def from_metadata(cls, metadata: dict[str, Any] | None) -> DiagnosticRow | None:

        if not metadata:

            return None

        raw = metadata.get(RETRIEVAL_DIAGNOSTICS_KEY)

        if not isinstance(raw, dict):

            return None

        latency = metadata.get(RETRIEVAL_LATENCY_MS_KEY, raw.get(RETRIEVAL_LATENCY_MS_KEY, 0.0))

        try:

            latency_ms = float(latency)

        except (TypeError, ValueError):

            latency_ms = 0.0

        return cls(diagnostics=dict(raw), latency_ms=latency_ms)





def extract_retrieval_diagnostics(metadata: dict[str, Any] | None) -> dict[str, Any]:

    if not metadata:

        return {}

    raw = metadata.get(RETRIEVAL_DIAGNOSTICS_KEY)

    return dict(raw) if isinstance(raw, dict) else {}





def extract_retrieval_latency_ms(metadata: dict[str, Any] | None) -> float:

    if not metadata:

        return 0.0

    raw = metadata.get(RETRIEVAL_LATENCY_MS_KEY)

    try:

        return float(raw)

    except (TypeError, ValueError):

        return 0.0





def latency_bucket(latency_ms: float) -> str:

    if latency_ms < 50:

        return "lt_50ms"

    if latency_ms < 200:

        return "lt_200ms"

    if latency_ms < 500:

        return "lt_500ms"

    return "gte_500ms"





def summarize_retrieval_diagnostics(rows: list[DiagnosticRow]) -> dict[str, Any]:

    if not rows:

        return {

            "query_count": 0,

            "truncated_count": 0,

            "candidate_sources": {},

            "fallback_reasons": [],

            "scanned_count_total": 0,

            "latency_buckets": {},

            "latency_ms_avg": 0.0,

        }

    diag_dicts = [row.diagnostics for row in rows]

    latencies_ms = [row.latency_ms for row in rows]

    truncated_count = sum(1 for row in diag_dicts if row.get("truncated"))

    sources: dict[str, int] = {}

    for row in diag_dicts:

        key = str(row.get("candidate_source") or row.get("source") or "unknown")

        sources[key] = sources.get(key, 0) + 1

    buckets: dict[str, int] = {}

    for ms in latencies_ms:

        bucket = latency_bucket(ms)

        buckets[bucket] = buckets.get(bucket, 0) + 1

    fallback_reasons = [str(row.get("fallback_reason") or "") for row in diag_dicts if row.get("fallback_reason")]

    scanned_total = sum(int(row.get("scanned_count") or 0) for row in diag_dicts)

    return {

        "query_count": len(rows),

        "truncated_count": truncated_count,

        "candidate_sources": sources,

        "fallback_reasons": fallback_reasons,

        "scanned_count_total": scanned_total,

        "latency_buckets": buckets,

        "latency_ms_avg": (sum(latencies_ms) / len(latencies_ms)) if latencies_ms else 0.0,

    }


