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
    mip_gap: Optional[float] = None # solver option
    time_limit: Optional[int] = None  # seconds, per solve
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


@DeprecationWarning
def wandb_save_champion(spec: PolicySpec, artifact_name: str = "policy_spec") -> None:
    try:
        import wandb  # type: ignore

        run = wandb.run or wandb.init(project="dayahead-battery-scheduling-champion", settings=wandb.Settings(_disable_stats=True))
        art = wandb.Artifact(artifact_name, type="policy")
        import io, json

        buf = io.BytesIO(json.dumps(spec.to_dict(), indent=2).encode("utf-8"))
        art.add_file(local_path=None, name="policy.json", file=buf)
        run.log_artifact(art, aliases=[CHAMPION_ALIAS])
    except Exception:
        # Optional dependency or offline mode
        pass
