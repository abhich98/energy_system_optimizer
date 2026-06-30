from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Optional, Tuple
import copy
from unittest.mock import DEFAULT

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from esms.models.battery import BATTERY_UNITS
from esms.models import Battery

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]

# API base URL (modify this depending on local vs hosted)
API_BASE = "http://localhost:8001"
DETERM_ENDPOINT = f"{API_BASE}/dayahead/deterministic"
STOCH_ENDPOINT = f"{API_BASE}/dayahead/stochastic"

OPENSOURCE_HOUSEHOLD_INFO = (
    "Open household data source: https://doi.org/10.1038/s41597-022-01156-1"
)
OPENSOURCE_PRICES_INFO = "Open prices data source for the year 2025 were synthesised from the German spot market (EPEX SPOT) day-ahead prices for 2025. Read the repository README for more details."


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def list_files(folder: Path, pattern: str) -> list[Path]:
    return sorted(folder.glob(pattern))


def load_text_bytes(path: Path) -> bytes:
    return path.read_bytes()


def parse_csv_preview(content: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(content))


DETERM_REQUIRED_COLS = ["pv", "load", "import_price"]
HIST_REQUIRED_COLS = ["pv", "load"]
AHEAD_REQUIRED_COLS = ["import_price"]

SAMPLE_SINGLE_BATTERY_PATH = ROOT_DIR / "config" / "sonnenBatterie10.json"
DEFAULT_BATTERY_VALUES_DICT = load_json_file(SAMPLE_SINGLE_BATTERY_PATH)[0]

DEFAULT_SOLVER_CONFIG_DICT = {
    "solver": "scip",
    "timestep_hours": 1.0,
    "verbose": False,
}


def _validate_batteries(
    raw_batteries: list[dict[str, Any]],
) -> tuple[Optional[list[dict[str, Any]]], Optional[str]]:
    try:
        validated = [Battery(**b).model_dump() for b in raw_batteries]
        return validated, None
    except Exception as exc:
        return None, str(exc)


def _default_battery_template(index: int) -> dict[str, Any]:
    battery_dict = copy.copy(DEFAULT_BATTERY_VALUES_DICT)
    battery_dict["id"] = f"battery_{index + 1}"
    return battery_dict


def _seed_battery_widget_state(
    key_prefix: str, batteries: list[dict[str, Any]]
) -> None:
    for idx, battery in enumerate(batteries):
        for key in DEFAULT_BATTERY_VALUES_DICT.keys():
            st.session_state[f"{key_prefix}_{key}_{idx}"] = battery[key] # Every key should exist or else something is wrong with the battery dict.

        st.session_state[f"{key_prefix}_id_{idx}"] = str(
            battery.get("id", f"battery_{idx + 1}")
        )
        st.session_state[f"{key_prefix}_capacity_{idx}"] = float(
            battery.get("capacity", 1.0)
        )
        st.session_state[f"{key_prefix}_max_charge_{idx}"] = float(
            battery.get("max_charge", 1.0)
        )
        st.session_state[f"{key_prefix}_max_discharge_{idx}"] = float(
            battery.get("max_discharge", 1.0)
        )
        st.session_state[f"{key_prefix}_charge_eff_{idx}"] = float(
            battery.get("charge_efficiency", 0.95)
        )
        st.session_state[f"{key_prefix}_discharge_eff_{idx}"] = float(
            battery.get("discharge_efficiency", 0.95)
        )
        st.session_state[f"{key_prefix}_initial_soc_{idx}"] = float(
            battery.get("initial_soc", 0.0)
        )
        st.session_state[f"{key_prefix}_min_soc_{idx}"] = float(
            battery.get("min_soc", 0.0)
        )
        st.session_state[f"{key_prefix}_max_soc_{idx}"] = float(
            battery.get("max_soc", battery.get("capacity", 1.0))
        )
        st.session_state[f"{key_prefix}_degr_{idx}"] = float(
            battery.get("degradation_cost", 0.0)
        )


