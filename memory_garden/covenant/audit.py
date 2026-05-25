"""Garden Covenant in-memory audit helpers."""

from __future__ import annotations

import hashlib
import json

from memory_garden.covenant.decisions import PolicyDecision
from memory_garden.covenant.models import GardenCovenant


def covenant_hash(covenant: GardenCovenant) -> str:
    """Return a stable hash for a covenant."""
    payload = covenant.model_dump(mode="json")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class CovenantAudit:
    """In-memory policy decision audit log."""

    def __init__(self, max_recent_decisions: int = 50):
        if max_recent_decisions < 1:
            raise ValueError("max_recent_decisions must be >= 1")
        self.max_recent_decisions = max_recent_decisions
        self._decisions: list[PolicyDecision] = []

    def record_decision(self, decision: PolicyDecision) -> None:
        self._decisions.append(decision)
        if len(self._decisions) > self.max_recent_decisions:
            self._decisions = self._decisions[-self.max_recent_decisions :]

    def list_recent_decisions(self, limit: int = 50) -> list[PolicyDecision]:
        if limit < 1:
            return []
        return list(self._decisions[-limit:])

    def covenant_hash(self, covenant: GardenCovenant) -> str:
        return covenant_hash(covenant)

    def inspect(self, covenant: GardenCovenant | None = None) -> dict:
        blocked = [d for d in self._decisions if not d.allowed]
        critical = [d for d in self._decisions if d.severity.value == "critical"]
        payload = {
            "recent_decision_count": len(self._decisions),
            "blocked_decision_count": len(blocked),
            "critical_decision_count": len(critical),
            "recent_policy_names": [d.policy_name for d in self._decisions[-10:]],
        }
        if covenant is not None:
            payload["covenant_hash"] = covenant_hash(covenant)
            payload["covenant_version"] = covenant.version
        return payload


__all__ = ["CovenantAudit", "covenant_hash"]
