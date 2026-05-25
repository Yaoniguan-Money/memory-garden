"""第三层 Stage 3F：规则版 HarvestGardenBrief 撰写（短文、可追溯、不接 Runtime）。"""

from __future__ import annotations

from typing import Any

from memory_garden.harvest.models import (
    BouquetSlot,
    BriefMode,
    GardenBouquet,
    HarvestGardenBrief,
    HarvestQuery,
    HarvestScore,
    MemoryCandidate,
)
from memory_garden.harvest.policy import HarvestBudgetPolicy

_FIELD_MAX = 500
_TOKEN_PAD = 20


def _clamp_field(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return "暂无可展示摘要。"
    if len(t) > _FIELD_MAX:
        return t[: _FIELD_MAX - 3].rstrip() + "..."
    return t


def _cand_map(candidates: list[MemoryCandidate]) -> dict[str, MemoryCandidate]:
    return {c.candidate_id: c for c in candidates}


def _lifecycle_for(cand: MemoryCandidate | None) -> str:
    if cand is None:
        return ""
    sm = cand.metadata.get("source_memory")
    if not isinstance(sm, dict):
        return ""
    lc = sm.get("lifecycle")
    return lc.strip().lower() if isinstance(lc, str) else ""


def _risky_lifecycle(lc: str) -> bool:
    return lc in ("greenhouse", "pruned", "composted")


def _excluded_candidate_ids(meta: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    raw = meta.get("excluded")
    if not isinstance(raw, list):
        return out
    for row in raw:
        if isinstance(row, dict):
            cid = row.get("candidate_id")
            if isinstance(cid, str) and cid:
                out.add(cid)
    return out


def _placements_list(meta: dict[str, Any]) -> list[dict[str, Any]]:
    p = meta.get("placements")
    if not isinstance(p, list):
        return []
    return [x for x in p if isinstance(x, dict)]


def _all_bouquet_cids(bq: GardenBouquet) -> set[str]:
    s: set[str] = set()
    for _k, ids in (bq.slots or {}).items():
        if isinstance(ids, list):
            for x in ids:
                if isinstance(x, str):
                    s.add(x)
    return s


def _append_slot(
    bouquet: GardenBouquet,
    slot: BouquetSlot,
    *,
    excluded_cid: set[str],
    cmap: dict[str, MemoryCandidate],
    pos_mids: list[str],
    guard_mids: list[str],
    seen_pos: set[str],
    seen_guard: set[str],
) -> None:
    for cid in bouquet.slots.get(slot, []) or []:
        if not isinstance(cid, str) or cid in excluded_cid:
            continue
        cobj = cmap.get(cid)
        mid = cobj.memory_id if cobj is not None else ""
        if not mid:
            continue
        lc = _lifecycle_for(cobj)
        risky = _risky_lifecycle(lc)
        if slot == BouquetSlot.GUARDRAIL:
            if mid not in seen_guard:
                seen_guard.add(mid)
                guard_mids.append(mid)
        else:
            if risky:
                continue
            if mid not in seen_pos:
                seen_pos.add(mid)
                pos_mids.append(mid)


def _order_by_memory_ids_meta(pos_ids: list[str], meta: dict[str, Any]) -> list[str]:
    """在 ``metadata[\"memory_ids_ordered\"]``（若存在）中优先保留出现顺序，再追加其余积极侧 id。"""
    raw = meta.get("memory_ids_ordered")
    if not isinstance(raw, list):
        return pos_ids
    pos_set = set(pos_ids)
    ordered: list[str] = []
    seen: set[str] = set()
    for mid in raw:
        if isinstance(mid, str) and mid in pos_set and mid not in seen:
            ordered.append(mid)
            seen.add(mid)
    for mid in pos_ids:
        if mid not in seen:
            ordered.append(mid)
            seen.add(mid)
    return ordered


def _token_estimate_from_fields(a: HarvestGardenBrief) -> int:
    blob = "".join(
        [
            a.intent,
            a.use,
            a.avoid,
            a.style,
            a.safety,
            a.nudge,
            ",".join(a.source_memory_ids),
        ]
    )
    return max(8, len(blob) // 4 + _TOKEN_PAD)


class HarvestGardenBriefWriter:
    """依据花束槽位组装短简报：**PRIMARY/CORROBORATION**→积极参考区；**GUARDRAIL**→谨慎区。"""

    def write(
        self,
        query: HarvestQuery,
        bouquet: GardenBouquet,
        candidates: list[MemoryCandidate],
        scores: list[HarvestScore],
        policy: HarvestBudgetPolicy | None = None,
    ) -> HarvestGardenBrief:
        _ = scores  # 本规则版不向文案注入分数细节，避免虚构
        cmap = _cand_map(candidates)
        meta = dict(bouquet.metadata) if bouquet.metadata else {}
        excluded_cid = _excluded_candidate_ids(meta)
        placements = _placements_list(meta)

        q_hint = query.raw_user_text.strip()
        q_clip = q_hint[:100] + ("…" if len(q_hint) > 100 else "")
        intent = _clamp_field(
            f"围绕用户表达的摘录式简报（非断言）。"
            f"上下文摘录：{'（空）' if not q_clip else q_clip}"
        )

        pos_mids_ordered: list[str] = []
        guard_mids_ordered: list[str] = []
        seen_pos: set[str] = set()
        seen_guard: set[str] = set()
        in_bouquet = _all_bouquet_cids(bouquet)

        for row in placements:
            cid = row.get("candidate_id")
            mid = row.get("memory_id")
            slot_raw = row.get("slot")
            slot_s = slot_raw if isinstance(slot_raw, str) else ""
            if not isinstance(cid, str) or cid in excluded_cid or cid not in in_bouquet:
                continue
            cobj = cmap.get(cid)
            lc = _lifecycle_for(cobj)
            risky = _risky_lifecycle(lc)

            if not isinstance(mid, str) or not mid:
                continue

            if slot_s == BouquetSlot.PRIMARY.value:
                if not risky and mid not in seen_pos:
                    seen_pos.add(mid)
                    pos_mids_ordered.append(mid)
            elif slot_s == BouquetSlot.CORROBORATION.value:
                if not risky and mid not in seen_pos:
                    seen_pos.add(mid)
                    pos_mids_ordered.append(mid)
            elif slot_s == BouquetSlot.GUARDRAIL.value:
                if mid not in seen_guard:
                    seen_guard.add(mid)
                    guard_mids_ordered.append(mid)

        # 花束槽位补全：避免仅出现在 slots 却未写入 placements 的候选被遗漏
        _append_slot(
            bouquet,
            BouquetSlot.PRIMARY,
            excluded_cid=excluded_cid,
            cmap=cmap,
            pos_mids=pos_mids_ordered,
            guard_mids=guard_mids_ordered,
            seen_pos=seen_pos,
            seen_guard=seen_guard,
        )
        _append_slot(
            bouquet,
            BouquetSlot.CORROBORATION,
            excluded_cid=excluded_cid,
            cmap=cmap,
            pos_mids=pos_mids_ordered,
            guard_mids=guard_mids_ordered,
            seen_pos=seen_pos,
            seen_guard=seen_guard,
        )
        _append_slot(
            bouquet,
            BouquetSlot.GUARDRAIL,
            excluded_cid=excluded_cid,
            cmap=cmap,
            pos_mids=pos_mids_ordered,
            guard_mids=guard_mids_ordered,
            seen_pos=seen_pos,
            seen_guard=seen_guard,
        )

        pos_mids_ordered = _order_by_memory_ids_meta(pos_mids_ordered, meta)

        if pos_mids_ordered:
            use = (
                "如与当前话题相关，可参考以下记忆标识（PRIMARY/CORROBORATION）："
                + "、".join(pos_mids_ordered[:48])
                + "。**不得**将此视为对用户状态的必然结论。"
            )
        else:
            use = (
                "当前花束无可作为积极采纳依据的 PRIMARY/CORROBORATION 记忆标识；请勿强行套用外部记忆。"
            )

        avoid = ""
        if guard_mids_ordered:
            avoid = _clamp_field(
                "以下为 GUARDRAIL/风险向标识，**不作为**可信事实或直接指导："
                + "、".join(guard_mids_ordered[:48])
                + "。若为温室、修剪或堆肥状态，请避免写成积极可用的长期结论。"
            )
        else:
            avoid = (
                "无单独 GUARDRAIL 条目；仍请避免对用户意图作过度断言；"
                "如记忆与上下文无关请忽略简报。"
            )

        style = _clamp_field("语气中性简短；以标识占位指代记忆卡，请勿拼接记忆卡全文。")
        safety = _clamp_field(
            "安全：不断言用户偏好或事实确定性；不向用户转嫁未核验结论；温室/归档类条目不得改写为正向依据。"
        )
        nudge = _clamp_field(
            "复核提示：请将简报仅作编排线索；CORROBORATION 可在相关时一并核对上下文；若无关则跳过。"
        )

        source_ids = list(pos_mids_ordered)
        brief_mode = policy.default_brief_mode if policy is not None else BriefMode.TEMPLATE

        hb = HarvestGardenBrief(
            intent=intent,
            use=_clamp_field(use),
            avoid=_clamp_field(avoid),
            style=style,
            safety=safety,
            nudge=nudge,
            source_memory_ids=source_ids[:128],
            token_estimate=None,
            mode=brief_mode,
        )
        te = _token_estimate_from_fields(hb)
        return hb.model_copy(update={"token_estimate": te})
