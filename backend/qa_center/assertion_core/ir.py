from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class AssertionIR:
    type: str
    operator: str = "eq"
    expected: Any = None
    scope: str = ""
    path: str = ""
    provider: str = ""
    source: str = "explicit"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssertionResultIR:
    type: str
    operator: str = "eq"
    expected: Any = None
    actual: Any = None
    passed: bool = False
    scope: str = ""
    provider: str = ""
    source: str = "explicit"
    metadata: Dict[str, Any] = field(default_factory=dict)