def battery_editor(
    key_prefix: str
) -> Optional[list[dict[str, Any]]]:
    state_key = f"{key_prefix}_batteries_state"
    count_widget_key = f"{key_prefix}_battery_count_input"

    if state_key not in st.session_state:
        st.session_state[state_key] = [copy.copy(DEFAULT_BATTERY_VALUES_DICT)]
    if count_widget_key not in st.session_state:
        st.session_state[count_widget_key] = len(st.session_state[state_key])
        # _seed_battery_widget_state(key_prefix, st.session_state[state_key])

    current_count = len(st.session_state[state_key])
    desired_count = st.number_input(
        "Number of batteries",
        min_value=1,
        max_value=10,
        step=1,
        key=count_widget_key,
    )
    desired_count = int(desired_count)
    if desired_count != current_count:
        if desired_count > current_count:
            for idx in range(current_count, desired_count):
                st.session_state[state_key].append(
                    _default_battery_template(idx)
                )
        else:
            st.session_state[state_key] = st.session_state[state_key][:desired_count]
        _seed_battery_widget_state(key_prefix, st.session_state[state_key])

    edited_batteries: list[dict[str, Any]] = []
    tabs = st.tabs(
        [f"Battery {i + 1}" for i in range(len(st.session_state[state_key]))]
    )
    for idx, tab in enumerate(tabs):
        template = st.session_state[state_key][idx]
        with tab:
            if st.button("Reset to defaults", key=f"{key_prefix}_reset_{idx}"):
                reset_template = _default_battery_template(default_batteries, idx)
                st.session_state[state_key][idx] = reset_template

                st.session_state[f"{key_prefix}_id_{idx}"] = str(
                    reset_template.get("id", f"battery_{idx + 1}")
                )
                st.session_state[f"{key_prefix}_capacity_{idx}"] = float(
                    reset_template.get("capacity", 1.0)
                )
                st.session_state[f"{key_prefix}_max_charge_{idx}"] = float(
                    reset_template.get("max_charge", 1.0)
                )
                st.session_state[f"{key_prefix}_max_discharge_{idx}"] = float(
                    reset_template.get("max_discharge", 1.0)
                )
                st.session_state[f"{key_prefix}_charge_eff_{idx}"] = float(
                    reset_template.get("charge_efficiency", 0.95)
                )
                st.session_state[f"{key_prefix}_discharge_eff_{idx}"] = float(
                    reset_template.get("discharge_efficiency", 0.95)
                )
                st.session_state[f"{key_prefix}_initial_soc_{idx}"] = float(
                    reset_template.get("initial_soc", 0.0)
                )
                st.session_state[f"{key_prefix}_min_soc_{idx}"] = float(
                    reset_template.get("min_soc", 0.0)
                )
                st.session_state[f"{key_prefix}_max_soc_{idx}"] = float(
                    reset_template.get("max_soc", reset_template.get("capacity", 1.0))
                )
                st.session_state[f"{key_prefix}_degr_{idx}"] = float(
                    reset_template.get("degradation_cost", 0.0)
                )
                st.rerun()

            st.text_input(
                "id",
                key=f"{key_prefix}_id_{idx}",
                value=str(template.get("id", f"battery_{idx + 1}")),
            )
            col1, col2, col3 = st.columns(3)
            col1.number_input(
                f"capacity [{BATTERY_UNITS['capacity']}]",
                min_value=0.001,
                key=f"{key_prefix}_capacity_{idx}",
            )
            col2.number_input(
                f"max_charge [{BATTERY_UNITS['max_charge']}]",
                min_value=0.001,
                key=f"{key_prefix}_max_charge_{idx}",
            )
            col3.number_input(
                f"max_discharge [{BATTERY_UNITS['max_discharge']}]",
                min_value=0.001,
                key=f"{key_prefix}_max_discharge_{idx}",
            )

            col4, col5, col6 = st.columns(3)
            col4.number_input(
                "charge_efficiency",
                min_value=0.0001,
                max_value=1.0,
                key=f"{key_prefix}_charge_eff_{idx}",
            )
            col5.number_input(
                "discharge_efficiency",
                min_value=0.0001,
                max_value=1.0,
                key=f"{key_prefix}_discharge_eff_{idx}",
            )
            col6.number_input(
                f"initial_soc [{BATTERY_UNITS['initial_soc']}]",
                min_value=0.0,
                key=f"{key_prefix}_initial_soc_{idx}",
            )

            col7, col8, col9 = st.columns(3)
            col7.number_input(
                f"min_soc [{BATTERY_UNITS['min_soc']}]",
                min_value=0.0,
                key=f"{key_prefix}_min_soc_{idx}",
            )
            col8.number_input(
                f"max_soc [{BATTERY_UNITS['max_soc']}]",
                min_value=0.0,
                key=f"{key_prefix}_max_soc_{idx}",
            )
            col9.number_input(
                f"degradation_cost [{BATTERY_UNITS['degradation_cost']}]",
                min_value=0.0,
                key=f"{key_prefix}_degr_{idx}",
            )

        edited_batteries.append(
            {
                "id": str(st.session_state[f"{key_prefix}_id_{idx}"]),
                "capacity": float(st.session_state[f"{key_prefix}_capacity_{idx}"]),
                "max_charge": float(st.session_state[f"{key_prefix}_max_charge_{idx}"]),
                "max_discharge": float(
                    st.session_state[f"{key_prefix}_max_discharge_{idx}"]
                ),
                "charge_efficiency": float(
                    st.session_state[f"{key_prefix}_charge_eff_{idx}"]
                ),
                "discharge_efficiency": float(
                    st.session_state[f"{key_prefix}_discharge_eff_{idx}"]
                ),
                "initial_soc": float(
                    st.session_state[f"{key_prefix}_initial_soc_{idx}"]
                ),
                "min_soc": float(st.session_state[f"{key_prefix}_min_soc_{idx}"]),
                "max_soc": float(st.session_state[f"{key_prefix}_max_soc_{idx}"]),
                "degradation_cost": float(st.session_state[f"{key_prefix}_degr_{idx}"]),
            }
        )

    validated, err = _validate_batteries(edited_batteries)
    if err:
        st.error(f"Battery validation failed: {err}")
        return None
    st.session_state[state_key] = [dict(b) for b in validated]
    return validated


