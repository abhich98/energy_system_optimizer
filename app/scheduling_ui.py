from __future__ import annotations

import copy
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scheduling_config import DEFAULT_BATTERY_VALUES_DICT, DEFAULT_SOLVER_OPTS_DICT

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
    tabs = st.tabs(
        [f"Battery {i + 1}" for i in range(len(st.session_state[state_key]))]
    )
    for idx, tab in enumerate(tabs):
        with tab:
            if st.button("Reset to defaults", key=f"{key_prefix}_reset_{idx}"):
                reset_template = _default_battery_template(idx)
                st.session_state[state_key][idx] = reset_template
                for key in reset_template.keys():
                    st.session_state[f"{key_prefix}_{key}_{idx}"] = reset_template[key]
                st.rerun()

            st.text_input("id", key=f"{key_prefix}_id_{idx}")
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
                key=f"{key_prefix}_charge_efficiency_{idx}",
            )
            col5.number_input(
                "discharge_efficiency",
                min_value=0.0001,
                max_value=1.0,
                key=f"{key_prefix}_discharge_efficiency_{idx}",
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
    st.session_state[state_key] = [dict(b) for b in validated]
    return validated


def solver_opts_editor(key_prefix: str) -> Optional[dict[str, Any]]:
    state_key = f"{key_prefix}_opts_state"

    if state_key not in st.session_state:
        st.session_state[state_key] = copy.copy(DEFAULT_SOLVER_OPTS_DICT)

    opts = st.session_state[state_key]
    field_col, info_col = st.columns([12, 1])
    timestep_hours = field_col.number_input(
        "timestep_hours [hours]",
        min_value=0.01,
        value=float(opts.get("timestep_hours", 1.0)),
        step=0.25,
        key=f"{key_prefix}_timestep_hours",
    )
    if info_col.button("ℹ️", key=f"{key_prefix}_timestep_hours_info"):
        st.info(
            "Optimization interval in hours. Example: 1.0 = hourly steps, 0.25 = 15-minute steps. Only applicable if 'Date' column is not provided in the input CSVs."
        )

    edited = {"timestep_hours": float(timestep_hours)}
    if float(timestep_hours) <= 0:
        st.error("Timestep hours must be greater than 0.")
        return None
    st.session_state[state_key] = dict(edited)
    return edited


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


def apply_theme_and_header() -> None:
    st.set_page_config(page_title="Household Battery Scheduling", layout="wide")
    theme_css = """
        <style>
            html, body, [class*="css"] { font-size: 1.30rem; }
            .stApp {
                background: linear-gradient(180deg, #1a103d 0%, #120a2c 100%);
                color: #f8fafc;
            }
            [data-testid="stAppViewContainer"],
            [data-testid="stHeader"],
            [data-testid="stToolbar"],
            [data-testid="stSidebar"],
            [data-testid="stSidebarNav"] {
                background: transparent;
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
                border-radius: 10px;
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
                background-color: rgba(14, 165, 233, 0.18);
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
            [data-testid="stDataFrame"] {
                background: rgba(15, 23, 42, 0.88);
            }
            .app-header {
                background: linear-gradient(90deg, #0ea5e9, #22c55e);
                padding: 18px 22px;
                border-radius: 12px;
                color: #ffffff;
                text-align: center;
                box-shadow: 0 16px 40px rgba(0, 0, 0, 0.28);
            }
            .app-header h1 { color: #ffffff !important; font-size: 2.0rem; margin: 0; }
            .app-header p { margin: 8px 0 0 0; color: #e2e8f0; font-weight: 600; }
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
