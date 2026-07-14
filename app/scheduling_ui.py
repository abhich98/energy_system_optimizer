from __future__ import annotations

import copy
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scheduling_config import (
    DEFAULT_BATTERY_VALUES_DICT,
    DEFAULT_SOLVER_OPTS_DICT,
    CHART_COLORS,
)

from esms.models import Battery
from esms.models.battery import BATTERY_UNITS


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
            st.session_state[f"{key_prefix}_{key}_{idx}"] = battery[key]


def battery_editor(key_prefix: str) -> Optional[list[dict[str, Any]]]:
    state_key = f"{key_prefix}_batteries_state"
    count_widget_key = f"{key_prefix}_battery_count_input"

    if state_key not in st.session_state:
        st.session_state[state_key] = [copy.copy(DEFAULT_BATTERY_VALUES_DICT)]
    if count_widget_key not in st.session_state:
        st.session_state[count_widget_key] = len(st.session_state[state_key])
        _seed_battery_widget_state(key_prefix, st.session_state[state_key])

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
                st.session_state[state_key].append(_default_battery_template(idx))
        else:
            st.session_state[state_key] = st.session_state[state_key][:desired_count]
        _seed_battery_widget_state(key_prefix, st.session_state[state_key])

    edited_batteries: list[dict[str, Any]] = []

    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))

    def _clamp_state(key: str, low: float, high: float) -> None:
        st.session_state[key] = _clamp(st.session_state[key], low, high)

    tabs = st.tabs(
        [f"Battery {i + 1}" for i in range(len(st.session_state[state_key]))]
    )
    dcharge = 0.2
    for idx, tab in enumerate(tabs):
        with tab:
            if st.button("Reset to defaults", key=f"{key_prefix}_reset_{idx}"):
                reset_template = _default_battery_template(idx)
                st.session_state[state_key][idx] = reset_template
                for key in reset_template.keys():
                    st.session_state[f"{key_prefix}_{key}_{idx}"] = reset_template[key]

            st.text_input("id", key=f"{key_prefix}_id_{idx}")
            _clamp_state(f"{key_prefix}_capacity_{idx}", dcharge, 100.0)
            st.slider(
                f"capacity [{BATTERY_UNITS['capacity']}]",
                min_value=dcharge,
                max_value=100.0,
                step=dcharge,
                key=f"{key_prefix}_capacity_{idx}",
            )

            capacity_now = float(st.session_state[f"{key_prefix}_capacity_{idx}"])
            _clamp_state(f"{key_prefix}_max_charge_{idx}", dcharge, capacity_now)
            st.slider(
                f"max_charge [{BATTERY_UNITS['max_charge']}]",
                min_value=dcharge,
                max_value=capacity_now,  # assuming battery takes at least 1 hour to charge fully
                step=dcharge,
                key=f"{key_prefix}_max_charge_{idx}",
            )
            _clamp_state(f"{key_prefix}_max_discharge_{idx}", dcharge, capacity_now)
            st.slider(
                f"max_discharge [{BATTERY_UNITS['max_discharge']}]",
                min_value=dcharge,
                max_value=capacity_now,  # assuming battery takes at least 1 hour to discharge fully
                step=dcharge,
                key=f"{key_prefix}_max_discharge_{idx}",
            )

            _clamp_state(f"{key_prefix}_charge_efficiency_{idx}", 0.01, 1.0)
            st.slider(
                "charge_efficiency",
                min_value=0.01,
                max_value=1.0,
                step=0.01,
                key=f"{key_prefix}_charge_efficiency_{idx}",
            )
            _clamp_state(f"{key_prefix}_discharge_efficiency_{idx}", 0.01, 1.0)
            st.slider(
                "discharge_efficiency",
                min_value=0.01,
                max_value=1.0,
                step=0.01,
                key=f"{key_prefix}_discharge_efficiency_{idx}",
            )

            _clamp_state(f"{key_prefix}_initial_soc_{idx}", 0.0, capacity_now)
            st.slider(
                f"initial_soc [{BATTERY_UNITS['initial_soc']}]",
                min_value=0.0,
                max_value=capacity_now,
                step=dcharge,
                key=f"{key_prefix}_initial_soc_{idx}",
            )
            _clamp_state(f"{key_prefix}_min_soc_{idx}", 0.0, capacity_now)
            st.slider(
                f"min_soc [{BATTERY_UNITS['min_soc']}]",
                min_value=0.0,
                max_value=capacity_now,
                step=dcharge,
                key=f"{key_prefix}_min_soc_{idx}",
            )
            _clamp_state(f"{key_prefix}_max_soc_{idx}", 0.0, capacity_now)
            st.slider(
                f"max_soc [{BATTERY_UNITS['max_soc']}]",
                min_value=0.0,
                max_value=capacity_now,
                step=dcharge,
                key=f"{key_prefix}_max_soc_{idx}",
            )

            _clamp_state(f"{key_prefix}_degradation_cost_{idx}", 0.0, 0.5)
            st.slider(
                f"degradation_cost [{BATTERY_UNITS['degradation_cost']}]",
                min_value=0.0,
                max_value=0.5,
                step=0.005,
                key=f"{key_prefix}_degradation_cost_{idx}",
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
                    st.session_state[f"{key_prefix}_charge_efficiency_{idx}"]
                ),
                "discharge_efficiency": float(
                    st.session_state[f"{key_prefix}_discharge_efficiency_{idx}"]
                ),
                "initial_soc": float(
                    st.session_state[f"{key_prefix}_initial_soc_{idx}"]
                ),
                "min_soc": float(st.session_state[f"{key_prefix}_min_soc_{idx}"]),
                "max_soc": float(st.session_state[f"{key_prefix}_max_soc_{idx}"]),
                "degradation_cost": float(
                    st.session_state[f"{key_prefix}_degradation_cost_{idx}"]
                ),
            }
        )

    validated, err = _validate_batteries(edited_batteries)
    if err:
        st.error(f"Battery validation failed: {err}")
        return None
    if validated is None:
        st.error("Battery validation failed for unknown reason.")
        return None
    st.session_state[state_key] = [dict(b) for b in validated]
    return validated


