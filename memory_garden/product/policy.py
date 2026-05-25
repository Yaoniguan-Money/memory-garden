"""产品级记忆策略与 provider 调用门禁。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.core.models import SensitivityLevel
from memory_garden.product.models import MemoryProposal, VisibilityScope
from memory_garden.providers.base import ProviderCallContext
from memory_garden.providers.config import ProviderPolicy
from memory_garden.providers.errors import ProviderPolicyError


SENSITIVE_TERMS = (
    "password",
    "api key",
    "token",
    "secret",
    "ssn",
    "social security",
    "credit card",
    "bank account",
    "diagnosis",
    "medical",
    "passport",
)


class MemoryPolicy(BaseModel):
    """Storage, retrieval, model visibility, export, and provider policy."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    write_mode: str = Field(default="trusted", description="manual, trusted, or auto")
    allow_sensitive_storage: bool = False
    allow_model_visibility_for_sensitive: bool = False
    allow_export_sensitive: bool = False
    require_confirmation_for_sensitive: bool = True
    require_confirmation_for_identity: bool = True
    provider_policy: ProviderPolicy = Field(default_factory=ProviderPolicy)

    def classify_sensitivity(self, text: str) -> tuple[SensitivityLevel, list[str]]:
        lower = text.casefold()
        flags = [term for term in SENSITIVE_TERMS if term in lower]
        if flags:
            return SensitivityLevel.high, [f"sensitive_term:{flag}" for flag in flags]
        return SensitivityLevel.none, []

    def apply_to_proposal(self, proposal: MemoryProposal) -> MemoryProposal:
        sensitivity, flags = self.classify_sensitivity(
            "\n".join([proposal.title, proposal.essence, proposal.evidence])
        )
        risk_flags = list(dict.fromkeys([*proposal.risk_flags, *flags]))
        new_sensitivity = proposal.sensitivity
        if sensitivity == SensitivityLevel.high:
            new_sensitivity = SensitivityLevel.high
        requires_confirmation = proposal.requires_confirmation
        if new_sensitivity in (SensitivityLevel.medium, SensitivityLevel.high):
            requires_confirmation = self.require_confirmation_for_sensitive
        if "identity" in proposal.tags or proposal.memory_type.value == "identity":
            requires_confirmation = self.require_confirmation_for_identity
        if new_sensitivity == SensitivityLevel.high and not self.allow_sensitive_storage:
            requires_confirmation = True
            risk_flags.append("policy_requires_sensitive_review")
        return proposal.model_copy(
            update={
                "sensitivity": new_sensitivity,
                "risk_flags": risk_flags,
                "requires_confirmation": requires_confirmation,
            }
        )

    def allows_visibility(self, proposal_or_sensitivity: MemoryProposal | SensitivityLevel, scope: VisibilityScope) -> bool:
        sensitivity = (
            proposal_or_sensitivity.sensitivity
            if isinstance(proposal_or_sensitivity, MemoryProposal)
            else proposal_or_sensitivity
        )
        if sensitivity not in (SensitivityLevel.medium, SensitivityLevel.high):
            return True
        if scope == VisibilityScope.model:
            return self.allow_model_visibility_for_sensitive
        if scope == VisibilityScope.export:
            return self.allow_export_sensitive
        return True

    def assert_provider_call_allowed(self, context: ProviderCallContext, text: str) -> None:
        if len(text) > self.provider_policy.max_chars_per_call:
            raise ProviderPolicyError("Provider 调用被阻止：文本超过 ProviderPolicy.max_chars_per_call")
        sensitivity, flags = self.classify_sensitivity(text)
        if flags and not self.provider_policy.allow_sensitive_text:
            raise ProviderPolicyError("Provider 调用被阻止：文本可能包含敏感信息")
        if text and not self.provider_policy.allow_raw_user_text:
            raise ProviderPolicyError("Provider 调用被阻止：策略未允许发送用户原文")
        provider_kind = context.provider_kind or "llm"
        if context.allow_remote and not self.provider_policy.allows_remote(provider_kind):
            raise ProviderPolicyError(f"远程 {provider_kind} provider 调用被策略阻止")
        if sensitivity == SensitivityLevel.high and not self.provider_policy.allow_sensitive_text:
            raise ProviderPolicyError("敏感文本不能发送给 provider")
