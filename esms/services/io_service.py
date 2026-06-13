"""I/O service for parsing input files and formatting output."""

import json
import io
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from esms.api.schemas import SolverConfig
from esms.models import Battery

FORECASTS_CSV_REQUIRED_COLUMNS = ["pv", "load", "import_price"]
STOCHASTIC_SCENARIOS_CSV_REQUIRED_COLUMNS = ["scenario", "probability", "pv", "load"]
TIMESTAMP_COLUMN_CANDIDATES = ["timestamp", "Date"]
PRICE_RT_COLUMNS = ["import_price_rt", "export_price_rt"]
PRICE_AHEAD_COLUMNS = ["import_price_ahead", "export_price_ahead"]


class IOService:
    """Service for handling input/output operations."""

    @staticmethod
    def _resolve_first_existing_column(df: pd.DataFrame, candidates: List[str]) -> str:
        for candidate in candidates:
            if candidate in df.columns:
                return candidate
        raise ValueError(
            f"None of the candidate columns {candidates} found. Found columns: {list(df.columns)}"
        )

    @staticmethod
    def parse_batteries_json(content: bytes) -> List[Battery]:
        """
        Parse batteries JSON file.

        Args:
            content: JSON file content as bytes

        Returns:
            List of Battery objects

        Raises:
            ValueError: If JSON is invalid or validation fails
        """
        try:
            data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in batteries file: {e}")

        if not isinstance(data, list):
            raise ValueError("Batteries JSON must contain an array of battery objects")

        batteries = []
        for idx, battery_data in enumerate(data):
            try:
                # Validate and create Battery directly with Pydantic
                battery = Battery(**battery_data)
                batteries.append(battery)
            except Exception as e:
                raise ValueError(f"Error in battery {idx}: {e}")

        if not batteries:
            raise ValueError("No batteries found in batteries.json")

        return batteries

    @staticmethod
    def parse_forecasts_csv(content: bytes) -> Dict[str, Any]:
        """
        Parse forecasts CSV file.

        Expected columns: timestep, pv, load, import_price, export_price (optional)

        Args:
            content: CSV file content as bytes

        Returns:
            Dictionary with pv, load, import_price, export_price arrays

        Raises:
            ValueError: If CSV is invalid or required columns are missing
        """
        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception as e:
            raise ValueError(f"Invalid CSV in forecasts file: {e}")

        # Validate required columns
        required_columns = FORECASTS_CSV_REQUIRED_COLUMNS
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(
                f"Missing required columns in forecasts.csv: {missing_columns}. "
                f"Found columns: {list(df.columns)}"
            )

        # Extract data
        forecasts = {
            "pv": df["pv"].values,
            "load": df["load"].values,
            "import_price": df["import_price"].values,
        }

        # Optional export_price column
        if "export_price" in df.columns:
            forecasts["export_price"] = df["export_price"].values
        else:
            forecasts["export_price"] = None

        # Validate data
        n_timesteps = len(forecasts["pv"])
        if n_timesteps == 0:
            raise ValueError("Forecasts CSV is empty")

        for key, values in forecasts.items():
            if values is not None and len(values) != n_timesteps:
                raise ValueError(
                    f"All forecast columns must have the same length. "
                    f"pv has {n_timesteps}, {key} has {len(values)}"
                )

        return forecasts

    @staticmethod
    def parse_stochastic_scenarios_csv(content: bytes) -> Dict[str, Any]:
        """Parse explicit stochastic scenario input CSV.

        Expected columns:
        - timestamp or Date
        - scenario
        - probability
        - pv
        - load
        - import_price_rt
        - export_price_rt (optional)
        """
        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception as e:
            raise ValueError(f"Invalid CSV in scenarios file: {e}")

        missing_columns = [
            col
            for col in STOCHASTIC_SCENARIOS_CSV_REQUIRED_COLUMNS
            if col not in df.columns
        ]
        if missing_columns:
            raise ValueError(
                f"Missing required columns in scenarios.csv: {missing_columns}. "
                f"Found columns: {list(df.columns)}"
            )

        timestamp_col = IOService._resolve_first_existing_column(
            df, TIMESTAMP_COLUMN_CANDIDATES
        )
        import_price_rt_col, export_price_rt_col = PRICE_RT_COLUMNS

        df = df.copy()
        df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
        if df[timestamp_col].isna().any():
            raise ValueError("Invalid timestamps in scenarios.csv")

        df = df.sort_values(["scenario", timestamp_col]).reset_index(drop=True)

        scenario_ids = list(df["scenario"].drop_duplicates())
        if not scenario_ids:
            raise ValueError("No scenarios found in scenarios.csv")

        first_scenario = df[df["scenario"] == scenario_ids[0]].reset_index(drop=True)
        timestamps = pd.DatetimeIndex(first_scenario[timestamp_col])
        n_timesteps = len(first_scenario)
        if n_timesteps == 0:
            raise ValueError("Scenario CSV contains no timesteps")

        load_scenarios = []
        pv_scenarios = []
        import_price_rt_scenarios = []
        export_price_rt_scenarios = []
        probabilities = []

        for scenario_id in scenario_ids:
            scenario_df = df[df["scenario"] == scenario_id].reset_index(drop=True)
            if len(scenario_df) != n_timesteps:
                raise ValueError(
                    "All scenarios must contain the same number of timesteps. "
                    f"Scenario '{scenario_id}' has {len(scenario_df)}, expected {n_timesteps}."
                )

            scenario_timestamps = pd.DatetimeIndex(scenario_df[timestamp_col])
            if not scenario_timestamps.equals(timestamps):
                raise ValueError(
                    f"Scenario '{scenario_id}' timestamps do not match the first scenario."
                )

            # Assumed that probability is the same across all timesteps for a given scenario, so we take the first value
            probabilities.append(float(scenario_df["probability"].iloc[0]))
            load_scenarios.append(
                pd.to_numeric(scenario_df["load"], errors="coerce").to_numpy(
                    dtype=float
                )
            )
            pv_scenarios.append(
                pd.to_numeric(scenario_df["pv"], errors="coerce").to_numpy(dtype=float)
            )
            import_price_rt_scenarios.append(
                pd.to_numeric(
                    scenario_df[import_price_rt_col], errors="coerce"
                ).to_numpy(dtype=float)
            )

            if export_price_rt_col is None:
                export_price_rt_scenarios.append(np.zeros(n_timesteps, dtype=float))
            else:
                export_price_rt_scenarios.append(
                    pd.to_numeric(
                        scenario_df[export_price_rt_col], errors="coerce"
                    ).to_numpy(dtype=float)
                )

        probabilities_array = np.array(probabilities, dtype=float)
        if np.any(np.isnan(probabilities_array)):
            raise ValueError("Invalid scenario probabilities in scenarios.csv")
        if not np.isclose(probabilities_array.sum(), 1.0, atol=1e-6):
            raise ValueError(
                "Scenario probabilities must sum to 1.0. "
                f"Got {probabilities_array.sum():.6f}."
            )

        return {
            "timestamps": timestamps,
            "load_scenarios": np.array(load_scenarios, dtype=float),
            "pv_scenarios": np.array(pv_scenarios, dtype=float),
            "import_price_rt_scenarios": np.array(
                import_price_rt_scenarios, dtype=float
            ),
            "export_price_rt_scenarios": np.array(
                export_price_rt_scenarios, dtype=float
            ),
            "scenario_probabilities": probabilities_array,
            "scenario_ids": scenario_ids,
        }

    @staticmethod
    def parse_ahead_prices_csv(
        content: bytes,
        expected_timestamps: Optional[pd.DatetimeIndex] = None,
    ) -> Dict[str, Any]:
        """Parse ahead-price CSV aligned with explicit scenarios."""
        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception as e:
            raise ValueError(f"Invalid CSV in ahead prices file: {e}")

        timestamp_col = IOService._resolve_first_existing_column(
            df, TIMESTAMP_COLUMN_CANDIDATES
        )
        import_price_ahead_col, export_price_ahead_col = PRICE_AHEAD_COLUMNS

        df = df.copy()
        df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
        if df[timestamp_col].isna().any():
            raise ValueError("Invalid timestamps in ahead_prices.csv")

        df = df.sort_values(timestamp_col).reset_index(drop=True)
        timestamps = pd.DatetimeIndex(df[timestamp_col])

        if expected_timestamps is not None and not timestamps.equals(
            expected_timestamps
        ):
            raise ValueError(
                "ahead_prices.csv timestamps must match the scenario timestamps exactly."
            )

        export_price_ahead = (
            pd.to_numeric(df[export_price_ahead_col], errors="coerce").to_numpy(
                dtype=float
            )
            if export_price_ahead_col is not None
            else np.zeros(len(df), dtype=float)
        )

        return {
            "timestamps": timestamps,
            "import_price_ahead": pd.to_numeric(
                df[import_price_ahead_col], errors="coerce"
            ).to_numpy(dtype=float),
            "export_price_ahead": export_price_ahead,
        }

    @staticmethod
    def parse_fix_decision_vars_csv(
        content: Optional[bytes], battery_ids: List[str] | None
    ) -> Dict[str, Any]:
        """
        Parse fixed decision variables CSV file.

        Args:
            content: CSV file content as bytes (optional)

        Returns:
            Dictionary with decision variables to fix during optimization

        Raises:
            ValueError: If CSV is invalid
        """
        if content is None:
            return {}

        try:
            data = pd.read_csv(io.BytesIO(content))
        except Exception as e:
            raise ValueError(f"Invalid CSV in fixed decision variables file: {e}")

        fix_decision_vars = {}
        if "grid_import" in data.columns:
            fix_decision_vars["grid_import_values"] = data["grid_import"].values
        if "grid_export" in data.columns:
            fix_decision_vars["grid_export_values"] = data["grid_export"].values
        if battery_ids is not None and len(data.columns) > 2:
            charge_values = []
            discharge_values = []
            for battery_id in battery_ids:
                charge_values.append(data[f"{battery_id}_charge"].values)
                discharge_values.append(data[f"{battery_id}_discharge"].values)

            fix_decision_vars["charge_values"] = np.array(charge_values)
            fix_decision_vars["discharge_values"] = np.array(discharge_values)

        return fix_decision_vars

    @staticmethod
    def parse_config_json(content: Optional[bytes]) -> SolverConfig:
        """
        Parse solver configuration JSON file.

        Args:
            content: JSON file content as bytes (optional)

        Returns:
            SolverConfig object with defaults if content is None

        Raises:
            ValueError: If JSON is invalid
        """
        if content is None:
            # Return default config
            return SolverConfig()

        try:
            data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")

        try:
            config = SolverConfig(**data)
        except Exception as e:
            raise ValueError(f"Invalid config: {e}")

        return config

    @staticmethod
    def results_to_csv(results_df: pd.DataFrame) -> str:
        """
        Convert results DataFrame to CSV string.

        Args:
            results_df: Results DataFrame from optimizer

        Returns:
            CSV string
        """
        return results_df.to_csv(index=True)