def solver_opts_editor(key_prefix: str) -> Optional[dict[str, Any]]:
    state_key = f"{key_prefix}_opts_state"

    if state_key not in st.session_state:
        st.session_state[state_key] = copy.copy(DEFAULT_SOLVER_OPTS_DICT)

    opts = st.session_state[state_key]
    timestep_hours = st.number_input(
        "timestep_hours [hours]",
        min_value=0.01,
        value=float(opts.get("timestep_hours", 1.0)),
        step=0.25,
        key=f"{key_prefix}_timestep_hours",
        help="Time interval in of the input data in hours. Example: 1.0 = hourly steps, 0.25 = 15-minute steps. Only applicable if 'Date' column is not provided in the input CSVs.",
    )

    edited = {"timestep_hours": float(timestep_hours)}
    if float(timestep_hours) <= 0:
        st.error("Timestep hours must be greater than 0.")
        return None
    st.session_state[state_key] = dict(edited)
    return edited


# Color palette for dark blue background
COLOR_PV = CHART_COLORS["pv"]
COLOR_LOAD = CHART_COLORS["load"]
COLOR_PRICE = CHART_COLORS["price"]
COLOR_CHARGE = CHART_COLORS["charge"]
COLOR_DISCHARGE = CHART_COLORS["discharge"]
COLOR_SOC = CHART_COLORS["soc"]
COLOR_ACTUAL = CHART_COLORS["actual"]
COLOR_EXPECTED = CHART_COLORS["expected"]