def _validate_config(
    cfg: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        timestep_hours = float(cfg.get("timestep_hours", 1.0))
        if timestep_hours <= 0:
            raise ValueError("timestep_hours must be > 0")
        solver = str(cfg.get("solver", "scip"))
        verbose = bool(cfg.get("verbose", False))
        return {
            "solver": solver,
            "timestep_hours": timestep_hours,
            "verbose": verbose,
        }, None
    except Exception as exc:
        return None, str(exc)


def get_available_solvers() -> list[str]:
    try:
        response = requests.get(f"{API_BASE}/health", timeout=15)
        response.raise_for_status()
        payload = response.json()
        solvers = payload.get("available_solvers", [])
        if isinstance(solvers, list):
            return [str(solver) for solver in solvers if str(solver).strip()]
    except Exception:
        pass
    return []


def config_editor(
    default_config: dict[str, Any], available_solvers: list[str], key_prefix: str
) -> Optional[dict[str, Any]]:
    state_key = f"{key_prefix}_config_state"

    if state_key not in st.session_state:
        st.session_state[state_key] = {
            "solver": default_config.get("solver", "scip"),
            "timestep_hours": float(default_config.get("timestep_hours", 1.0)),
            "verbose": bool(default_config.get("verbose", False)),
        }

    cfg = st.session_state[state_key]
    solver_options = list(
        dict.fromkeys([solver for solver in available_solvers if solver])
    )
    current_solver = str(cfg.get("solver", default_config.get("solver", "scip")))
    if current_solver not in solver_options:
        solver_options = [current_solver] + [
            solver for solver in solver_options if solver != current_solver
        ]
    if not solver_options:
        solver_options = [current_solver]

    cols = st.columns(3)
    solver = cols[0].selectbox(
        "solver",
        options=solver_options,
        index=(
            solver_options.index(current_solver)
            if current_solver in solver_options
            else 0
        ),
        key=f"{key_prefix}_solver",
    )
    timestep_hours = cols[1].number_input(
        "timestep_hours [hours]",
        min_value=0.01,
        value=float(cfg.get("timestep_hours", 1.0)),
        step=0.25,
        key=f"{key_prefix}_timestep",
    )
    verbose = cols[2].checkbox(
        "verbose", value=bool(cfg.get("verbose", False)), key=f"{key_prefix}_verbose"
    )

    if st.button("Reset solver config", key=f"{key_prefix}_reset_cfg"):
        st.session_state[state_key] = {
            "solver": default_config.get("solver", solver_options[0]),
            "timestep_hours": float(default_config.get("timestep_hours", 1.0)),
            "verbose": bool(default_config.get("verbose", False)),
        }
        st.session_state[f"{key_prefix}_solver"] = st.session_state[state_key]["solver"]
        st.session_state[f"{key_prefix}_timestep"] = st.session_state[state_key][
            "timestep_hours"
        ]
        st.session_state[f"{key_prefix}_verbose"] = st.session_state[state_key][
            "verbose"
        ]
        cfg = st.session_state[state_key]
        solver = cfg["solver"]
        timestep_hours = cfg["timestep_hours"]
        verbose = cfg["verbose"]

    edited = {
        "solver": solver,
        "timestep_hours": float(timestep_hours),
        "verbose": bool(verbose),
    }
    validated, err = _validate_config(edited)
    if err:
        st.error(f"Config validation failed: {err}")
        return None
    st.session_state[state_key] = dict(validated)
    return validated


def build_four_panel_chart(
    input_df: pd.DataFrame, output_df: pd.DataFrame
) -> go.Figure:
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=(
            "PV and Load",
            "Import and Export Price",
            "Grid Import and Export",
            "Battery Charge and Discharge (All Batteries)",
        ),
    )

    input_x = (
        input_df["Date"]
        if "Date" in input_df.columns
        else (
            input_df["timestep"] if "timestep" in input_df.columns else input_df.index
        )
    )
    output_x = output_df.index

    for col, label in [("pv", "PV"), ("load", "Load")]:
        if col in input_df.columns:
            fig.add_trace(
                go.Scatter(x=input_x, y=input_df[col], mode="lines", name=label),
                row=1,
                col=1,
            )

    for col, label in [
        ("import_price", "Import Price"),
        ("export_price", "Export Price"),
    ]:
        if col in input_df.columns:
            fig.add_trace(
                go.Scatter(x=input_x, y=input_df[col], mode="lines", name=label),
                row=2,
                col=1,
            )

    grid_cols = [
        col
        for col in output_df.columns
        if "grid" in col.lower()
        and ("import" in col.lower() or "export" in col.lower())
    ]
    for col in grid_cols:
        fig.add_trace(
            go.Scatter(x=output_x, y=output_df[col], mode="lines", name=col),
            row=3,
            col=1,
        )

    battery_cols = [
        col
        for col in output_df.columns
        if ("charge" in col.lower() or "discharge" in col.lower())
        and "grid" not in col.lower()
    ]
    for col in battery_cols:
        fig.add_trace(
            go.Scatter(x=output_x, y=output_df[col], mode="lines", name=col),
            row=4,
            col=1,
        )

    fig.update_layout(
        height=1200, legend=dict(orientation="h"), margin=dict(t=60, b=20)
    )
    fig.update_xaxes(title_text="timestep", row=4, col=1)
    return fig


