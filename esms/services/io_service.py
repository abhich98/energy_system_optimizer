"""I/O service for parsing input files and formatting output."""

import json
import io
from typing import List, Dict, Any, Optional
import pandas as pd

from esms.api.schemas import SolverConfig
from esms.models import Battery

FORECASTS_CSV_REQUIRED_COLUMNS = ["pv", "load", "price"]


class IOService:
    """Service for handling input/output operations."""

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

        Expected columns: timestep, pv, load, price, export_price (optional)

        Args:
            content: CSV file content as bytes

        Returns:
            Dictionary with pv, load, price, export_price arrays

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
            "price": df["price"].values,
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
