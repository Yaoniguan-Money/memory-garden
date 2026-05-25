"""Forget workflow service for the product facade."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from memory_garden.product.models import ForgetPlanRecord, ForgetProofRecord, utc_now
from memory_garden.product.storage import ProductMemoryStore
from memory_garden.soil.content_probes import build_content_probes_from_db, probe_safe_dump
from memory_garden.soil.forget import execute_hard_forget, plan_hard_forget
from memory_garden.soil.forget_proof import prove_forget as prove_hard_forget


class ForgetService:
    """Internal implementation behind ProductMemorySystem forget facades."""

    def __init__(
        self,
        *,
        garden_home: str | Path,
        store: ProductMemoryStore,
        resolve_memory_id: Callable[[str], str | None],
        logger: logging.Logger | None = None,
    ) -> None:
        self.garden_home = Path(garden_home)
        self.store = store
        self.resolve_memory_id = resolve_memory_id
        self.logger = logger or logging.getLogger(__name__)

    def plan_forget(
        self,
        target: str = "",
        *,
        memory_id: str | None = None,
        cascade: bool = True,
    ) -> ForgetPlanRecord:
        resolved = memory_id or self.resolve_memory_id(target)
        if not resolved:
            raise LookupError("No matching memory found")
        plan = plan_hard_forget(self.garden_home, resolved)
        affected = {k: list(v) for k, v in plan.affected_entities.items()}
        affected.setdefault("proposal", [p.id for p in self.store.proposals_for_memory(resolved)])
        probes = plan.content_probes
        record = ForgetPlanRecord(
            memory_id=resolved,
            target=target,
            cascade=cascade,
            affected=affected,
            risks=[] if cascade else ["Related audit records may remain because cascade is disabled"],
            content_probe_fingerprint=probes.probe_fingerprint if probes is not None else "",
            content_probes_safe=probe_safe_dump(probes) if probes is not None else {},
        )
        return self.store.save_forget_plan(record)

    def execute_forget(self, plan_id: str) -> tuple[ForgetPlanRecord, ForgetProofRecord]:
        plan = self.store.get_forget_plan(plan_id)
        content_probes = build_content_probes_from_db(self.garden_home, plan.memory_id)
        result = execute_hard_forget(
            self.garden_home,
            plan.memory_id,
            reason=f"product forget plan {plan.id}",
            dry_run=False,
            cascade=plan.cascade,
        )
        if result.status == "ok":
            cleaned = self.store.delete_memory_products(plan.memory_id)
            purged = self.store.purge_retrieval_events_for_memory(plan.memory_id)
            if purged:
                cleaned.append(f"memory_retrieval_events.purged={purged}")
            if cleaned:
                self.logger.debug("cleaned product records for %s: %s", plan.memory_id, cleaned)
        proof = self.prove_forget(
            plan.memory_id,
            plan_id=plan.id,
            content_probes=content_probes,
            cascade=plan.cascade,
        )
        executed = plan.model_copy(
            update={
                "status": "executed" if result.status == "ok" else result.status,
                "executed_at": utc_now(),
                "result": result.model_dump(mode="json"),
                "content_probe_fingerprint": result.content_probe_fingerprint or plan.content_probe_fingerprint,
            }
        )
        self.store.save_forget_plan(executed)
        return executed, proof

    def prove_forget(
        self,
        memory_id: str,
        *,
        plan_id: str = "",
        content_probes: Any = None,
        cascade: bool | None = None,
    ) -> ForgetProofRecord:
        if cascade is None and plan_id:
            try:
                cascade = self.store.get_forget_plan(plan_id).cascade
            except KeyError:
                cascade = None
        proof = prove_hard_forget(
            self.garden_home,
            memory_id,
            content_probes=content_probes,
            cascade=cascade,
        )
        record = ForgetProofRecord(
            plan_id=plan_id,
            memory_id=memory_id,
            proven=proof.proven,
            checks=[check.model_dump(mode="json") for check in proof.checks],
            metadata=_redact_proof_metadata(proof, content_probes),
            content_probe_fingerprint=proof.content_probe_fingerprint,
            proof_level=proof.proof_level,
        )
        return self.store.save_forget_proof(record)


def _redact_proof_metadata(proof: Any, content_probes: Any) -> dict[str, Any]:
    """Persist ForgetProof metadata without probe plaintext."""
    payload = proof.model_dump(mode="json")
    if content_probes is not None:
        payload["content_probes_safe"] = probe_safe_dump(content_probes)
    checks = payload.get("checks", [])
    for check in checks:
        evidence = check.get("evidence", {})
        if isinstance(evidence, dict) and "queries" in evidence:
            evidence.pop("queries", None)
    payload["checks"] = checks
    return payload
