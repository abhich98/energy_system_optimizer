from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class PolicySpec:
    """Defines a stochastic policy recipe for day-ahead scheduling.

    Keep this use-case specific (household day-ahead), but avoid hard-coding
    anything that would block reuse.
    """

    id: str
    history_days: int
    num_scenarios: int
    pv_coeff: float = 0.5
    load_coeff: float = 0.5
    solver: str = "scip"
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


CHAMPION_ALIAS = "champion"


def save_champion_local(spec: PolicySpec, path: str) -> None:
    import json

    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec.to_dict(), f, indent=2)


def load_champion_local(path: str) -> PolicySpec:
    import json

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return PolicySpec(**data)