def apply_theme_and_header():
    st.set_page_config(page_title="Household Battery Scheduling", layout="wide")
    theme_css = """
        <style>
            /* Larger base font for readability */
            html, body, [class*="css"] { font-size: 1.18rem; }

            /* Light mode */
            @media (prefers-color-scheme: light) {
                    /* yellowish background */
                    .stApp { background-color: #fff8e1; }
                html, body, [class*="css"] { color: #0b1220; }
                .stButton>button { background-color: #0ea5e9; color: #0b1220; }
                .stTabs [data-baseweb="tab"] { color: #0b1220; }
            }

            /* Dark mode */
            @media (prefers-color-scheme: dark) {
                    /* dark purple background */
                    .stApp { background-color: #1a103d; }
                html, body, [class*="css"] { color: #e2e8f0; }
                .stButton>button { background-color: #22c55e; color: #0b1220; }
                .stTabs [data-baseweb="tab"] { color: #e2e8f0; }
            }

            .app-header { 
                background: linear-gradient(90deg, #0ea5e9, #22c55e); 
                padding: 18px 22px; border-radius: 12px; 
                color: #0b1220; text-align: center;
            }
            .app-header h1 { color: #0b1220 !important; font-size: 2.0rem; margin: 0; }
            .app-header p { margin: 8px 0 0 0; color: #0b1220; font-weight: 600; }
            .stButton>button { border-radius: 8px; border: 0; font-weight: 700; }
        </style>
        """
    st.markdown(theme_css, unsafe_allow_html=True)
    st.markdown(
        """
                <div class="app-header">
                    <h1>Household Battery Scheduling</h1>
                    <p>Obtain day-ahead (next day's) schedule for your household battery/BESS.</p>
                </div>
                """,
        unsafe_allow_html=True,
    )
    # Use your own data for day-ahead scheduling — forecast-based or historical-data–based — for a PV + battery household.


