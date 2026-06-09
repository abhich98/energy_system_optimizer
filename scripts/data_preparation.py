from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
import logging

import h5py
import pandas as pd
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = (
	ROOT_DIR / "data" / "data_household_germany" / "data_preparation_config.yaml"
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Data Preparation")


def load_config(config_path: Path) -> dict[str, Any]:
	with config_path.open("r", encoding="utf-8") as config_file:
		return yaml.safe_load(config_file)


def build_hdf_table_path(template: str, household_id: str) -> str:
	return template.format(household_id=household_id)


def ensure_unique_date_rows(frame: pd.DataFrame, value_columns: list[str]) -> pd.DataFrame:
	aggregated = (
		frame.groupby("Date", as_index=False)[value_columns]
		.mean(numeric_only=True)
		.sort_values("Date")
		.reset_index(drop=True)
	)
	return aggregated[["Date", *value_columns]]


def read_power_table(
	h5_file: h5py.File, table_path: str, time_column: str, power_column: str, value_name: str
) -> pd.DataFrame:
	"""Read a power table from the HDF5 file and convert it to a DataFrame.
	Assumes the time column is in seconds since epoch and the power column is in watts.
	Returns a DataFrame with a Date column and a value column in kW.
	"""
	table = h5_file[table_path]
	frame = pd.DataFrame(table.fields([power_column, time_column])[:])
	frame["Date"] = pd.to_datetime(frame[time_column], unit="s")
	frame[value_name] = pd.to_numeric(frame[power_column], errors="coerce")
	frame[value_name] /= 1000.0  # Convert W to kW

	return ensure_unique_date_rows(frame, [value_name])


def read_price_table(
	prices_path: Path, price_time_column: str, price_mwh_column: str
) -> pd.DataFrame:
	prices = pd.read_csv(prices_path, sep=";", low_memory=False)
	prices["Date"] = pd.to_datetime(
		prices[price_time_column], format="%b %d, %Y %I:%M %p", errors="raise"
	)
	prices["Energy price (EUR/MWh)"] = pd.to_numeric(
		prices[price_mwh_column], errors="coerce"
	)
	prices["Energy price (EUR/kWh)"] = prices["Energy price (EUR/MWh)"] / 1000.0

	return ensure_unique_date_rows(prices, ["Energy price (EUR/MWh)", "Energy price (EUR/kWh)"])


def build_dataset(config: dict[str, Any], config_path: Path) -> pd.DataFrame:
	data_dir = config_path.parent
	household_id = config["household_id"]
	time_column = config["columns"]["time"]
	power_column = config["columns"]["power"]

	hdf5_path = data_dir / config["input"]["hdf5_file"]
	prices_path = data_dir / config["input"]["prices_file"]

	year = config["year"]
	time_delta = config["time_delta"]
	time_series = pd.date_range(
		start=f"{year}-01-01 00:00:00",
		end=f"{year}-12-31 23:59:59",
		freq=pd.Timedelta(hours=time_delta),
	)

	with h5py.File(hdf5_path, "r") as h5_file:
		pv = read_power_table(
			h5_file,
			config["tables"]["pv"],
			time_column,
			power_column,
			"PV generation (kW)",
		)
		pv["PV generation (kW)"] *= eval(config["PV_ratio"])  # Scale PV generation to household load

		household = read_power_table(
			h5_file,
			build_hdf_table_path(config["tables"]["household"], household_id),
			time_column,
			power_column,
			"household_load",
		)
		heatpump = read_power_table(
			h5_file,
			build_hdf_table_path(config["tables"]["heatpump"], household_id),
			time_column,
			power_column,
			"heatpump_load",
		)

	load = household.merge(heatpump, on="Date", how="outer")
	load["Consumption (kW)"] = load["household_load"].fillna(0) + load[
		"heatpump_load"
	].fillna(0)
	load = load[["Date", "Consumption (kW)"]]

	prices = read_price_table(
		prices_path,
		config["columns"]["price_time"],
		config["columns"]["price_mwh"],
	)
	prices["Energy price (EUR/kWh)"] += config["prices_fixed_comp_euro_kwh"]
	prices["Energy price (EUR/kWh)"].clip(lower=0.0, inplace=True) # Ensure no negative prices after adding the fixed component
	prices["Energy price (EUR/MWh)"] = prices["Energy price (EUR/kWh)"] * 1000.0

	dataset = pd.DataFrame({"Date": time_series})
	logger.info(f"dataset shape after initialization: {dataset.shape}")
	dataset = dataset.merge(prices, on="Date", how="left", validate="one_to_one")

	# PV and load data come from 2019, so we merge them with the dataset after merging the prices to preserve the price data for the target year (2025)
	year_diff = year - pv["Date"].dt.year.iloc[0]
	pv["Date"] = pv["Date"] + pd.DateOffset(years=year_diff)
	load["Date"] = load["Date"] + pd.DateOffset(years=year_diff)
	dataset = dataset.merge(pv, on="Date", how="left", validate="one_to_one")
	dataset = dataset.merge(load, on="Date", how="left", validate="one_to_one")
	dataset = dataset.sort_values("Date").reset_index(drop=True)

	dataset["Consumption (pu)"] = (
		dataset["Consumption (kW)"] / dataset["Consumption (kW)"].max(skipna=True)
	)

	column_order = [
		"Date",
		"PV generation (kW)",
		"Consumption (kW)",
		"Consumption (pu)",
		"Energy price (EUR/MWh)",
		"Energy price (EUR/kWh)",
	]
	logger.info(f"Final dataset shape: {dataset.shape}")
	return dataset[column_order]


def build_output_path(config: dict[str, Any], version: str) -> Path:
	output_dir = ROOT_DIR / config["output"]["directory"]
	filename = f"{config['output']['filename_stem']}_v{version}.xlsx"
	return output_dir / filename


def write_dataset(dataset: pd.DataFrame, config: dict[str, Any], output_path: Path) -> None:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
		dataset.to_excel(
			writer,
			sheet_name=config["output"]["sheet_name"],
			index=False,
		)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Build a Germany household dataset workbook from HDF5 and price sources."
	)
	parser.add_argument(
		"--config",
		type=Path,
		default=DEFAULT_CONFIG_PATH,
		help="Path to the YAML configuration file.",
	)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	config_path = args.config.resolve()
	config = load_config(config_path)
	version = config["version"]
	logger.info(f"Building dataset version {version} using config at {config_path}")

	dataset = build_dataset(config, config_path)
	output_path = build_output_path(config, version)
	write_dataset(dataset, config, output_path)

	logger.info(f"Wrote {len(dataset)} rows to {output_path}")


if __name__ == "__main__":
	main()