def build_output_panel_chart(
    input_df: pd.DataFrame,
    output_df: pd.DataFrame,
    batteries: list[dict],
    pv_label: str = "PV",
    load_label: str = "Load",
    show_actual: bool = False,
) -> go.Figure:
    """Build scheduling output chart with per-battery subplots and SOC on secondary y-axis.

    Args:
        input_df: Input forecasts/ahead data (for pv, load, price traces).
        output_df: Optimization output DataFrame.
        batteries: Battery config list (for SOC-to-percentage conversion).
        pv_label: Label for PV trace (e.g., "Forecasted PV", "Expected PV").
        load_label: Label for Load trace (e.g., "Forecasted Load", "Expected Load").
        show_actual: If True, also show actual pv/load from input_df as separate traces.

    # TODO: show_actual and input_df are turning out to be redundant, but keeping them for now in case we want to show actual vs expected in the future.
    """
    # Detect battery IDs from output columns
    battery_ids: list[str] = []
    for bat in batteries:
        battery_ids.append(str(bat["id"]))
    battery_ids = sorted(set(battery_ids))

    n_batteries = len(battery_ids)
    n_rows = 2 + n_batteries  # row 1: PV/Load, row 2: Price, rows 3+: batteries

    subplot_titles = [f"{pv_label} and {load_label}", "Import and Export Price"]
    for bid in battery_ids:
        subplot_titles.append(f"{bid}: Charge/Discharge (kW) & SOC (%)")

    specs: list[list[dict]] = [[{"secondary_y": False}], [{"secondary_y": False}]]
    for _ in battery_ids:
        specs.append([{"secondary_y": True}])

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        subplot_titles=tuple(subplot_titles),
        specs=specs,
    )

    input_x = input_df.index
    output_x = output_df.index

    # Row 1: PV and Load
    pv_col_out = (
        "pv"
        if "pv" in output_df.columns
        else ("expected_pv" if "expected_pv" in output_df.columns else None)
    )
    load_col_out = (
        "load"
        if "load" in output_df.columns
        else ("expected_load" if "expected_load" in output_df.columns else None)
    )

    if pv_col_out and pv_col_out in output_df.columns:
        fig.add_trace(
            go.Scatter(
                x=output_x,
                y=output_df[pv_col_out],
                mode="lines",
                name=pv_label,
                line=dict(color=COLOR_PV),
            ),
            row=1,
            col=1,
        )
    if load_col_out and load_col_out in output_df.columns:
        fig.add_trace(
            go.Scatter(
                x=output_x,
                y=output_df[load_col_out],
                mode="lines",
                name=load_label,
                line=dict(color=COLOR_LOAD),
            ),
            row=1,
            col=1,
        )
    if show_actual and "pv" in input_df.columns:
        fig.add_trace(
            go.Scatter(
                x=input_x,
                y=input_df["pv"],
                mode="lines",
                name="Actual PV",
                line=dict(color=COLOR_ACTUAL, dash="dash"),
            ),
            row=1,
            col=1,
        )
    if show_actual and "load" in input_df.columns:
        fig.add_trace(
            go.Scatter(
                x=input_x,
                y=input_df["load"],
                mode="lines",
                name="Actual Load",
                line=dict(color=COLOR_EXPECTED, dash="dash"),
            ),
            row=1,
            col=1,
        )
    fig.update_yaxes(title_text="Power (kW)", row=1, col=1)

    # Row 2: Import and Export Price
    for col, label, color in [
        ("import_price", "Import Price", COLOR_PRICE),
        # ("export_price", "Export Price", "#94a3b8"),
    ]:
        src_df = output_df if col in output_df.columns else input_df
        if col in src_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=(output_x if col in output_df.columns else input_x),
                    y=src_df[col],
                    mode="lines",
                    name=label,
                    line=dict(color=color),
                ),
                row=2,
                col=1,
            )
    fig.update_yaxes(
        title_text="Electricity Price (EUR/kWh)", row=2, col=1, autorange=True
    )

    # Rows 3+: Per-battery charge/discharge + SOC
    battery_capacities: dict[str, float] = {}
    if batteries:
        for b in batteries:
            bid = str(b["id"])
            battery_capacities[bid] = float(b.get("capacity", 1.0))

    for i, bid in enumerate(battery_ids):
        row = 3 + i
        charge_col = f"{bid}_charge"
        discharge_col = f"{bid}_discharge"
        soc_col = f"{bid}_soc"

        if charge_col in output_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=output_x,
                    y=output_df[charge_col].round(4),
                    mode="lines",
                    name=f"{bid} Charge",
                    line=dict(color=COLOR_CHARGE),
                ),
                row=row,
                col=1,
                secondary_y=False,
            )
        if discharge_col in output_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=output_x,
                    y=output_df[discharge_col].round(4),
                    mode="lines",
                    name=f"{bid} Discharge",
                    line=dict(color=COLOR_DISCHARGE),
                ),
                row=row,
                col=1,
                secondary_y=False,
            )
        if soc_col in output_df.columns:
            capacity = battery_capacities.get(bid, 1.0)
            soc_pct = pd.to_numeric(output_df[soc_col], errors="coerce").fillna(0.0)
            if capacity > 0:
                soc_pct = (soc_pct / capacity * 100.0).clip(0, 100)
            fig.add_trace(
                go.Scatter(
                    x=output_x,
                    y=soc_pct,
                    mode="lines",
                    name=f"{bid} SOC",
                    line=dict(color=COLOR_SOC, dash="dot"),
                ),
                row=row,
                col=1,
                secondary_y=True,
            )
        fig.update_yaxes(
            title_text="Power (kW)",
            row=row,
            col=1,
            secondary_y=False,
            showgrid=True,
            gridcolor="rgba(255,255,255,0.12)",
            griddash="solid",
            dtick=None,
        )
        fig.update_yaxes(
            title_text="SOC (%)",
            row=row,
            col=1,
            secondary_y=True,
            range=[0, 105],
            showgrid=False,
            dtick=15,
        )

    height = 600 + n_batteries * 300
    # Equal-height y-domains for all subplots (Plotly: y=0 is bottom, y=1 is top)
    row_height = 1.0 / n_rows
    for i in range(n_rows):
        y_end = 1.0 - i * row_height
        y_start = y_end - row_height
        fig.update_yaxes(domain=[y_start, y_end], row=i + 1, col=1)
    fig.update_layout(
        height=height,
        legend=dict(orientation="v", x=0.94, xanchor="left"),
        margin=dict(t=60, b=20, r=40),
    )
    fig.update_xaxes(
        title_text="Date",
        row=n_rows,
        col=1,
    )
    return fig


