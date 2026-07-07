from __future__ import annotations

import os
from typing import Optional, Tuple

import pandas as pd
import json
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scheduling_api import (
    call_deterministic_api,
    call_stochastic_api,
    is_champion_healthy,
)
from scheduling_config import (
    AHEAD_REQUIRED_COLS,
    DETERM_REQUIRED_COLS,
    HIST_REQUIRED_COLS,

    CHAMPION_POLICY_PATH,

    OPEN_SOURCE_DATASET_PATH,
    OPEN_SOURCE_DATE_COL,
    OPEN_SOURCE_END_MONTH,
    OPEN_SOURCE_LOAD_COL,
    OPEN_SOURCE_PRICE_COL,
    OPEN_SOURCE_PV_COL,
    OPEN_SOURCE_SHEET,
    OPEN_SOURCE_START_MONTH,
)
from scheduling_ui import battery_editor, build_four_panel_chart, solver_opts_editor


def import_forecasts_flow() -> Optional[Tuple[pd.DataFrame, list[dict], dict]]:
    st.subheader("Forecast-based (deterministic) approach")
    st.markdown(
        "*Provide PV generation and load forecasts, and electricity prices, for the next day.*"
    )
    uploaded = st.file_uploader(
        "Upload CSV file (columns: "
        + ", ".join(DETERM_REQUIRED_COLS)
        + ", Date (date-time, optional))",
        type=["csv"],
        key="forecast_upl",
    )
    if uploaded is None:
        st.info("Upload a forecasts CSV file to continue.")
        return None

    forecasts_df = pd.read_csv(uploaded)
    with st.expander("Batteries", expanded=False):
        batteries = battery_editor(key_prefix="det")
    with st.expander("Solver configuration", expanded=False):
        opts = solver_opts_editor(key_prefix="det")

    if batteries is None or opts is None:
        st.info("Fix validation errors above to continue.")
        return None
    return forecasts_df, batteries, opts


def import_history_flow() -> (
    Optional[Tuple[pd.DataFrame, pd.DataFrame, list[dict], dict, Optional[dict]]]
):
    st.subheader("History-based (stochastic) approach")
    st.markdown(
        "*Provide PV generation and load data from immediate past. Provide electricity prices for the next day.*"
    )

    hist_u = st.file_uploader(
        "Upload history CSV (columns: "
        + ", ".join(HIST_REQUIRED_COLS)
        + ", Date (date-time, optional))",
        type=["csv"],
        key="hist_upl",
    )
    ahead_u = st.file_uploader(
        "Upload ahead prices CSV (columns: "
        + ", ".join(AHEAD_REQUIRED_COLS)
        + ", Date (date-time, optional))",
        type=["csv"],
        key="ahead_upl",
    )
    if hist_u is None or ahead_u is None:
        st.info("Upload both history and ahead files to continue.")
        return None

    hist_df = pd.read_csv(hist_u)
    ahead_df = pd.read_csv(ahead_u)

    controls = _stochastic_controls(key_prefix="stoch")
    if controls is None:
        return None
    batteries, opts, override = controls

    return hist_df, ahead_df, batteries, opts, override


@st.cache_data(show_spinner=False)
def _load_open_source_dataset() -> pd.DataFrame:
    raw_df = pd.read_excel(OPEN_SOURCE_DATASET_PATH, sheet_name=OPEN_SOURCE_SHEET)
    renamed_df = raw_df.rename(
        columns={
            OPEN_SOURCE_DATE_COL: "Date",
            OPEN_SOURCE_PV_COL: "pv",
            OPEN_SOURCE_LOAD_COL: "load",
            OPEN_SOURCE_PRICE_COL: "import_price",
        }
    )
    required_cols = ["Date", "pv", "load", "import_price"]
    missing = [col for col in required_cols if col not in renamed_df.columns]
    if missing:
        raise ValueError(f"Dataset missing required columns: {missing}")

    data_df = renamed_df[required_cols].copy()
    data_df["Date"] = pd.to_datetime(data_df["Date"], errors="coerce")
    data_df.dropna(subset=["Date", "pv", "load", "import_price"], inplace=True)

    data_df.sort_values("Date", inplace=True)
    data_df.reset_index(drop=True, inplace=True)
    return data_df


