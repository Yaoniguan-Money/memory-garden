"""Garden Covenant exceptions."""

from __future__ import annotations


class CovenantError(ValueError):
    """Base class for covenant errors."""


class CovenantValidationError(CovenantError):
    """Raised when a covenant violates schema or hard baseline constraints."""

    def __init__(
        self,
        message: str,
        *,
        field_path: str | None = None,
        suggestion: str | None = None,
        violations: list["CovenantValidationError"] | None = None,
    ):
        super().__init__(message)
        self.field_path = field_path
        self.suggestion = suggestion
        self.violations = list(violations or [])


class CovenantLoaderError(CovenantError):
    """Raised when covenant loading fails."""


class CovenantViolation(CovenantError):
    """Raised when a critical covenant policy blocks an operation."""


__all__ = [
    "CovenantError",
    "CovenantLoaderError",
    "CovenantValidationError",
    "CovenantViolation",
]
