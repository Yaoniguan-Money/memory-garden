"""记忆法庭：判决模型、规则引擎与角色论述。"""

from memory_garden.core.court.case import RuleOutcome, build_court_case
from memory_garden.core.court.engine import MemoryCourtEngine, evaluate_rules
from memory_garden.core.court.interfaces import MemoryCourtEngineProtocol
from memory_garden.core.court.roles import triangulate_arguments
from memory_garden.core.court.verdict import CourtVerdict, CourtVerdictType

__all__ = [
    "CourtVerdict",
    "CourtVerdictType",
    "MemoryCourtEngine",
    "MemoryCourtEngineProtocol",
    "RuleOutcome",
    "build_court_case",
    "evaluate_rules",
    "triangulate_arguments",
]
