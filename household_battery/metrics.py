from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import numpy as np
import pandas as pd


@dataclass
class DailyMetrics:
    date: pd.Timestamp
    total_cost: float
    net_energy_cost: float
    degradation_cost: float
    self_consumption: float
    self_sufficiency: float
    grid_dependency: float
    runtime_sec: float
    violations: int


def aggregate_metrics(rows: list[DailyMetrics]) -> Dict[str, Any]:
    frame = pd.DataFrame([r.__dict__ for r in rows])
    return {
        "days": int(frame.shape[0]),
        "mean_total_cost": float(frame.total_cost.mean()),
        "p95_runtime_sec": (
            float(np.percentile(frame.runtime_sec, 95)) if len(frame) else 0.0
        ),
        "violations_sum": int(frame.violations.sum()),
        "win_rate_vs_champion": None,  # to be filled by selection logic when comparing
    }
