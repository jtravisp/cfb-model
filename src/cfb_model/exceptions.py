"""Custom exceptions for the cfb-model research pipeline (SPEC-phase2 §9)."""

from cfb.errors import CfbError


class SourceNotInCrosswalkError(CfbError):
    """Raised when looking up an undeclared source in the crosswalk (SPEC-phase2 §3.4)."""


class LeakageError(CfbError):
    """Raised when feature aggregation touches future or current-week data (SPEC-phase2 §9)."""
