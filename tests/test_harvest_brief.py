"""第三层 Stage 3F：HarvestGardenBriefWriter。"""

import inspect
import json


from memory_garden.harvest.brief import HarvestGardenBriefWriter
from memory_garden.harvest.models import (
    BouquetSlot,
    BriefMode,
    GardenBouquet,
    HarvestQuery,
    HarvestScore,
    MemoryCandidate,
)
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.runtime.session import GardenBrief as RuntimeGardenBrief


def _sm(lifecycle: str = "sprout") -> dict:
    return {"lifecycle": lifecycle, "thorns": "短", "importance": 0.5, "confidence": 0.5}


def _c(cid: str, mid: str, lifecycle: str = "sprout") -> MemoryCandidate:
    return MemoryCandidate(
        candidate_id=cid,
        memory_id=mid,
        excerpt="",
        metadata={"source_memory": _sm(lifecycle)},
    )


def _bq(
    slots: dict,
    placements: list[dict],
    excluded: list | None = None,
) -> GardenBouquet:
    return GardenBouquet(
        slots=slots,
        metadata={"placements": placements, "excluded": list(excluded or [])},
    )


def test_primary_memory_id_in_use_and_sources() -> None:
    q = HarvestQuery(raw_user_text="我想整理界面")
    c = _c("cp", "mem-p", "sprout")
    bq = _bq(
        {BouquetSlot.PRIMARY: ["cp"], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: []},
        [{"candidate_id": "cp", "memory_id": "mem-p", "slot": "primary", "reason": "x"}],
    )
    br = HarvestGardenBriefWriter().write(q, bq, [c], [], None)
    assert "mem-p" in br.use
    assert br.source_memory_ids == ["mem-p"]


def test_corroboration_can_appear_in_use_and_nudge_references_corroboration() -> None:
    q = HarvestQuery(raw_user_text="核对")
    c = _c("cc", "mem-c")
    bq = _bq(
        {BouquetSlot.PRIMARY: [], BouquetSlot.CORROBORATION: ["cc"], BouquetSlot.GUARDRAIL: []},
        [{"candidate_id": "cc", "memory_id": "mem-c", "slot": "corroboration", "reason": "x"}],
    )
    br = HarvestGardenBriefWriter().write(q, bq, [c], [], None)
    assert "mem-c" in br.use
    assert "CORROBORATION" in br.nudge


def test_guardrail_in_avoid_not_in_source_ids() -> None:
    q = HarvestQuery(raw_user_text="-")
    good = _c("ok", "mem-ok")
    bad = _c("gr", "mem-r")
    bq = _bq(
        {
            BouquetSlot.PRIMARY: ["ok"],
            BouquetSlot.CORROBORATION: [],
            BouquetSlot.GUARDRAIL: ["gr"],
        },
        [
            {"candidate_id": "ok", "memory_id": "mem-ok", "slot": "primary", "reason": "p"},
            {"candidate_id": "gr", "memory_id": "mem-r", "slot": "guardrail", "reason": "g"},
        ],
    )
    br = HarvestGardenBriefWriter().write(q, bq, [good, bad], [], None)
    assert "mem-r" in br.avoid
    assert "mem-r" not in br.source_memory_ids
    assert "mem-ok" in br.source_memory_ids


def test_greenhouse_not_written_as_positive_reference() -> None:
    q = HarvestQuery(raw_user_text="温室")
    gh = _c("gh", "mem-gh", lifecycle="greenhouse")
    bq = _bq(
        {BouquetSlot.PRIMARY: [], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: ["gh"]},
        [{"candidate_id": "gh", "memory_id": "mem-gh", "slot": "guardrail", "reason": "g"}],
    )
    br = HarvestGardenBriefWriter().write(q, bq, [gh], [], None)
    assert "mem-gh" not in br.source_memory_ids
    assert "mem-gh" not in br.use
    assert "mem-gh" in br.avoid


def test_source_memory_ids_dedup_and_subset_of_bouquet_positives() -> None:
    q = HarvestQuery(raw_user_text="d")
    c = _c("a", "mem-dup")
    bq = _bq(
        {BouquetSlot.PRIMARY: ["a", "a"], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: []},
        [
            {"candidate_id": "a", "memory_id": "mem-dup", "slot": "primary", "reason": "1"},
            {"candidate_id": "a", "memory_id": "mem-dup", "slot": "primary", "reason": "2"},
        ],
    )
    br = HarvestGardenBriefWriter().write(q, bq, [c], [], None)
    assert br.source_memory_ids == ["mem-dup"]