def call_deterministic_api(
    batteries: list[dict[str, Any]],
    forecasts_df: pd.DataFrame,
    timestep_hours: Optional[float],
) -> pd.DataFrame:
    payload = {
        "batteries": batteries,
        "forecasts_csv": forecasts_df.to_csv(index=False),
        "timestep_hours": timestep_hours,
    }
    r = requests.post(DETERM_ENDPOINT, json=payload, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"API error {r.status_code}: {r.text}")
    data = r.json()
    return (
        pd.DataFrame(data["schedule"]).set_index("Date")
        if "Date" in pd.DataFrame(data["schedule"]).columns
        else pd.DataFrame(data["schedule"])
    )


def call_stochastic_api(
    batteries: list[dict[str, Any]],
    history_df: pd.DataFrame,
    ahead_df: pd.DataFrame,
    policy_override: Optional[dict[str, Any]],
    timestep_hours: Optional[float],
) -> pd.DataFrame:
    payload = {
        "batteries": batteries,
        "history_csv": history_df.to_csv(index=False),
        "ahead_prices_csv": ahead_df.to_csv(index=False),
        "policy_override": policy_override,
        "timestep_hours": timestep_hours,
    }
    r = requests.post(STOCH_ENDPOINT, json=payload, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"API error {r.status_code}: {r.text}")
    data = r.json()
    return (
        pd.DataFrame(data["schedule"]).set_index("Date")
        if "Date" in pd.DataFrame(data["schedule"]).columns
        else pd.DataFrame(data["schedule"])
    )


def open_source_data_overview(df: pd.DataFrame, title_suffix: str = "") -> None:
    st.subheader(f"Open-source household data overview {title_suffix}")
    c1, c2 = st.columns(1)
    # Plot PV+Load and Prices
    with c1:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05)
        if all(c in df.columns for c in ["pv", "load"]):
            fig.add_trace(go.Scatter(x=df["Date"], y=df["pv"], name="PV"), row=1, col=1)
            fig.add_trace(
                go.Scatter(x=df["Date"], y=df["load"], name="Load"), row=1, col=1
            )
        if "import_price" in df.columns:
            fig.add_trace(
                go.Scatter(x=df["Date"], y=df["import_price"], name="Import Price"),
                row=2,
                col=1,
            )
        st.plotly_chart(fig, use_container_width=True)


