# Why a Covenant Layer?

The Garden Covenant (Layer 8) is a dedicated memory policy and trust layer. Why is policy a separate layer rather than configuration in Core or Runtime?

## Policy Was Already Implicit

Before the Covenant, memory policy was scattered:

- Core's greenhouse logic encoded "sensitive content should be isolated."
- Harvest's bouquet builder encoded "greenhouse cards should not be in PRIMARY."
- Observatory's redaction encoded "PUBLIC views should not show full text."
- Runtime's command parser encoded "control commands are never observed."

These rules were correct but invisible. A new contributor would need to read six files across four layers to understand the full safety posture.

## Centralization Benefits

The Covenant collects all policy rules in one place:

- **Visibility**: One YAML file shows the complete policy.
- **Validation**: Unsafe configurations are rejected at load time, not discovered at runtime.
- **Auditability**: Every policy decision returns a structured `PolicyDecision` with a reason.
- **Non-overridable baselines**: Some rules (hard forget means invisible, API keys are never exported) cannot be disabled by configuration.

## The Covenant Does Not Enforce

The Covenant is currently read-only. It answers policy questions. It does not automatically enforce them in Core, Runtime, or Harvest. Earlier layers continue to operate with their existing behavior.

Bridging the Covenant to enforcement points in earlier layers is a future design question. The current separation ensures the policy model can be discussed, audited, and stabilized before it becomes an enforcement mechanism.
