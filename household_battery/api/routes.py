from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import logging
import os

from .models import DeterministicRequest, ChampionRequest
from .service import run_dayahead_deterministic, run_dayahead_champion
from .errors import DataValidationError

CHAMPION_POLICY_PATH = "./artifacts/champion.json"

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/dayahead/deterministic")
def dayahead_deterministic(req: DeterministicRequest):
    try:
        df = run_dayahead_deterministic(
            batteries_specs=[b.model_dump() for b in req.batteries],
            forecasts_csv_text=req.forecasts_csv,
            timestep_hours=req.timestep_hours,
        )
        return JSONResponse(content={"schedule": df.to_dict(orient="records")})
    except DataValidationError as e:
        # Data/format validation errors should be returned to the client
        logger.info("Deterministic scheduling validation error: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log internally at info level without stack trace leakage to clients
        logger.info("Deterministic scheduling failed: %s", str(e))
        raise HTTPException(
            status_code=400,
            detail="Invalid request or scheduling failed. Please verify inputs.",
        )


@router.post("/dayahead/stochastic")
def dayahead_stochastic(req: ChampionRequest):
    try:
        df = run_dayahead_champion(
            batteries_specs=[b.model_dump() for b in req.batteries],
            history_csv_text=req.history_csv,
            ahead_prices_csv_text=req.ahead_prices_csv,
            policy_override=(
                req.policy_override.model_dump() if req.policy_override else None
            ),
            champion_path=CHAMPION_POLICY_PATH,
            timestep_hours=req.timestep_hours,
        )
        return JSONResponse(content={"schedule": df.to_dict(orient="records")})
    except DataValidationError as e:
        logger.info("Stochastic scheduling validation error: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        logger.info("Champion policy file missing")
        raise HTTPException(
            status_code=503, detail="Champion policy is not configured on the server."
        )
    except Exception as e:
        logger.info("Stochastic scheduling failed: %s", str(e))
        raise HTTPException(
            status_code=400,
            detail="Invalid request or scheduling failed. Please verify inputs and champion policy.",
        )


@router.get("/health")
def health():
    """Basic health and solver availability check."""
    try:
        from esms import get_available_pyomo_solvers, __version__

        solvers = get_available_pyomo_solvers()
        champion_exists = os.path.exists(CHAMPION_POLICY_PATH)
        status = {
            "service": "Household Day-Ahead Scheduling API",
            "esms_version": __version__,
            "status": "Healthy" if (solvers and champion_exists) else "Degraded",
            "available_solvers": solvers,
            "champion_policy": {
                "exists": champion_exists,
            },
        }
        return JSONResponse(content=status)
    except Exception:
        return JSONResponse(content={"status": "Unhealthy"}, status_code=500)