def import_forecasts_flow() -> Tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    st.subheader("Forecast-based (deterministic) approach")
    st.caption(
        "Provide a CSV file with PV generation and load forecasts, and electricity prices, for the next day."
    )
    uploaded = st.file_uploader(
        "Upload forecasts CSV (columns: pv, load, import_price, Date (date-time, optional))",
        type=["csv"],
        key="forecast_upl",
    )
    if uploaded is None:
        st.info("Upload a forecasts CSV file to continue.")
        st.stop()
    forecasts_df = pd.read_csv(uploaded)
    available_solvers = get_available_solvers()
    with st.expander("Batteries", expanded=False):
        batteries = battery_editor(key_prefix="det")
    with st.expander("Solver configuration", expanded=False):
        config = config_editor(available_solvers, key_prefix="det")
    if batteries is None or config is None:
        st.info("Fix validation errors above to continue.")
        st.stop()
    return forecasts_df, batteries, config


def import_history_flow() -> Tuple[
    pd.DataFrame,
    pd.DataFrame,
    list[dict[str, Any]],
    dict[str, Any],
    Optional[dict[str, Any]],
]:
    st.subheader("Import historical + ahead data (stochastic method)")
    hist_u = st.file_uploader(
        "Upload history CSV (pv, load, optional Date)", type=["csv"], key="hist_upl"
    )
    ahead_u = st.file_uploader(
        "Upload ahead prices CSV (import_price, optional Date)",
        type=["csv"],
        key="ahead_upl",
    )
    if hist_u is None or ahead_u is None:
        st.info("Upload both history and ahead files to continue.")
        st.stop()
    hist_df = pd.read_csv(hist_u)
    ahead_df = pd.read_csv(ahead_u)
    available_solvers = get_available_solvers()
    with st.expander("Batteries", expanded=False):
        batteries = battery_editor(key_prefix="stoch")
    with st.expander("Solver configuration", expanded=False):
        config = config_editor(default_config, available_solvers, key_prefix="stoch")
    if batteries is None or config is None:
        st.info("Fix validation errors above to continue.")
        st.stop()
    st.subheader("Champion policy override (optional)")
    with st.expander("Override champion policy"):
        ov = {}
        if st.checkbox("Enable override"):
            ov["history_days"] = st.number_input("history_days", min_value=1, value=3)
            ov["num_scenarios"] = st.number_input("num_scenarios", min_value=1, value=3)
            ov["pv_coeff"] = st.slider("pv_coeff", 0.0, 1.0, 0.5, 0.05)
            ov["load_coeff"] = 1.0 - ov["pv_coeff"]
        else:
            ov = None
    return hist_df, ahead_df, batteries, config, ov


