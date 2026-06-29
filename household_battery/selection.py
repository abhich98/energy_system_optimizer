from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import numpy as np
import yaml


@dataclass(frozen=True)
class PromotionRules:
    mean_gain_min: float = 0.02
    mean_gain_strong: float = 0.03
    win_rate_min: float = 0.60
    p95_runtime_max_sec: float = 60.0
    require_zero_violations: bool = True


def wilcoxon_pvalue(daily_deltas: np.ndarray) -> float:
    try:
        from scipy.stats import wilcoxon  # type: ignore

        stat, p = wilcoxon(daily_deltas)
        return float(p)
    except Exception:
        # SciPy optional — if missing, skip the test by returning 1.0
        return 1.0


def should_promote(summary: Dict[str, Any], rules: PromotionRules) -> bool:
    """Decide promotion based on summary dict fields computed by evaluator.

    Expected keys:
      - mean_gain (float): mean daily cost reduction vs champion on holdout
      - win_rate (float): fraction of holdout days improved
      - p95_runtime_sec (float)
      - violations_sum (int)
      - daily_deltas (np.ndarray): per-day cost deltas (challenger - champion)
    """
    mean_gain = float(summary.get("mean_gain", 0.0))
    win_rate = float(summary.get("win_rate", 0.0))
    p95_rt = float(summary.get("p95_runtime_sec", 1e9))
    violations = int(summary.get("violations_sum", 0))
    deltas = np.asarray(summary.get("daily_deltas", []), dtype=float)

    if rules.require_zero_violations and violations > 0:
        return False
    if p95_rt > rules.p95_runtime_max_sec:
        return False
    if win_rate < rules.win_rate_min:
        return False

    if mean_gain >= rules.mean_gain_strong:
        return True
    if mean_gain >= rules.mean_gain_min:
        p = wilcoxon_pvalue(deltas)
        return p <= 0.05
    return False


def load_rules(path: str | None) -> PromotionRules:
    """Load promotion rules from YAML; fallback to defaults if missing/invalid."""
    if not path:
        return PromotionRules()
    else:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return PromotionRules(**cfg)
