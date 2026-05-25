"""Seventh layer Stage 7D: Suite Packs (smoke / safety / full selectors, no execution)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.lab.models import LabCase, LabSuite


# ---------------------------------------------------------------------------
# pack name constants
# ---------------------------------------------------------------------------

SMOKE = "smoke"
SAFETY = "safety"
FULL = "full"

_PACK_NAMES = (SMOKE, SAFETY, FULL)


class UnknownPackError(ValueError):
    """Raised when an unknown pack name is requested."""


# ---------------------------------------------------------------------------
# pack model
# ---------------------------------------------------------------------------

class LabSuitePack(BaseModel):
    """Metadata-only description of a pre-defined suite pack (no execution)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    pack_name: str = Field(..., min_length=1)
    suite_ids: list[str] = Field(default_factory=list)
    case_ids: list[str] = Field(default_factory=list)
    total_cases: int = Field(ge=0)
    description: str = Field(default="")
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# case ID selectors
# ---------------------------------------------------------------------------

_SMOKE_CASE_IDS = (
    "lab.6b.seed.control_commands.no_preference_capture_v1",
    "lab.6b.runtime.short_circuit.no_after_reply_agent_v1",
    "lab.6b.harvest.no_full_card_dump_in_digest.v1",
    "lab.6b.observatory.public.no_full_user_message.v1",
)


_SAFETY_CASE_IDS = (
    "lab.6b.court.block_negative_identity_plant.v1",
    "lab.6b.growth.sensitive_greenhouse_path.v1",
    "lab.6b.harvest.no_full_card_dump_in_digest.v1",
    "lab.6b.observatory.public.no_full_user_message.v1",
    "lab.6b.observatory.public.no_full_assistant_reply.v1",
    # 占位 case：hard forget 无泄漏验证，待对应 fixture 实现后激活
    "lab.7d.hard_forget_no_leak.placeholder",
)

# ---------------------------------------------------------------------------
# all cases index
# ---------------------------------------------------------------------------

def _all_cases_index() -> dict[str, LabCase]:
    from memory_garden.lab.fixtures import default_lab_suites

    idx: dict[str, LabCase] = {}
    for s in default_lab_suites():
        for c in s.cases:
            idx[c.case_id] = c
    return idx


def _build_hard_forget_placeholder_suite() -> LabSuite:
    """Build a lightweight placeholder suite for hard forget (snapshot-contract only).

    This suite only carries assertions from rule_templates; no fixture actual_data.
    """
    from memory_garden.lab.rule_templates import hard_forget_must_not_leak_text

    return LabSuite(
        suite_id="lab_suite_hard_forget_placeholder_7d",
        name="Lab Hard Forget Placeholder (snapshot-contract)",
        cases=[
            LabCase(
                case_id="lab.7d.hard_forget_no_leak.placeholder",
                name="hard forget no leak (snapshot-contract placeholder)",
                description="Placeholder: asserts hard_forgotten_text_leak_count==0. No fixture example_actual.",
                assertions=hard_forget_must_not_leak_text(),
                metadata={
                    "primary_target": "observatory",
                    "fixture_kind": "hard_forget_placeholder",
                    "snapshot_contract": True,
                    "placeholder": True,
                    "note": "no fixture example_actual; integrator must provide snapshot",
                },
            )
        ],
        metadata={
            "fixture_kind": "hard_forget_placeholder",
            "version": "7d",
            "snapshot_contract": True,
            "placeholder": True,
        },
    )


# ---------------------------------------------------------------------------
# pack builders
# ---------------------------------------------------------------------------

def _build_suites_for_case_ids(case_ids: tuple[str, ...]) -> list[LabSuite]:
    """Build LabSuite objects by grouping selected cases by their original suite_id."""
    idx = _all_cases_index()
    suites_by_id: dict[str, list[LabCase]] = {}
    suite_names: dict[str, str] = {}
    cid_to_sid: dict[str, str] = {}

    from memory_garden.lab.fixtures import default_lab_suites
    for s in default_lab_suites():
        for c in s.cases:
            cid_to_sid[c.case_id] = s.suite_id
            suite_names[s.suite_id] = s.name

    ordered_sids: list[str] = []
    for cid in case_ids:
        if cid in cid_to_sid and cid in idx:
            sid = cid_to_sid[cid]
            if sid not in suites_by_id:
                suites_by_id[sid] = []
                ordered_sids.append(sid)
            suites_by_id[sid].append(idx[cid])

    return [
        LabSuite(
            suite_id=sid,
            name=suite_names.get(sid, ""),
            cases=suites_by_id[sid],
            metadata={"fixture_kind": "pack_selection", "pack": "dynamic"},
        )
        for sid in ordered_sids
    ]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def get_lab_suite_pack(pack_name: str) -> LabSuitePack:
    """Return pack metadata for the given pack name."""
    if pack_name not in _PACK_NAMES:
        raise UnknownPackError(
            f"Unknown pack {pack_name!r}. Valid: {list(_PACK_NAMES)}"
        )

    suites = get_lab_suites_for_pack(pack_name)
    suite_ids = sorted({s.suite_id for s in suites})
    case_ids: list[str] = []
    for s in suites:
        case_ids.extend(c.case_id for c in s.cases)

    total = len(case_ids)

    if pack_name == SMOKE:
        desc = "Smoke pack: critical seed / runtime / harvest / observatory cases."
        tags = ["smoke", "critical", "ci"]
    elif pack_name == SAFETY:
        desc = (
            "Safety pack: greenhouse / compost / observatory redaction / hard forget cases. "
            "Hard forget case is snapshot-contract placeholder (no fixture actual_data)."
        )
        tags = ["safety", "greenhouse", "observatory", "snapshot-contract", "placeholder"]
    else:
        desc = "Full pack: all default_lab_suites cases."
        tags = ["full", "all", "regression"]

    return LabSuitePack(
        pack_name=pack_name,
        suite_ids=suite_ids,
        case_ids=case_ids,
        total_cases=total,
        description=desc,
        tags=tags,
    )


def get_lab_suites_for_pack(pack_name: str) -> list[LabSuite]:
    """Return the list of LabSuite objects for the given pack name (no execution)."""
    if pack_name == SMOKE:
        return _build_suites_for_case_ids(_SMOKE_CASE_IDS)

    if pack_name == SAFETY:
        suites = _build_suites_for_case_ids(_SAFETY_CASE_IDS)
        suites.append(_build_hard_forget_placeholder_suite())
        return suites

    if pack_name == FULL:
        from memory_garden.lab.fixtures import default_lab_suites
        return list(default_lab_suites())

    raise UnknownPackError(
        f"Unknown pack {pack_name!r}. Valid: {list(_PACK_NAMES)}"
    )


def list_lab_suite_packs() -> list[LabSuitePack]:
    """Return pack metadata for all known packs in stable order."""
    return [get_lab_suite_pack(n) for n in _PACK_NAMES]


__all__ = [
    "SMOKE",
    "SAFETY",
    "FULL",
    "LabSuitePack",
    "UnknownPackError",
    "get_lab_suite_pack",
    "get_lab_suites_for_pack",
    "list_lab_suite_packs",
]