def test_excluded_candidate_not_in_source_ids() -> None:
    q = HarvestQuery(raw_user_text="e")
    c1 = _c("keep", "m-keep")
    c2 = _c("cut", "m-cut")
    bq = _bq(
        {BouquetSlot.PRIMARY: ["keep", "cut"], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: []},
        [
            {"candidate_id": "keep", "memory_id": "m-keep", "slot": "primary", "reason": "p"},
            {"candidate_id": "cut", "memory_id": "m-cut", "slot": "primary", "reason": "p"},
        ],
        excluded=[{"candidate_id": "cut", "memory_id": "m-cut", "reason": "ex"}],
    )
    br = HarvestGardenBriefWriter().write(q, bq, [c1, c2], [], None)
    assert "m-keep" in br.source_memory_ids
    assert "m-cut" not in br.source_memory_ids


def test_token_estimate_positive_integer_deterministic() -> None:
    q = HarvestQuery(raw_user_text="tok")
    c = _c("t", "m-t")
    bq = _bq(
        {BouquetSlot.PRIMARY: ["t"], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: []},
        [{"candidate_id": "t", "memory_id": "m-t", "slot": "primary", "reason": ""}],
    )
    w = HarvestGardenBriefWriter()
    b1 = w.write(q, bq, [c], [], None)
    b2 = w.write(q, bq, [c], [], None)
    assert isinstance(b1.token_estimate, int)
    assert b1.token_estimate >= 8
    assert b1.token_estimate == b2.token_estimate


def test_harvest_brief_json_roundtrip() -> None:
    q = HarvestQuery(raw_user_text="j")
    c = _c("j", "m-j")
    bq = _bq(
        {BouquetSlot.PRIMARY: ["j"], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: []},
        [{"candidate_id": "j", "memory_id": "m-j", "slot": "primary", "reason": ""}],
    )
    br = HarvestGardenBriefWriter().write(q, bq, [c], [], None)
    raw = br.model_dump(mode="json")
    json.dumps(raw)


def test_to_runtime_brief_has_no_token_or_mode_fields() -> None:
    q = HarvestQuery(raw_user_text="r")
    c = _c("r", "m-r")
    bq = _bq(
        {BouquetSlot.PRIMARY: ["r"], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: []},
        [{"candidate_id": "r", "memory_id": "m-r", "slot": "primary", "reason": ""}],
    )
    hb = HarvestGardenBriefWriter().write(q, bq, [c], [], None)
    rt = hb.to_runtime_brief()
    assert isinstance(rt, RuntimeGardenBrief)
    assert "token_estimate" not in RuntimeGardenBrief.model_fields
    dumped = rt.model_dump()
    assert "mode" not in dumped


def test_brief_dump_not_embedding_source_memory_blob() -> None:
    q = HarvestQuery(raw_user_text="!")
    huge = "Y" * 5000
    c = MemoryCandidate(
        candidate_id="h",
        memory_id="m-h",
        excerpt="",
        metadata={"source_memory": {"lifecycle": "sprout", "essence": huge, "thorns": "短"}},
    )
    bq = _bq(
        {BouquetSlot.PRIMARY: ["h"], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: []},
        [{"candidate_id": "h", "memory_id": "m-h", "slot": "primary", "reason": ""}],
    )
    br = HarvestGardenBriefWriter().write(q, bq, [c], [], None)
    blob = json.dumps(br.model_dump(mode="json"))
    assert huge not in blob


def test_writer_preserves_input_objects() -> None:
    q = HarvestQuery(raw_user_text="im")
    c = _c("i", "m-i")
    bq = _bq(
        {BouquetSlot.PRIMARY: ["i"], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: []},
        [{"candidate_id": "i", "memory_id": "m-i", "slot": "primary", "reason": ""}],
    )
    s = HarvestScore(candidate_id="i", relevance=0.5)
    id_c, id_b, id_s = id(c), id(bq), id(s)
    HarvestGardenBriefWriter().write(q, bq, [c], [s])
    assert id(c) == id_c and id(bq) == id_b and id(s) == id_s


def test_brief_writer_source_has_no_ml_stack() -> None:
    import memory_garden.harvest.brief as bf

    t = inspect.getsource(bf).lower()
    for bad in ("openai", "anthropic", "embed", "vector", "faiss", "llm", "rerank"):
        assert bad not in t


def test_policy_changes_brief_mode() -> None:
    q = HarvestQuery(raw_user_text="m")
    c = _c("m", "mm")
    bq = _bq(
        {BouquetSlot.PRIMARY: ["m"], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: []},
        [{"candidate_id": "m", "memory_id": "mm", "slot": "primary", "reason": ""}],
    )
    pol = HarvestBudgetPolicy(default_brief_mode=BriefMode.CURATED)
    br = HarvestGardenBriefWriter().write(q, bq, [c], [], pol)
    assert br.mode == BriefMode.CURATED