def _stochastic_controls(
    key_prefix: str,
) -> Optional[Tuple[list[dict], dict, Optional[dict]]]:
    st.subheader("Inputs and Options")
    with st.expander("Batteries", expanded=False):
        batteries = battery_editor(key_prefix=key_prefix)
    with st.expander("Solver opts", expanded=False):
        opts = solver_opts_editor(key_prefix=key_prefix)

    if batteries is None or opts is None:
        st.info("Fix validation errors above to continue.")
        return None

    # st.subheader("Champion policy override (optional)")
    with st.expander("Override champion policy (optional)", expanded=False):
        override: Optional[dict[str, float | int]] = {}
        if st.checkbox("Enable override", key=f"{key_prefix}_enable_override"):
            override["history_days"] = st.number_input(
                "history_days",
                min_value=1,
                value=3,
                key=f"{key_prefix}_history_days",
            )
            override["num_scenarios"] = st.number_input(
                "num_scenarios",
                min_value=1,
                value=3,
                key=f"{key_prefix}_num_scenarios",
            )
            override["pv_coeff"] = st.slider(
                "pv_coeff",
                0.0,
                1.0,
                0.5,
                0.05,
                key=f"{key_prefix}_pv_coeff",
            )
            override["load_coeff"] = 1.0 - float(override["pv_coeff"])
        else:
            override = None

    return batteries, opts, override


def _render_forecast_preview(forecasts_df: pd.DataFrame) -> None:
    st.subheader("Input preview")
    with st.expander("Preview", expanded=True):
        plot_tab, table_tab = st.tabs(["Plot", "Table"])
        with plot_tab:
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
                    go.Scatter(x=x, y=forecasts_df["load"], name="Load"), row=1, col=1
                )
            if "import_price" in forecasts_df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=x, y=forecasts_df["import_price"], name="Import Price"
                    ),
                    row=2,
                    col=1,
                )
            st.plotly_chart(fig, width="stretch")
        with table_tab:
            st.dataframe(forecasts_df.head(300), width="stretch", height=260)


def _render_history_preview(hist_df: pd.DataFrame, ahead_df: pd.DataFrame) -> None:
    st.subheader("Inputs preview")
    with st.expander("Preview", expanded=True):
        plot_tab, table_tab = st.tabs(["Plot", "Table"])
        with plot_tab:
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05
            )
            xh = hist_df["Date"] if "Date" in hist_df.columns else hist_df.index
            xa = ahead_df["Date"] if "Date" in ahead_df.columns else ahead_df.index
            if all(c in hist_df.columns for c in ["pv", "load"]):
                fig.add_trace(
                    go.Scatter(x=xh, y=hist_df["pv"], name="PV (history)"), row=1, col=1
                )
                fig.add_trace(
                    go.Scatter(x=xh, y=hist_df["load"], name="Load (history)"),
                    row=1,
                    col=1,
                )
            if "import_price" in ahead_df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=xa, y=ahead_df["import_price"], name="Import Price (ahead)"
                    ),
                    row=2,
                    col=1,
                )
            st.plotly_chart(fig, width="stretch")
        with table_tab:
            st.write("History (first rows)")
            st.dataframe(hist_df.head(200), width="stretch", height=200)
            st.write("Ahead prices (first rows)")
            st.dataframe(ahead_df.head(200), width="stretch", height=200)


def _render_open_source_overview(data_df: pd.DataFrame) -> None:
    st.subheader("Open-source dataset preview (April–December)")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06)
    fig.add_trace(go.Scatter(x=data_df["Date"], y=data_df["pv"], name="PV"), row=1, col=1)
    fig.add_trace(
        go.Scatter(x=data_df["Date"], y=data_df["load"], name="Consumption"),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=data_df["Date"], y=data_df["import_price"], name="Import Price"),
        row=2,
        col=1,
    )
    st.plotly_chart(fig, width="stretch")


