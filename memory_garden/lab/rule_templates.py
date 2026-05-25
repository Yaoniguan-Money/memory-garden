"""Seventh layer Stage 7C: Memory Garden Rule Templates (LabAssertion factories, no execution)."""

from __future__ import annotations

from memory_garden.lab.models import LabAssertion, LabAssertionType, LabTarget


# ---------------------------------------------------------------------------
# Seed domain templates
# ---------------------------------------------------------------------------

def seed_min_count(min_count: int) -> LabAssertion:
    """Assert that at least *min_count* pending preference signals exist.

    Uses ``count_equals`` on ``seed.pending_preference_signals`` with the
    exact count expected in a snapshot regression scenario.
    """
    return LabAssertion(
        assertion_type=LabAssertionType.count_equals,
        target=LabTarget.seed,
        field_path="pending_preference_signals",
        expected=min_count,
    )


def seed_forbids_control_command_memory() -> list[LabAssertion]:
    """Control commands must not create preference seeds or echo as preference slot."""
    return [
        LabAssertion(
            assertion_type=LabAssertionType.field_absent,
            target=LabTarget.seed,
            field_path="control_command_echo_as_preference_seed",
            expected=None,
        ),
        LabAssertion(
            assertion_type=LabAssertionType.count_equals,
            target=LabTarget.seed,
            field_path="pending_preference_signals",
            expected=0,
        ),
    ]


def assistant_reply_must_not_be_user_memory() -> list[LabAssertion]:
    """Assistant reply text must not be recorded as user-originated memory input.

    Uses a placeholder field path (snapshot contract, not a business execution path).
    """
    return [
        LabAssertion(
            assertion_type=LabAssertionType.is_false,
            target=LabTarget.seed,
            field_path="assistant_reply_recorded_as_user_input",
            expected=None,
        ),
    ]


# ---------------------------------------------------------------------------
# Court / Growth domain templates
# ---------------------------------------------------------------------------

def court_allows_verdicts(verdicts: list[str]) -> list[LabAssertion]:
    """Assert that every given verdict label appears in the court verdict list.

    Returns one ``contains`` assertion per verdict label.
    """
    return [
        LabAssertion(
            assertion_type=LabAssertionType.contains,
            target=LabTarget.court,
            field_path="verdict",
            expected=v,
        )
        for v in verdicts
    ]


def court_forbids_verdicts(verdicts: list[str]) -> list[LabAssertion]:
    """Assert that none of the given verdict labels appear in the court verdict list.

    Returns one ``not_contains`` assertion per verdict label.
    """
    return [
        LabAssertion(
            assertion_type=LabAssertionType.not_contains,
            target=LabTarget.court,
            field_path="verdict",
            expected=v,
        )
        for v in verdicts
    ]


def negative_emotion_must_not_plant() -> list[LabAssertion]:
    """Negative self-narratives must be blocked from becoming stable identity traits.

    Covers both court blocking and safety escalation paths.
    """
    return [
        LabAssertion(
            assertion_type=LabAssertionType.is_false,
            target=LabTarget.court,
            field_path="allow_plant_as_stable_identity_trait",
            expected=None,
        ),
        LabAssertion(
            assertion_type=LabAssertionType.contains,
            target=LabTarget.court,
            field_path="safety_escalations",
            expected="defer_identity_planting",
        ),
    ]


# ---------------------------------------------------------------------------
# Harvest domain templates
# ---------------------------------------------------------------------------

def greenhouse_must_not_enter_positive_brief() -> list[LabAssertion]:
    """Greenhouse / sensitive items must not leak into positive brief output.

    ``greenhouse_leak_count`` is an integer counter; asserted as ``equals 0``.
    """
    return [
        LabAssertion(
            assertion_type=LabAssertionType.equals,
            target=LabTarget.harvest,
            field_path="greenhouse_leak_count",
            expected=0,
        ),
        LabAssertion(
            assertion_type=LabAssertionType.field_absent,
            target=LabTarget.harvest,
            field_path="greenhouse_leaked_to_brief",
            expected=None,
        ),
    ]


def brief_requires_source_ids(max_count: int = 32) -> list[LabAssertion]:
    """Brief must include traceable source memory IDs, and must stay within limit."""
    return [
        LabAssertion(
            assertion_type=LabAssertionType.field_present,
            target=LabTarget.harvest,
            field_path="source_memory_ids",
            expected=None,
        ),
        LabAssertion(
            assertion_type=LabAssertionType.count_at_most,
            target=LabTarget.harvest,
            field_path="source_memory_ids",
            expected=max_count,
        ),
    ]


def brief_must_not_expose_full_memory_text() -> list[LabAssertion]:
    """Brief must not embed complete MemoryCard plaintext or dump full card bodies."""
    return [
        LabAssertion(
            assertion_type=LabAssertionType.is_false,
            target=LabTarget.harvest,
            field_path="brief_embeds_complete_memory_card_plaintext",
            expected=None,
        ),
        LabAssertion(
            assertion_type=LabAssertionType.field_absent,
            target=LabTarget.harvest,
            field_path="serialised_full_cards_bodies_dump",
            expected=None,
        ),
    ]


# ---------------------------------------------------------------------------
# Runtime domain templates
# ---------------------------------------------------------------------------

def command_must_short_circuit() -> list[LabAssertion]:
    """Control commands must short-circuit: handled=True, no after_reply, no agent."""
    return [
        LabAssertion(
            assertion_type=LabAssertionType.is_true,
            target=LabTarget.runtime,
            field_path="command_handled",
            expected=None,
        ),
        LabAssertion(
            assertion_type=LabAssertionType.is_false,
            target=LabTarget.runtime,
            field_path="after_reply_called",
            expected=None,
        ),
        LabAssertion(
            assertion_type=LabAssertionType.is_false,
            target=LabTarget.runtime,
            field_path="agent_called",
            expected=None,
        ),
    ]


# ---------------------------------------------------------------------------
# Observatory domain templates
# ---------------------------------------------------------------------------

def observatory_public_must_redact_long_text() -> list[LabAssertion]:
    """PUBLIC observation view must not expose entire user message or assistant reply."""
    return [
        LabAssertion(
            assertion_type=LabAssertionType.is_false,
            target=LabTarget.observatory,
            field_path="public_sections_include_entire_user_message",
            expected=None,
        ),
        LabAssertion(
            assertion_type=LabAssertionType.is_false,
            target=LabTarget.observatory,
            field_path="public_sections_include_entire_assistant_reply",
            expected=None,
        ),
    ]


def hard_forget_must_not_leak_text() -> list[LabAssertion]:
    """Hard-forgotten text must not leak into any observatory view.

    ``hard_forgotten_text_leak_count`` is an integer counter; asserted as ``equals 0``.
    Never carries real sensitive text.
    """
    return [
        LabAssertion(
            assertion_type=LabAssertionType.equals,
            target=LabTarget.observatory,
            field_path="hard_forgotten_text_leak_count",
            expected=0,
        ),
    ]


__all__ = [
    "assistant_reply_must_not_be_user_memory",
    "brief_must_not_expose_full_memory_text",
    "brief_requires_source_ids",
    "command_must_short_circuit",
    "court_allows_verdicts",
    "court_forbids_verdicts",
    "greenhouse_must_not_enter_positive_brief",
    "hard_forget_must_not_leak_text",
    "negative_emotion_must_not_plant",
    "observatory_public_must_redact_long_text",
    "seed_forbids_control_command_memory",
    "seed_min_count",
]