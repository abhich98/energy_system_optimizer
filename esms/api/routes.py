"""FastAPI routes for EsMS optimization service."""

import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import io

from esms import __version__
from esms.services.io_service import IOService
from esms.services.optimization_service import OptimizationService
from esms import get_available_pyomo_solvers, SUGGESTED_SOLVERS

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Status information
    """
    available_solvers = get_available_pyomo_solvers()
    status = {
        "service": "EsMS Energy Optimization API",
        "version": __version__,
    }
    if not available_solvers:
        status["status"] = "Unhealthy"
        status["error"] = (
            f"No available solvers found. Please install at least one of the following solvers: {SUGGESTED_SOLVERS}"
        )
    else:
        status["status"] = "Healthy"
        status["available_solvers"] = available_solvers

    return status


@router.post("/optimize")
async def optimize(
    batteries_json: UploadFile = File(
        ..., description="Battery configuration JSON file"
    ),
    forecasts_csv: UploadFile = File(..., description="Forecast data CSV file"),
    fix_decision_vars_csv: Optional[UploadFile] = File(
        None, description="Optional fixed decision variables CSV file"
    ),
    config_json: Optional[UploadFile] = File(
        None, description="Optional solver configuration JSON file"
    ),
):
    """
    Run energy optimization with uploaded files.

    Required files:
    - batteries_json: Array of battery configurations
    - forecasts_csv: Time series with pv, load, price columns

    Optional files:
    - fix_decision_vars_csv: Fixed decision variables CSV file
    - config_json: Solver configuration (defaults to SCIP LP)

    Returns:
        CSV file with optimization schedule
    """
    logger.info("Received optimization request")

    try:
        # Parse batteries
        logger.info("Parsing batteries.json...")
        batteries_content = await batteries_json.read()
        batteries = IOService.parse_batteries_json(batteries_content)
        logger.info(f"Parsed {len(batteries)} batteries")

        # Parse forecasts
        logger.info("Parsing forecasts.csv...")
        forecasts_content = await forecasts_csv.read()
        forecasts = IOService.parse_forecasts_csv(forecasts_content)
        logger.info(f"Parsed {len(forecasts['pv'])} timesteps")

        # Parse fixed decision variables (optional)
        logger.info("Parsing fix_decision_vars.csv...")
        fix_decision_vars_content = (
            await fix_decision_vars_csv.read() if fix_decision_vars_csv else None
        )
        fix_decision_vars = IOService.parse_fix_decision_vars_csv(
            fix_decision_vars_content, [b.id for b in batteries]
        )
        logger.info(
            f"Parsed fixed decision variables: {list(fix_decision_vars.keys())}"
        )

        # Parse config (optional)
        logger.info("Parsing config.json...")
        config_content = await config_json.read() if config_json else None
        config = IOService.parse_config_json(config_content)
        logger.info(f"Configuration: solver={config.solver}")

        # Run optimization
        logger.info("Running optimization...")
        results_df = OptimizationService.optimize(
            batteries,
            forecasts,
            fix_decision_vars,
            config,
        )

        # Convert to CSV
        csv_content = IOService.results_to_csv(results_df)

        logger.info("Optimization completed successfully")

        # Return CSV as streaming response
        return StreamingResponse(
            io.BytesIO(csv_content.encode("utf-8")),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=optimization_schedule.csv"
            },
        )

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except RuntimeError as e:
        logger.error(f"Optimization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@router.post("/stochastic-optimize")
async def stochastic_optimize(
    batteries_json: UploadFile = File(
        ..., description="Battery configuration JSON file"
    ),
    scenarios_csv: UploadFile = File(
        ...,
        description=(
            "Scenario CSV with timestamp/Date, scenario, probability, pv, load, "
            "import_price_rt, and optional export_price_rt"
        ),
    ),
    ahead_prices_csv: UploadFile = File(
        ...,
        description=(
            "Ahead-price CSV with timestamp/Date, import_price_ahead, and optional export_price_ahead"
        ),
    ),
    schedule_bess: bool = File(
        False,
        description="Whether to include BESS scheduling in the optimization (default: false)",
    ),
    config_json: Optional[UploadFile] = File(
        None, description="Optional solver configuration JSON file"
    ),
):
    """Run stochastic optimization with explicit scenario inputs and return expected results as CSV."""
    logger.info("Received stochastic optimization request")

    try:
        logger.info("Parsing batteries.json...")
        batteries_content = await batteries_json.read()
        batteries = IOService.parse_batteries_json(batteries_content)
        logger.info("Parsed %s batteries", len(batteries))

        logger.info("Parsing scenarios.csv...")
        scenarios_content = await scenarios_csv.read()
        scenarios = IOService.parse_stochastic_scenarios_csv(scenarios_content)
        logger.info(
            "Parsed %s scenarios with %s timesteps each",
            scenarios["load_scenarios"].shape[0],
            scenarios["load_scenarios"].shape[1],
        )

        logger.info("Parsing ahead_prices.csv...")
        ahead_prices_content = await ahead_prices_csv.read()
        ahead_prices = IOService.parse_ahead_prices_csv(
            ahead_prices_content,
            expected_timestamps=scenarios["timestamps"],
        )
        logger.info(
            "Parsed %s ahead timesteps", len(ahead_prices["import_price_ahead"])
        )

        logger.info("Parsing config.json...")
        config_content = await config_json.read() if config_json else None
        config = IOService.parse_config_json(config_content)
        logger.info("Configuration: solver=%s", config.solver)

        logger.info("Running stochastic optimization...")
        results_df = OptimizationService.optimize_stochastic(
            batteries=batteries,
            scenarios=scenarios,
            ahead_prices=ahead_prices,
            schedule_bess=schedule_bess,
            config=config,
        )

        csv_content = IOService.results_to_csv(results_df)

        logger.info("Stochastic optimization completed successfully")

        return StreamingResponse(
            io.BytesIO(csv_content.encode("utf-8")),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=stochastic_optimization_schedule.csv"
            },
        )

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except RuntimeError as e:
        logger.error(f"Optimization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")