def render_scheduling_tabs() -> None:
    det_tab, stoch_tab, explore_tab = st.tabs(
        ["Forecast-based", "History–based", "Explore open-source data"]
    )

    with det_tab:
        det_inputs = import_forecasts_flow()
        if det_inputs is not None:
            forecasts_df, batteries, opts = det_inputs
            _render_forecast_preview(forecasts_df)
            if st.button("Run scheduling", key="run_det"):
                with st.spinner("Calling API... (up to 5 minutes)"):
                    try:
                        output_df = call_deterministic_api(
                            batteries, forecasts_df, opts.get("timestep_hours")
                        )
                    except Exception as exc:
                        st.error(str(exc))
                        st.stop()
                st.success("Completed.")
                with st.expander("Schedule output", expanded=True):
                    out_plot, out_table = st.tabs(["Plot", "Table"])
                    with out_plot:
                        chart = build_four_panel_chart(forecasts_df, output_df)
                        st.plotly_chart(chart, width="stretch")
                    with out_table:
                        st.dataframe(output_df, width="stretch", height=320)

    with stoch_tab:
        if "champion_health_checked" not in st.session_state:
            st.session_state["champion_health_checked"] = False
        if "champion_health_ready" not in st.session_state:
            st.session_state["champion_health_ready"] = None

        check_now = st.button("Check health", key="check_champion_health")
        if check_now:
            with st.spinner("Checking champion policy on server..."):
                st.session_state["champion_health_ready"] = is_champion_healthy()
                st.session_state["champion_health_checked"] = True

        champion_ready = st.session_state["champion_health_ready"]

        if champion_ready is None:
            st.info("Click 'Check health' to verify server readiness.")
        elif not champion_ready:
            st.warning(
                "Champion policy is not configured on the server. This service is unavailable."
            )
        else:
            stoch_inputs = import_history_flow()
            if stoch_inputs is not None:
                hist_df, ahead_df, batteries, opts, override = stoch_inputs
                _render_history_preview(hist_df, ahead_df)
                if st.button("Run scheduling", key="run_stoch"):
                    with st.spinner("Calling API... (up to 5 minutes)"):
                        try:
                            output_df = call_stochastic_api(
                                batteries,
                                hist_df,
                                ahead_df,
                                override,
                                opts.get("timestep_hours"),
                            )
                        except Exception as exc:
                            st.error(str(exc))
                            st.stop()
                    st.success("Completed.")
                    with st.expander("Schedule output", expanded=True):
                        out_plot, out_table = st.tabs(["Plot", "Table"])
                        with out_plot:
                            chart = build_four_panel_chart(ahead_df.copy(), output_df)
                            st.plotly_chart(chart, width="stretch")
                        with out_table:
                            st.dataframe(output_df, width="stretch", height=320)

    with explore_tab:
        st.markdown(
            "*Select a day in the open-source dataset. Corresponding history and ahead inputs are automatically derived.*"
        )

        try:
            data_df = _load_open_source_dataset()
        except Exception as exc:
            st.error(f"Failed to load dataset: {exc}")
            return

        if data_df.empty:
            st.warning("No data available for the configured April–December window.")
            return

        display_df = data_df[
        data_df["Date"].dt.month.between(OPEN_SOURCE_START_MONTH, OPEN_SOURCE_END_MONTH)
        ]
        _render_open_source_overview(display_df)

        available_days = sorted(display_df["Date"].dt.date.unique())
        selected_day = st.date_input(
            "Select day for day-ahead scheduling",
            value=available_days[0],
            min_value=available_days[0],
            max_value=available_days[-1],
            key="open_source_selected_day",
        )

        day_start = pd.Timestamp(selected_day)
        day_end = day_start + pd.Timedelta(days=1)

        if "explore_champion_health_ready" not in st.session_state:
            st.session_state["explore_champion_health_ready"] = None
        if st.button("Check health", key="check_champion_health_explore"):
            with st.spinner("Checking champion policy on server..."):
                st.session_state["explore_champion_health_ready"] = is_champion_healthy()

        champion_ready = st.session_state["explore_champion_health_ready"]
        if champion_ready is None:
            st.info("Click 'Check health' to verify server readiness.")
            return
        if not champion_ready:
            st.warning(
                "Champion policy is not configured on the server. Stochastic service is unavailable."
            )
            return

        controls = _stochastic_controls(key_prefix="open")
        if controls is None:
            return
        batteries, opts, override = controls

        # Determine history_days from champion policy or override
        if os.path.exists(CHAMPION_POLICY_PATH):
            champion_spec = json.load(open(CHAMPION_POLICY_PATH, "r", encoding="utf-8"))
            history_days = champion_spec["history_days"]
        else:
            history_days = 3
        if override and "history_days" in override:
            history_days = int(override["history_days"])

        history_start = day_start - pd.Timedelta(days=history_days)
        history_df = data_df[(data_df["Date"] >= history_start) & (data_df["Date"] < day_start)][
            ["Date"] + HIST_REQUIRED_COLS
        ].copy()
        ahead_df = data_df[(data_df["Date"] >= day_start) & (data_df["Date"] < day_end)][
            ["Date"] + AHEAD_REQUIRED_COLS
        ].copy()

        if ahead_df.empty:
            st.error("No ahead prices found for the selected date in the open-source dataset.")
            return
        if history_df.empty:
            st.error(
                "Not enough history data before selected date. Try a later date or lower history_days in override."
            )
            return

        _render_history_preview(history_df, ahead_df)

        if st.button("Run scheduling", key="run_open_source"):
            with st.spinner("Calling API... (up to 5 minutes)"):
                try:
                    output_df = call_stochastic_api(
                        batteries,
                        history_df,
                        ahead_df,
                        override,
                        opts.get("timestep_hours"),
                    )
                except Exception as exc:
                    st.error(str(exc))
                    st.stop()
            st.success("Completed.")
            with st.expander("Schedule output", expanded=True):
                out_plot, out_table = st.tabs(["Plot", "Table"])
                with out_plot:
                    chart = build_four_panel_chart(ahead_df.copy(), output_df)
                    st.plotly_chart(chart, width="stretch")
                with out_table:
                    st.dataframe(output_df, width="stretch", height=320)