def apply_theme_and_header() -> None:
    st.set_page_config(page_title="Household Battery Scheduling", layout="wide")
    theme_css = """
        <style>
            html, body, [class*="css"] { font-size: 1.20rem; }
            .stApp {
                background: radial-gradient(circle at 20% 20%, rgba(14, 165, 233, 0.18), transparent 40%),
                            radial-gradient(circle at 80% 0%, rgba(34, 197, 94, 0.14), transparent 45%),
                            linear-gradient(180deg, #1a103d 0%, #120a2c 100%);
                color: #f8fafc;
            }
            [data-testid="stAppViewContainer"],
            [data-testid="stHeader"],
            [data-testid="stToolbar"],
            [data-testid="stToolbar"] {
                background: transparent;
            }
            [data-testid="stSidebar"],
            [data-testid="stSidebar"] > div:first-child {
                background: linear-gradient(180deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.75) 100%);
                border-right: 1px solid rgba(56, 189, 248, 0.25);
            }
            [data-testid="stMainBlockContainer"],
            [data-testid="stAppViewContainer"] .main .block-container,
            section.main > div.block-container {
                padding-top: 2.0rem !important;
            }
            main, section, article, div[data-testid="stVerticalBlock"], div[data-testid="stHorizontalBlock"] {
                color: #f8fafc;
            }
            p, li, label, span, div, h1, h2, h3, h4, h5, h6 {
                color: inherit;
            }
            .stMarkdown, .stCaption, .stText, .stExpander, .stDataFrame, .stPlotlyChart {
                color: #f8fafc;
            }
            .stButton>button {
                background-color: #0ea5e9;
                color: #ffffff;
                border: 0;
                border-radius: 8px;
                font-weight: 700;
            }
            .stButton>button:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
            .stTabs [data-baseweb="tab"] {
                color: #f8fafc;
            }
            .stTabs [aria-selected="true"] {
                background: linear-gradient(90deg, rgba(14, 165, 233, 0.28), rgba(168, 85, 247, 0.22));
                border-color: rgba(168, 85, 247, 0.45);
            }
            .stNumberInput input,
            .stTextInput input,
            .stTextArea textarea,
            .stSelectbox div,
            .stMultiSelect div {
                background-color: #0f172a !important;
                color: #f8fafc !important;
                border-color: #334155 !important;
            }
            .stNumberInput label,
            .stTextInput label,
            .stTextArea label,
            .stSelectbox label,
            .stRadio label,
            .stCheckbox label {
                color: #f8fafc !important;
            }
            .stSlider [role="slider"] {
                background: #facc15 !important;
                border: 2px solid #0f172a !important;
            }
            .stSlider [role="slider"]:focus,
            .stSlider [role="slider"]:focus-visible {
                box-shadow: 0 0 0 3px rgba(250, 204, 21, 0.35) !important;
                outline: none !important;
            }
            .stSlider [data-testid="stTickBarMin"],
            .stSlider [data-testid="stTickBarMax"],
            .stSlider [data-testid="stSliderMin"],
            .stSlider [data-testid="stSliderMax"] {
                color: #ffffff !important;
                background: transparent !important;
                text-shadow: 0 1px 2px rgba(15, 23, 42, 0.75) !important;
            }
            .stSlider:focus-within [data-testid="stTickBarMin"],
            .stSlider:focus-within [data-testid="stTickBarMax"],
            .stSlider:focus-within [data-testid="stSliderMin"],
            .stSlider:focus-within [data-testid="stSliderMax"] {
                color: #ffffff !important;
                background: transparent !important;
            }
            .stExpander {
                border: 1px solid rgba(56, 189, 248, 0.24) !important;
                border-radius: 12px !important;
                background: rgba(15, 23, 42, 0.32) !important;
            }
            .stInfo {
                border-left: 6px solid #22d3ee !important;
            }
            .stSuccess {
                border-left: 6px solid #34d399 !important;
            }
            .stWarning {
                border-left: 6px solid #f59e0b !important;
            }
            .stError {
                border-left: 6px solid #ef4444 !important;
            }
            [data-testid="stDataFrame"] {
                background: rgba(15, 23, 42, 0.88);
                border: 1px solid rgba(168, 85, 247, 0.3);
                border-radius: 10px;
            }
            .app-header {
                background: linear-gradient(90deg, #0ea5e9, #22c55e, #a855f7);
                padding: 18px 22px;
                border-radius: 12px;
                color: #ffffff;
                text-align: center;
                box-shadow: 0 18px 44px rgba(14, 165, 233, 0.24);
                margin-top: 0;
            }
            .app-header h1 { color: #ffffff !important; font-size: 2.0rem; margin: 0; }
            .app-header p { margin: 8px 0 0 0; color: #e2e8f0; font-weight: 600; }
        </style>
    """
    st.markdown(theme_css, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="app-header">
            <h1>🔋 Household Battery Scheduling</h1>
            <p><i>When to charge and when not to</i> -- obtain day-ahead (tomorrow's) schedule for your household battery/BESS.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