def main() -> None:
    apply_theme_and_header()

    with st.expander("Instructions", expanded=False):
        st.markdown("""
            - For household battery scheduling, provide PV generation, load, electricity price data, and battery specifications.
            - Under *dynamic* electricity pricing, the prices are tied to EPEX spot day-ahead market prices. The electricity provider informs the household of the next day's prices. If you have a general *fixed tariff* contract, provide the value from your contract. 
            - It is assumed that provided data has following units: PV generation and load are in kW (kilowatts); prices are in EUR/kWh.

            **NOTE**: No claims or guarantees are made.
            """)

    st.markdown("**Try one of the two approaches:**")

    det_tab, stoch_tab = st.tabs(["Forecast-based", "History–based"])

    with det_tab:
        forecasts_df, batteries, config = import_forecasts_flow(
            default_batteries, default_config
        )
        st.subheader("Input preview")
        with st.expander("Preview", expanded=True):
            ptab, ttab = st.tabs(["Plot", "Table"])
            with ptab:
                fig = make_subplots(
                    rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05
                )
                x = (
                    forecasts_df["Date"]
                    if "Date" in forecasts_df.columns
                    else forecasts_df.index
                )
                if all(c in forecasts_df.columns for c in ["pv", "load"]):
                    fig.add_trace(
                        go.Scatter(x=x, y=forecasts_df["pv"], name="PV"), row=1, col=1
                    )
                    fig.add_trace(
                        go.Scatter(x=x, y=forecasts_df["load"], name="Load"),
                        row=1,
                        col=1,
                    )
                if "import_price" in forecasts_df.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=x, y=forecasts_df["import_price"], name="Import Price"
                        ),
                        row=2,
                        col=1,
                    )
                st.plotly_chart(fig, use_container_width=True)
            with ttab:
                st.dataframe(
                    forecasts_df.head(300), use_container_width=True, height=260
                )
        if st.button("Run forecast-based scheduling", key="run_det"):
            with st.spinner("Calling API... (up to 5 minutes)"):
                try:
                    output_df = call_deterministic_api(
                        batteries, forecasts_df, config.get("timestep_hours")
                    )
                except Exception as exc:
                    st.error(str(exc))
                    st.stop()
            st.success("Completed.")
            with st.expander("Schedule output", expanded=True):
                otab1, otab2 = st.tabs(["Plot", "Table"])
                with otab1:
                    chart = build_four_panel_chart(forecasts_df, output_df)
                    st.plotly_chart(chart, use_container_width=True)
                with otab2:
                    st.dataframe(output_df, use_container_width=True, height=320)

    with stoch_tab:
        # Check champion availability via health
        try:
            h = requests.get(f"{API_BASE}/health", timeout=15)
            healthy = h.ok and h.json().get("champion_policy", {}).get("exists", False)
        except Exception:
            healthy = False
        if not healthy:
            st.error(
                "Champion policy is not configured on the server. Stochastic service is unavailable."
            )
            st.stop()
        st.caption(
            "History required columns: "
            + ", ".join(HIST_REQUIRED_COLS)
            + ". Ahead required: "
            + ", ".join(AHEAD_REQUIRED_COLS)
            + ". Optional: Date"
        )
        hist_df, ahead_df, batteries, config, override = import_history_flow(
            default_batteries, default_config
        )
        st.subheader("Inputs preview")
        with st.expander("Preview", expanded=True):
            ptab2, ttab2 = st.tabs(["Plot", "Table"])
            with ptab2:
                fig2 = make_subplots(
                    rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05
                )
                xh = hist_df["Date"] if "Date" in hist_df.columns else hist_df.index
                xa = ahead_df["Date"] if "Date" in ahead_df.columns else ahead_df.index
                if all(c in hist_df.columns for c in ["pv", "load"]):
                    fig2.add_trace(
                        go.Scatter(x=xh, y=hist_df["pv"], name="PV (history)"),
                        row=1,
                        col=1,
                    )
                    fig2.add_trace(
                        go.Scatter(x=xh, y=hist_df["load"], name="Load (history)"),
                        row=1,
                        col=1,
                    )
                if "import_price" in ahead_df.columns:
                    fig2.add_trace(
                        go.Scatter(
                            x=xa,
                            y=ahead_df["import_price"],
                            name="Import Price (ahead)",
                        ),
                        row=2,
                        col=1,
                    )
                st.plotly_chart(fig2, use_container_width=True)
            with ttab2:
                st.write("History (first rows)")
                st.dataframe(hist_df.head(200), use_container_width=True, height=200)
                st.write("Ahead prices (first rows)")
                st.dataframe(ahead_df.head(200), use_container_width=True, height=200)
        if st.button("Run historical-data–based scheduling", key="run_stoch"):
            with st.spinner("Calling API... (up to 5 minutes)"):
                try:
                    output_df = call_stochastic_api(
                        batteries,
                        hist_df,
                        ahead_df,
                        override,
                        config.get("timestep_hours"),
                    )
                except Exception as exc:
                    st.error(str(exc))
                    st.stop()
            st.success("Completed.")
            with st.expander("Schedule output", expanded=True):
                otab3, otab4 = st.tabs(["Plot", "Table"])
                with otab3:
                    plot_input = ahead_df.copy()
                    chart = build_four_panel_chart(plot_input, output_df)
                    st.plotly_chart(chart, use_container_width=True)
                with otab4:
                    st.dataframe(output_df, use_container_width=True, height=320)


if __name__ == "__main__":
    main()
