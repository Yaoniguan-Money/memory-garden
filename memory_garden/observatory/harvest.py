"""第四层 Stage 4B：将第三层 HarvestTrace 转为 Observatory 结构与视图（只读，不入库）。"""

from __future__ import annotations

from typing import Any, cast

from memory_garden.harvest.models import (
    BouquetSlot,
    GardenBouquet,
    HarvestGardenBrief,
    HarvestTrace,
)
from memory_garden.observatory.models import (
    ObservationEvent,
    ObservationKind,
    ObservationLink,
    ObservationSourceRef,
    ObservationSpan,
    ObservationStatus,
    ObservationTrace,
    ObservationView,
    RedactionLevel,
)


def _clip(s: str, max_len: int) -> str:
    t = (s or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _sanitize_policy_note(h: HarvestTrace, max_chars: int) -> str:
    parts: list[str] = []
    for d in h.policy_decisions:
        for r in d.reasons or []:
            if isinstance(r, str) and r.strip():
                parts.append(r.strip())
    return _clip("; ".join(parts), max_chars)


class HarvestObservationAdapter:
    """Harvest 专用观测映射：不产生新采摘、不写存储、不透传长正文快照。"""

    _SPAN_CHILDREN = (
        "collect_candidates",
        "score_candidates",
        "rank_candidates",
        "build_bouquet",
        "write_brief",
    )

    def trace_from_harvest(self, harvest_trace: HarvestTrace) -> ObservationTrace:
        h = harvest_trace
        root = ObservationSpan(
            name="harvest_pipeline",
            parent_span_id=None,
            kind=ObservationKind.TRACE_ROOT,
            status=ObservationStatus.OK,
            attributes={"harvest_trace_id": h.trace_id},
        )
        spans: list[ObservationSpan] = [root]
        for step in self._SPAN_CHILDREN:
            spans.append(
                ObservationSpan(
                    name=step,
                    parent_span_id=root.span_id,
                    kind=ObservationKind.HARVEST,
                    status=ObservationStatus.OK,
                    attributes={
                        "harvest_trace_id": h.trace_id,
                        "stage": step,
                    },
                )
            )

        n_cand = len(h.candidates)
        n_scores = len(h.scores)
        n_pol = len(h.policy_decisions)

        events: list[ObservationEvent] = [
            ObservationEvent(
                name="harvest_started",
                kind=ObservationKind.HARVEST,
                attributes={"harvest_trace_id": h.trace_id},
            ),
            ObservationEvent(
                name="candidates_collected",
                kind=ObservationKind.HARVEST,
                attributes={
                    "harvest_trace_id": h.trace_id,
                    "count": n_cand,
                },
            ),
            ObservationEvent(
                name="scores_created",
                kind=ObservationKind.HARVEST,
                attributes={
                    "harvest_trace_id": h.trace_id,
                    "count": n_scores,
                },
            ),
            ObservationEvent(
                name="bouquet_built",
                kind=ObservationKind.HARVEST,
                attributes={
                    "harvest_trace_id": h.trace_id,
                    "has_bouquet": h.bouquet is not None,
                    "bouquet_id": h.bouquet.bouquet_id if h.bouquet else None,
                },
            ),
            ObservationEvent(
                name="brief_written",
                kind=ObservationKind.HARVEST,
                attributes={
                    "harvest_trace_id": h.trace_id,
                    "has_brief": h.brief is not None,
                    "token_estimate": h.brief.token_estimate if h.brief else None,
                    "brief_mode": h.brief.mode.value if h.brief else None,
                },
            ),
            ObservationEvent(
                name="harvest_completed",
                kind=ObservationKind.HARVEST,
                attributes={
                    "harvest_trace_id": h.trace_id,
                    "candidate_count": n_cand,
                    "score_count": n_scores,
                    "policy_decisions_count": n_pol,
                    "model_calls_count": len(h.model_calls),
                },
            ),
        ]

        source_refs: list[ObservationSourceRef] = [
            ObservationSourceRef(harvest_trace_id=h.trace_id),
        ]
        seen_mem: set[str] = set()
        for c in h.candidates:
            if c.memory_id and c.memory_id not in seen_mem:
                seen_mem.add(c.memory_id)
                source_refs.append(ObservationSourceRef(memory_id=c.memory_id))
        if h.brief:
            for mid in h.brief.source_memory_ids:
                if mid and mid not in seen_mem:
                    seen_mem.add(mid)
                    source_refs.append(ObservationSourceRef(memory_id=mid))

        links = self._build_links(h)

        meta_harvest = self._compact_harvest_meta(h)
        retrieval_diag = h.metadata.get("retrieval_diagnostics")
        if isinstance(retrieval_diag, dict):
            meta_harvest["retrieval_diagnostics"] = dict(retrieval_diag)

        return ObservationTrace(
            root_span_id=root.span_id,
            spans=spans,
            events=events,
            links=links,
            source_refs=source_refs,
            title="Harvest pipeline observation",
            started_at=h.query.created_at if h.query.created_at else None,
            ended_at=h.finalized_at,
            metadata={"harvest": meta_harvest},
        )

    def _build_links(self, h: HarvestTrace) -> list[ObservationLink]:
        out: list[ObservationLink] = []
        hv_ref = ObservationSourceRef(harvest_trace_id=h.trace_id)

        for c in h.candidates:
            out.append(
                ObservationLink(
                    relation="candidate_to_memory",
                    source_ref=None,
                    target_ref=ObservationSourceRef(memory_id=c.memory_id),
                    attributes={
                        "harvest_trace_id": h.trace_id,
                        "candidate_id": c.candidate_id,
                    },
                )
            )

        if h.brief:
            for mid in h.brief.source_memory_ids:
                out.append(
                    ObservationLink(
                        relation="brief_to_memory",
                        source_ref=hv_ref.model_copy(deep=True),
                        target_ref=ObservationSourceRef(memory_id=mid),
                        attributes={
                            "harvest_trace_id": h.trace_id,
                        },
                    )
                )

        bq = h.bouquet
        if bq:
            placements = bq.metadata.get("placements")
            rows: list[Any] = []
            if isinstance(placements, list):
                rows.extend(placements)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cid = row.get("candidate_id")
                slot_v = row.get("slot")
                if isinstance(cid, str) and cid:
                    out.append(
                        ObservationLink(
                            relation="bouquet_to_candidate",
                            source_ref=ObservationSourceRef(harvest_trace_id=h.trace_id),
                            target_ref=None,
                            attributes={
                                "harvest_trace_id": h.trace_id,
                                "bouquet_id": bq.bouquet_id,
                                "candidate_id": cid,
                                "slot": slot_v if isinstance(slot_v, str) else str(slot_v) if slot_v is not None else "",
                            },
                        )
                    )

        return out

    def _compact_harvest_meta(self, h: HarvestTrace) -> dict[str, Any]:
        cand_pub: list[dict[str, Any]] = []
        for c in h.candidates:
            cand_pub.append(
                {
                    "candidate_id": c.candidate_id,
                    "memory_id": c.memory_id,
                    "match_type": c.match_type.value,
                }
            )

        bouquet_block: dict[str, Any] = {}
        if h.bouquet:
            bouquet_block = {
                "bouquet_id": h.bouquet.bouquet_id,
                "slot_counts": {
                    slot.value if isinstance(slot, BouquetSlot) else str(slot): len(ids or [])
                    for slot, ids in (h.bouquet.slots or {}).items()
                },
                "placements_count": len(self._placement_rows(h.bouquet)),
            }

        brief_block: dict[str, Any] = {}
        brief_internal: dict[str, Any] = {"policy_note": _sanitize_policy_note(h, 500)}
        if h.brief:
            br: HarvestGardenBrief = h.brief
            brief_block = {
                "source_memory_ids": list(br.source_memory_ids),
                "token_estimate": br.token_estimate,
                "mode": br.mode.value,
                "intent_len": len(br.intent or ""),
                "use_len": len(br.use or ""),
            }
            brief_internal.update(
                {
                    "intent_excerpt": _clip(br.intent, 260),
                    "avoid_excerpt": _clip(br.avoid, 200),
                }
            )

        return {
            "h3_trace_id": h.trace_id,
            "query_id": h.query.query_id,
            "session_id": h.query.session_id,
            "lens_ids": [lz.lens_id for lz in h.lenses],
            "counts": {
                "candidates": len(h.candidates),
                "scores": len(h.scores),
                "policy_decisions": len(h.policy_decisions),
            },
            "candidates_public": cand_pub,
            "bouquet": bouquet_block,
            "brief_metrics": brief_block,
            "_internal_preview": brief_internal,
        }

    def _placement_rows(self, bq: GardenBouquet) -> list[Any]:
        p = bq.metadata.get("placements")
        if isinstance(p, list):
            return p
        return []

    def _build_pipeline_section(self, trace: ObservationTrace) -> dict[str, Any]:
        stages = [s.name for s in trace.spans if s.parent_span_id]
        return {
            "root_span_name": next((s.name for s in trace.spans if s.parent_span_id is None), None),
            "stages": stages,
            "finalized_at": trace.ended_at.isoformat() if trace.ended_at else None,
        }

    def _build_candidate_section(self, hv: dict[str, Any], n_c: int) -> dict[str, Any]:
        return {
            "count": n_c,
            "items": list(hv.get("candidates_public") or [])[:96],
        }

    def _build_bouquet_section(self, hv: dict[str, Any]) -> dict[str, Any]:
        return dict(hv.get("bouquet") or {})

    def _build_brief_section(
        self,
        hv: dict[str, Any],
        brief_m: dict[str, Any],
        *,
        redaction_level: RedactionLevel,
    ) -> dict[str, Any]:
        if redaction_level in (RedactionLevel.PUBLIC, RedactionLevel.SAFE):
            return {
                "source_memory_ids": list(brief_m.get("source_memory_ids") or [])[:128],
                "token_estimate": brief_m.get("token_estimate"),
                "mode": brief_m.get("mode"),
                "field_lengths": {
                    k: brief_m.get(k)
                    for k in ("intent_len", "use_len")
                    if brief_m.get(k) is not None
                },
            }
        if redaction_level == RedactionLevel.INTERNAL:
            prv = hv.get("_internal_preview")
            prv_d = prv if isinstance(prv, dict) else {}
            return {
                **{k: v for k, v in brief_m.items()},
                "intent_excerpt": prv_d.get("intent_excerpt"),
                "avoid_excerpt": prv_d.get("avoid_excerpt"),
                "policy_reasons_preview": prv_d.get("policy_note"),
            }
        return {}

    def _build_safety_section(self) -> dict[str, Any]:
        return {
            "notes": [
                "规则版 Harvest 观测；不包含向量语义评分。",
                "未拼接 MemoryCandidate.source_memory 全文。",
            ],
        }

    def view_from_trace(
        self,
        trace: ObservationTrace,
        redaction_level: RedactionLevel = RedactionLevel.PUBLIC,
    ) -> ObservationView:
        raw_hv = trace.metadata.get("harvest")
        hv = cast(dict[str, Any], raw_hv if isinstance(raw_hv, dict) else {})

        h3 = hv.get("h3_trace_id")
        raw_cnt = hv.get("counts")
        cnt = cast(dict[str, Any], raw_cnt if isinstance(raw_cnt, dict) else {})
        n_c = int(cnt.get("candidates") or 0)
        raw_brief = hv.get("brief_metrics")
        brief_m = cast(dict[str, Any], raw_brief if isinstance(raw_brief, dict) else {})

        summary = _clip(
            (
                f"本轮 Harvest 采摘观测：第三层追溯 {h3 or 'unknown'}；"
                f"候选 {n_c} 条；简报 token 粗估 {brief_m.get('token_estimate')}；"
                f"模式 {brief_m.get('mode')}。"
            ),
            800,
        )

        sections: dict[str, Any] = {
            "pipeline": self._build_pipeline_section(trace),
            "candidates": self._build_candidate_section(hv, n_c),
            "bouquet": self._build_bouquet_section(hv),
            "brief": self._build_brief_section(hv, brief_m, redaction_level=redaction_level),
            "safety": self._build_safety_section(),
        }
        retrieval_diag = hv.get("retrieval_diagnostics")
        if isinstance(retrieval_diag, dict):
            sections["retrieval_quality"] = dict(retrieval_diag)

        return ObservationView(
            redaction_level=redaction_level,
            summary=summary,
            sections=sections,
            source_trace_id=trace.trace_id,
            metadata={"observation_adapter": "harvest_v4b"},
        )
