"""Covenant Enforcer: bridge PolicyEngine decisions to garden operations.

This module provides ``CovenantEnforcer``, which wraps key garden
operations with policy checks.  It does **not** modify frozen layers
(Core, Runtime, Harvest) — it sits *around* them, checking policy
before delegating.

Pattern: same as Soil forget wrapping Core forget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from memory_garden.covenant.decisions import PolicyDecision, PolicySeverity
from memory_garden.covenant.engine import PolicyEngine
from memory_garden.covenant.models import GardenCovenant


@dataclass
class EnforcementResult:
    """Result of a single enforcement check."""

    allowed: bool
    policy_name: str = ""
    action: str = ""
    reason: str = ""
    severity: PolicySeverity = PolicySeverity.info
    matched_rules: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_decision(cls, d: PolicyDecision) -> "EnforcementResult":
        return cls(
            allowed=d.allowed,
            policy_name=d.policy_name,
            action=d.action,
            reason=d.reason,
            severity=d.severity,
            matched_rules=list(d.matched_rules),
            metadata=dict(d.metadata),
        )

    @classmethod
    def deny(cls, reason: str, *, policy_name: str = "", action: str = "") -> "EnforcementResult":
        return cls(allowed=False, reason=reason, policy_name=policy_name, action=action,
                   severity=PolicySeverity.critical)

    @classmethod
    def allow(cls, reason: str = "Default allow") -> "EnforcementResult":
        return cls(allowed=True, reason=reason)


class CovenantEnforcer:
    """Policy enforcement wrapper for garden operations.

    Usage::

        covenant = default_covenant()
        enforcer = CovenantEnforcer(covenant)

        # Before harvesting a memory
        result = enforcer.before_harvest(memory_card, purpose="brief")
        if not result.allowed:
            ...  # skip this memory

        # Before exporting
        result = enforcer.before_export(record, export_mode="bundle")
        if not result.allowed:
            raise ExportBlockedError(result.reason)
    """

    def __init__(self, covenant: GardenCovenant | None = None) -> None:
        if covenant is None:
            from memory_garden.covenant.defaults import default_garden_covenant
            covenant = default_garden_covenant()
        self._engine = PolicyEngine(covenant)

    @property
    def engine(self) -> PolicyEngine:
        return self._engine

    # ── Harvest checkpoints ─────────────────────────────────────────

    def before_harvest(self, memory: Any, *, purpose: str = "brief") -> EnforcementResult:
        """Check whether *memory* can be harvested for *purpose*.

        Call this before including a MemoryCard in a Garden Brief.
        """
        d = self._engine.can_harvest_memory(memory, purpose=purpose)
        return EnforcementResult.from_decision(d)

    def before_harvest_batch(
        self, memories: list[Any], *, purpose: str = "brief"
    ) -> tuple[list[Any], list[EnforcementResult]]:
        """Filter a list of memories, returning (allowed, denied_results)."""
        allowed: list[Any] = []
        denied: list[EnforcementResult] = []
        for m in memories:
            r = self.before_harvest(m, purpose=purpose)
            if r.allowed:
                allowed.append(m)
            else:
                denied.append(r)
        return allowed, denied

    # ── Model call checkpoints ──────────────────────────────────────

    def before_model_call(
        self, payload: Any, *, purpose: str, model_provider: str | None = None
    ) -> EnforcementResult:
        """Check whether *payload* can be sent to an external model."""
        d = self._engine.can_send_to_model(payload, purpose=purpose, model_provider=model_provider)
        return EnforcementResult.from_decision(d)

    # ── Display / Observatory checkpoints ───────────────────────────

    def before_display(
        self, memory: Any, *, surface: str = "report", debug: bool = False
    ) -> EnforcementResult:
        """Check whether *memory* can be displayed on *surface*."""
        d = self._engine.can_display_memory(memory, surface=surface, debug=debug)
        return EnforcementResult.from_decision(d)

    def before_display_batch(
        self, memories: list[Any], *, surface: str = "report", debug: bool = False
    ) -> tuple[list[Any], list[EnforcementResult]]:
        """Filter displayable memories."""
        allowed: list[Any] = []
        denied: list[EnforcementResult] = []
        for m in memories:
            r = self.before_display(m, surface=surface, debug=debug)
            if r.allowed:
                allowed.append(m)
            else:
                denied.append(r)
        return allowed, denied

    # ── Export checkpoints ──────────────────────────────────────────

    def before_export(self, record: Any, *, export_mode: str = "bundle") -> EnforcementResult:
        """Check whether *record* can be exported."""
        d = self._engine.can_export_record(record, export_mode=export_mode)
        return EnforcementResult.from_decision(d)

    # ── Forget checkpoints ──────────────────────────────────────────

    def before_hard_forget(self, target: Any) -> EnforcementResult:
        """Check whether *target* can be hard-forgotten."""
        d = self._engine.can_hard_forget(target)
        return EnforcementResult.from_decision(d)

    # ── Seed admission checkpoints ──────────────────────────────────

    def before_admit_seed(self, seed: Any, *, context: dict[str, Any] | None = None) -> EnforcementResult:
        """Check whether *seed* can be admitted to the garden."""
        d = self._engine.can_admit_seed(seed, context=context)
        return EnforcementResult.from_decision(d)

    def check_negative_identity(self, text: str) -> EnforcementResult:
        """Check whether *text* contains negative self-description."""
        d = self._engine.should_prevent_negative_identity_lock(text)
        return EnforcementResult.from_decision(d)

    def route_sensitive(self, seed_or_memory: Any) -> EnforcementResult:
        """Determine routing for potentially sensitive content."""
        d = self._engine.route_sensitive_memory(seed_or_memory)
        return EnforcementResult.from_decision(d)

    # ── Command checkpoints ─────────────────────────────────────────

    def is_control_command(self, text: str) -> EnforcementResult:
        """Check whether *text* is a control command (花花开/花花关)."""
        open_d = self._engine.is_open_command(text)
        if open_d.allowed:
            return EnforcementResult.from_decision(open_d)
        close_d = self._engine.is_close_command(text)
        if close_d.allowed:
            return EnforcementResult.from_decision(close_d)
        return EnforcementResult.allow("Not a control command")

    def should_memorize(self, text: str) -> EnforcementResult:
        """Check whether *text* should be memorized (control commands must not)."""
        d = self._engine.should_memorize_command(text)
        return EnforcementResult.from_decision(d)

    # ── Brief writing checkpoints ───────────────────────────────────

    def before_write_brief_instruction(
        self, instruction: str, source_memory_ids: list[str]
    ) -> EnforcementResult:
        """Check whether a brief instruction has sufficient source support."""
        d = self._engine.can_write_brief_instruction(instruction, source_memory_ids)
        return EnforcementResult.from_decision(d)
