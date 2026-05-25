"""第四层 Stage 4C：GardenEvent 日志 → Observatory（只读内存列表，不访问 Core / Repository）。"""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from memory_garden.core.models import GardenEvent, GardenEventType, GardenObjectType
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

_MAX_SCALAR_STR = 240
_MAX_LIST_ITEMS = 16
_MAX_PREVIEW = 220

_BUCKET_SEED = "seed_events"
_BUCKET_COURT = "court_events"
_BUCKET_GROWTH = "growth_events"
_BUCKET_DREAM = "dream_events"
_BUCKET_OTHER = "runtime_or_other_events"

_SEED_TYPES: frozenset[GardenEventType] = frozenset({GardenEventType.seed_created})
_COURT_TYPES: frozenset[GardenEventType] = frozenset(
    {GardenEventType.court_opened, GardenEventType.verdict_made}
)
_DREAM_TYPES: frozenset[GardenEventType] = frozenset({GardenEventType.dream_completed})
_GROWTH_TYPES: frozenset[GardenEventType] = frozenset(
    {
        GardenEventType.memory_planted,
        GardenEventType.memory_merged,
        GardenEventType.memory_pruned,
        GardenEventType.memory_composted,
        GardenEventType.memory_greenhoused,
        GardenEventType.memory_forgotten,
    }
)


def _clip(s: str, max_len: int) -> str:
    t = (s or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _journal_bucket(ev: GardenEvent) -> str:
    et = ev.event_type
    if et in _SEED_TYPES:
        return _BUCKET_SEED
    if et in _COURT_TYPES:
        return _BUCKET_COURT
    if et in _DREAM_TYPES:
        return _BUCKET_DREAM
    if et in _GROWTH_TYPES:
        return _BUCKET_GROWTH
    return _BUCKET_OTHER


def _observation_kind(ev: GardenEvent) -> ObservationKind:
    et = ev.event_type
    if et in _SEED_TYPES:
        return ObservationKind.SEED
    if et in _COURT_TYPES:
        return ObservationKind.COURT
    if et in _DREAM_TYPES:
        return ObservationKind.DREAM
    if et in _GROWTH_TYPES:
        return ObservationKind.GROWTH
    return ObservationKind.RUNTIME


def _infer_event_status(md: dict[str, Any]) -> ObservationStatus:
    lk = {k.lower(): v for k, v in md.items()}
    if lk.get("skipped") is True or lk.get("status") == "skipped":
        return ObservationStatus.SKIPPED
    st = lk.get("status")
    if isinstance(st, str) and st.lower() in ("failed", "error"):
        return ObservationStatus.ERROR
    if isinstance(st, str) and st.lower() in ("partial", "warn"):
        return ObservationStatus.PARTIAL
    err = lk.get("error") or lk.get("failed")
    if err is True or (isinstance(err, str) and err.strip()):
        return ObservationStatus.ERROR
    return ObservationStatus.OK


def _safe_flat_metadata(md: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not md:
        return out
    for k, v in md.items():
        key = str(k)[:96]
        if isinstance(v, (int, float, bool)) or v is None:
            out[key] = v
        elif isinstance(v, str):
            out[key] = _clip(v, _MAX_SCALAR_STR)
        elif isinstance(v, list):
            flat: list[Any] = []
            for item in v[:_MAX_LIST_ITEMS]:
                if isinstance(item, (int, float, bool)) or item is None:
                    flat.append(item)
                elif isinstance(item, str):
                    flat.append(_clip(item, _MAX_SCALAR_STR))
            if flat:
                out[key] = flat
        elif isinstance(v, dict):
            continue
        else:
            out[key] = str(v)[: _MAX_SCALAR_STR]
    return out


def _typed_source_ref_from_garden_object(ev: GardenEvent) -> ObservationSourceRef | None:
    """仅当 ``object_type`` 可强映射至 ``ObservationSourceRef`` 专有字段时才生成引用。"""
    ot = ev.object_type
    oid = ev.object_id
    if ot == GardenObjectType.seed:
        return ObservationSourceRef(seed_id=oid)
    if ot == GardenObjectType.memory_card:
        return ObservationSourceRef(memory_id=oid)
    if ot == GardenObjectType.court_case:
        return ObservationSourceRef(court_case_id=oid)
    if ot == GardenObjectType.dream_record:
        return ObservationSourceRef(dream_record_id=oid)
    if ot == GardenObjectType.garden_event:
        return ObservationSourceRef(event_id=oid)
    return None


def _links_from_event(ev: GardenEvent, safe_md: dict[str, Any]) -> list[ObservationLink]:
    gv_ref = ObservationSourceRef(event_id=ev.id)
    out: list[ObservationLink] = []

    raw_md = ev.metadata if isinstance(ev.metadata, dict) else {}
    sid = safe_md.get("seed_id") or raw_md.get("seed_id")
    if isinstance(sid, str) and sid.strip():
        out.append(
            ObservationLink(
                relation="event_to_seed",
                source_ref=gv_ref.model_copy(),
                target_ref=ObservationSourceRef(seed_id=sid.strip()[:512]),
                attributes={"garden_event_id": ev.id},
            )
        )
    for key, rel in (
        ("memory_card_id", "event_to_memory"),
        ("memory_id", "event_to_memory"),
        ("target_memory_id", "event_to_memory"),
    ):
        raw = safe_md.get(key) or raw_md.get(key)
        if isinstance(raw, str) and raw.strip():
            out.append(
                ObservationLink(
                    relation=rel,
                    source_ref=gv_ref.model_copy(),
                    target_ref=ObservationSourceRef(memory_id=raw.strip()[:512]),
                    attributes={"garden_event_id": ev.id},
                )
            )
    cid = safe_md.get("court_case_id") or raw_md.get("court_case_id")
    if isinstance(cid, str) and cid.strip():
        out.append(
            ObservationLink(
                relation="event_to_case",
                source_ref=gv_ref.model_copy(),
                target_ref=ObservationSourceRef(court_case_id=cid.strip()[:512]),
                attributes={"garden_event_id": ev.id},
            )
        )
    did = safe_md.get("dream_record_id") or raw_md.get("dream_record_id")
    if isinstance(did, str) and did.strip():
        out.append(
            ObservationLink(
                relation="event_to_dream",
                source_ref=gv_ref.model_copy(),
                target_ref=ObservationSourceRef(dream_record_id=did.strip()[:512]),
                attributes={"garden_event_id": ev.id},
            )
        )
    return out


class JournalObservationAdapter:
    """将内存中的 ``GardenEvent`` 列表映射为可追溯观测结构与视图。"""
    PhaseSpans = [_BUCKET_SEED, _BUCKET_COURT, _BUCKET_GROWTH, _BUCKET_DREAM, _BUCKET_OTHER]

    def trace_from_events(self, events: list[GardenEvent], *, trace_name: str = "garden_journal") -> ObservationTrace:
        root = ObservationSpan(
            name="garden_journal",
            parent_span_id=None,
            kind=ObservationKind.TRACE_ROOT,
            status=ObservationStatus.OK,
            attributes={"journal_trace_name": trace_name},
        )
        span_by_bucket: dict[str, ObservationSpan] = {}
        spans: list[ObservationSpan] = [root]
        for phase in self.PhaseSpans:
            sp = ObservationSpan(
                name=phase,
                parent_span_id=root.span_id,
                kind=_phase_kind(phase),
                status=ObservationStatus.OK,
                attributes={"bucket": phase},
            )
            span_by_bucket[phase] = sp
            spans.append(sp)

        obs_events: list[ObservationEvent] = []
        links: list[ObservationLink] = []
        previews: dict[str, str] = {}
        refs_list: list[ObservationSourceRef] = []
        ref_keys_seen: set[tuple[tuple[str, Any], ...]] = set()
        unmapped_object_refs: list[dict[str, str]] = []

        for ev in events:
            bucket = _journal_bucket(ev)
            previews[ev.id] = _clip(ev.summary, _MAX_PREVIEW)
            safe_md = _safe_flat_metadata(ev.metadata)

            attrs: dict[str, Any] = {
                **safe_md,
                "garden_event_id": ev.id,
                "event_type": ev.event_type.value,
                "object_type": ev.object_type.value,
                "object_id": _clip(ev.object_id, _MAX_SCALAR_STR),
                "summary_chars": len(ev.summary or ""),
                "journal_bucket": bucket,
                "journal_phase_span_name": bucket,
                "span_id_hint": span_by_bucket[bucket].span_id,
            }
            verdict = ev.metadata.get("verdict") if isinstance(ev.metadata, dict) else None
            if isinstance(verdict, str):
                attrs["verdict"] = _clip(verdict, 128)
            status = ev.metadata.get("status") if isinstance(ev.metadata, dict) else None
            if isinstance(status, str):
                attrs["status_hint"] = _clip(status, 64)

            obs_events.append(
                ObservationEvent(
                    name=ev.event_type.value,
                    kind=_observation_kind(ev),
                    occurred_at=ev.created_at,
                    status=_infer_event_status(ev.metadata if isinstance(ev.metadata, dict) else {}),
                    attributes=attrs,
                )
            )

            typed_src = _typed_source_ref_from_garden_object(ev)
            if typed_src is None:
                unmapped_object_refs.append(
                    {
                        "garden_event_id": ev.id,
                        "object_type": ev.object_type.value,
                        "object_id": _clip(ev.object_id, _MAX_SCALAR_STR),
                    }
                )

            refs_to_add: list[ObservationSourceRef] = []
            if typed_src is not None:
                refs_to_add.append(typed_src)
            refs_to_add.append(ObservationSourceRef(event_id=ev.id))

            for ref in refs_to_add:
                rs = ref.model_dump(exclude_none=True)
                if not rs:
                    continue
                key = tuple(sorted(rs.items()))
                if key not in ref_keys_seen:
                    ref_keys_seen.add(key)
                    refs_list.append(ref)

            links.extend(_links_from_event(ev, safe_md))

        span_counts = Counter(_journal_bucket(e) for e in events)
        for phase, sp in span_by_bucket.items():
            sp.attributes["event_count"] = span_counts.get(phase, 0)

        return ObservationTrace(
            root_span_id=root.span_id,
            spans=spans,
            events=obs_events,
            links=links,
            source_refs=refs_list,
            title=trace_name,
            metadata={
                "journal": {
                    "trace_name": trace_name,
                    "event_count": len(events),
                    "preview_by_garden_event_id": previews,
                    "type_counts": dict(Counter(e.event_type.value for e in events)),
                    "unmapped_object_refs": list(unmapped_object_refs),
                }
            },
        )

    def view_from_trace(
        self,
        trace: ObservationTrace,
        redaction_level: RedactionLevel = RedactionLevel.PUBLIC,
    ) -> ObservationView:
        raw_jm = trace.metadata.get("journal")
        jm = cast(dict[str, Any], raw_jm if isinstance(raw_jm, dict) else {})
        n = int(jm.get("event_count") or 0)
        tname = jm.get("trace_name") or "garden_journal"
        raw_previews = jm.get("preview_by_garden_event_id")
        previews: dict[str, str] = (
            cast(dict[str, str], raw_previews) if isinstance(raw_previews, dict) else {}
        )

        summary = _clip(f"花园日志观测「{tname}」：共 {n} 条事件。", 800)

        timeline_pub: list[dict[str, Any]] = []
        timeline_int: list[dict[str, Any]] = []
        seeds_stats: dict[str, Any] = {"count": 0, "event_ids": []}
        court_stats: dict[str, Any] = {"count": 0, "event_ids": []}
        growth_stats: dict[str, Any] = {"count": 0, "event_ids": []}
        dream_stats: dict[str, Any] = {"count": 0, "event_ids": []}

        for oe in trace.events:
            aid = oe.attributes.get("garden_event_id")
            pub_row = {
                "garden_event_id": aid,
                "name": oe.name,
                "occurred_at": oe.occurred_at.isoformat() if oe.occurred_at else None,
                "bucket": oe.attributes.get("journal_bucket"),
                "object_id": oe.attributes.get("object_id"),
                "status": oe.status.value,
            }
            timeline_pub.append(pub_row)
            int_row = dict(pub_row)
            if isinstance(aid, str) and aid in previews:
                int_row["summary_preview"] = previews[aid]
            timeline_int.append(int_row)

            b = oe.attributes.get("journal_bucket")
            if b == _BUCKET_SEED:
                seeds_stats["count"] += 1
                if isinstance(aid, str):
                    seeds_stats["event_ids"].append(aid)
            elif b == _BUCKET_COURT:
                court_stats["count"] += 1
                if isinstance(aid, str):
                    court_stats["event_ids"].append(aid)
            elif b == _BUCKET_GROWTH:
                growth_stats["count"] += 1
                if isinstance(aid, str):
                    growth_stats["event_ids"].append(aid)
            elif b == _BUCKET_DREAM:
                dream_stats["count"] += 1
                if isinstance(aid, str):
                    dream_stats["event_ids"].append(aid)

        for st in (seeds_stats, court_stats, growth_stats, dream_stats):
            st["event_ids"] = st["event_ids"][:64]

        safety = {
            "notes": [
                "基于 GardenEvent 列表的只读观测；未访问 Core / Repository。",
                "PUBLIC/SAFE 视图不含完整 summary 与原始 metadata 长文本。",
            ]
        }

        if redaction_level in (RedactionLevel.PUBLIC, RedactionLevel.SAFE):
            sections: dict[str, Any] = {
                "timeline": timeline_pub[:256],
                "seeds": seeds_stats,
                "court": court_stats,
                "growth": growth_stats,
                "dream": dream_stats,
                "safety": safety,
            }
        else:
            sections = {
                "timeline": timeline_int[:256],
                "seeds": seeds_stats,
                "court": court_stats,
                "growth": growth_stats,
                "dream": dream_stats,
                "safety": safety,
                "type_counts": jm.get("type_counts") if isinstance(jm.get("type_counts"), dict) else {},
            }

        return ObservationView(
            redaction_level=redaction_level,
            summary=summary,
            sections=sections,
            source_trace_id=trace.trace_id,
            metadata={"observation_adapter": "journal_v4c"},
        )


def _phase_kind(phase: str) -> ObservationKind:
    if phase == _BUCKET_SEED:
        return ObservationKind.SEED
    if phase == _BUCKET_COURT:
        return ObservationKind.COURT
    if phase == _BUCKET_GROWTH:
        return ObservationKind.GROWTH
    if phase == _BUCKET_DREAM:
        return ObservationKind.DREAM
    return ObservationKind.RUNTIME
