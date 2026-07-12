"""Main scheduling UI orchestration and tab rendering."""

from __future__ import annotations

import json
import os
from typing import Optional, Tuple

import pandas as pd
import streamlit as st
from scheduling_analytics import render_schedule_analytics
from scheduling_api import (
    call_deterministic_api,
    call_stochastic_api,
    is_champion_healthy,
)
from scheduling_config import (
    AHEAD_REQUIRED_COLS,
    CHAMPION_POLICY_PATH,
    HIST_REQUIRED_COLS,
    OPEN_SOURCE_DATASET_INFO,
    OPEN_SOURCE_END_MONTH,
    OPEN_SOURCE_START_MONTH,
)
from scheduling_flows import (
    import_forecasts_flow,
    import_history_flow,
    load_open_source_dataset,
    render_forecast_preview,
    render_history_preview,
    render_open_source_overview,
)
from scheduling_ui import build_four_panel_chart, solver_opts_editor


def _display_api_error(exc: Exception) -> None:
    """Display user-friendly API error messages."""
    err_text = str(exc).lower()
    if "timeout" in err_text:
        st.error("Request timed out while calling the API. Please try again.")
    elif "connection" in err_text or "refused" in err_text:
        st.error(
            "Could not connect to the API service. Please check if the backend is running."
        )
    else:
        st.error(f"Scheduling failed: {exc}")


def _stochastic_controls(
    key_prefix: str,
    batteries: Optional[list[dict]],
    show_timestep: bool,
    collapse_above: bool,
) -> Optional[Tuple[list[dict], dict, Optional[dict]]]:
    """Render options and override controls for stochastic scheduling."""
    with st.expander("Options", expanded=not collapse_above):
        if show_timestep:
            st.info(
                "Warning: `Date` column missing in one or both files, assuming data belongs to the next day. Set correct `timestep_hours` in the options."
            )
            opts = solver_opts_editor(key_prefix=key_prefix)
        else:
            opts = {"timestep_hours": None}

        override: Optional[dict[str, float | int]] = {}
        if st.checkbox(
            "Override champion policy (optional) for this run.",
            key=f"{key_prefix}_enable_override",
        ):
            override["history_days"] = st.number_input(
                "history_days",
                min_value=1,
                value=3,
                key=f"{key_prefix}_history_days",
            )
            override["num_scenarios"] = st.number_input(
                "num_scenarios",
                min_value=1,
                max_value=override["history_days"],
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

    if batteries is None or opts is None:
        st.info("Fix validation errors above to continue.")
        return None

    return batteries, opts, override


def _require_champion_health(key_prefix: str) -> bool:
    """Check and display champion policy health status."""
    ready_key = "champion_health_ready"
    if ready_key not in st.session_state:
        st.session_state[ready_key] = None

    button_col, status_col = st.columns([1, 3], vertical_alignment="center")
    with button_col:
        check_now = st.button(
            "Check health", key=f"{key_prefix}_check_champion_health"
        )
        if check_now:
            with st.spinner("Checking champion policy on server..."):
                st.session_state[ready_key] = is_champion_healthy()

    champion_ready = st.session_state[ready_key]
    if champion_ready is None:
        status_text = "ℹ️ Health check: Not checked."
    elif champion_ready:
        status_text = "✅ Health check: Champion policy is available."
    else:
        status_text = "⚠️ Health check: Champion policy is unavailable."

    with status_col:
        st.markdown(status_text)

    if champion_ready is None:
        return False
    if not champion_ready:
        return False
    return True


def render_scheduling_tabs(sidebar_batteries: Optional[list[dict]]) -> None:
    """Render all three scheduling tabs with inputs, run controls, and results."""
    det_tab, stoch_tab, explore_tab = st.tabs(
        ["Forecast-based", "History–based", "Explore open-source data"]
    )

    # ==================== DETERMINISTIC TAB ====================
    with det_tab:
        det_collapse_above = st.session_state.get("det_collapse_above", False)
        det_inputs = import_forecasts_flow(
            sidebar_batteries=sidebar_batteries,
            collapse_above=det_collapse_above,
        )
        if det_inputs is not None:
            forecasts_df, batteries, opts = det_inputs
            render_forecast_preview(
                forecasts_df=forecasts_df,
                collapse_above=det_collapse_above,
            )
            run_col, status_col = st.columns([1, 3], vertical_alignment="center")
            with run_col:
                run_det = st.button("Run scheduling", key="run_det")
            with status_col:
                det_status_placeholder = st.empty()
                det_status = st.session_state.get("det_run_status", "")
                if det_status:
                    det_status_placeholder.markdown(det_status)

            if run_det:
                st.session_state["det_collapse_above"] = True
                st.session_state["det_run_pending"] = True
                st.rerun()

            if st.session_state.get("det_run_pending", False):
                st.session_state["det_run_pending"] = False
                det_status_placeholder.markdown("⏳ Running schedule...")
                with st.spinner("Calling API... (up to 5 minutes)"):
                    try:
                        output_df = call_deterministic_api(
                            batteries, forecasts_df, opts.get("timestep_hours")
                        )
                    except Exception as exc:
                        st.session_state["det_run_status"] = "❌ Failed"
                        _display_api_error(exc)
                        st.stop()
                st.session_state["det_run_status"] = "✅ Completed"
                det_status_placeholder.markdown(st.session_state["det_run_status"])
                with st.expander("Schedule output", expanded=True):
                    out_plot, out_analytics, out_table = st.tabs(
                        ["Plot", "Analytics", "Table"]
                    )
                    with out_plot:
                        chart = build_four_panel_chart(forecasts_df, output_df)
                        st.plotly_chart(chart, width='stretch')
                    with out_analytics:
                        render_schedule_analytics(
                            input_df=forecasts_df,
                            output_df=output_df,
                            batteries=batteries,
                            timestep_hours_hint=opts.get("timestep_hours"),
                        )
                    with out_table:
                        st.dataframe(
                            output_df, width='stretch', height=320
                        )
                st.session_state["det_collapse_above"] = False
            else:
                det_status_placeholder.markdown("")

    # ==================== STOCHASTIC TAB ====================
    with stoch_tab:
        stoch_collapse_above = st.session_state.get("stoch_collapse_above", False)
        if _require_champion_health(key_prefix="stoch"):
            stoch_inputs = import_history_flow(
                sidebar_batteries=sidebar_batteries,
                collapse_above=stoch_collapse_above,
            )
            if stoch_inputs is not None:
                hist_df, ahead_df, batteries, opts, override = stoch_inputs
                render_history_preview(
                    hist_df=hist_df,
                    ahead_df=ahead_df,
                    collapse_above=stoch_collapse_above,
                )
                run_col, status_col = st.columns([1, 3], vertical_alignment="center")
                with run_col:
                    run_stoch = st.button("Run scheduling", key="run_stoch")
                with status_col:
                    stoch_status_placeholder = st.empty()
                    stoch_status = st.session_state.get("stoch_run_status", "")
                    if stoch_status:
                        stoch_status_placeholder.markdown(stoch_status)

                if run_stoch:
                    st.session_state["stoch_collapse_above"] = True
                    st.session_state["stoch_run_pending"] = True
                    st.rerun()

                if st.session_state.get("stoch_run_pending", False):
                    st.session_state["stoch_run_pending"] = False
                    stoch_status_placeholder.markdown("⏳ Running schedule...")
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
                            st.session_state["stoch_run_status"] = "❌ Failed"
                            _display_api_error(exc)
                            st.stop()
                    st.session_state["stoch_run_status"] = "✅ Completed"
                    stoch_status_placeholder.markdown(
                        st.session_state["stoch_run_status"]
                    )
                    with st.expander("Schedule output", expanded=True):
                        out_plot, out_analytics, out_table = st.tabs(
                            ["Plot", "Analytics", "Table"]
                        )
                        with out_plot:
                            chart = build_four_panel_chart(ahead_df.copy(), output_df)
                            st.plotly_chart(chart, width='stretch')
                        with out_analytics:
                            render_schedule_analytics(
                                input_df=ahead_df,
                                output_df=output_df,
                                batteries=batteries,
                                timestep_hours_hint=opts.get("timestep_hours"),
                            )
                        with out_table:
                            st.dataframe(
                                output_df, width='stretch', height=320
                            )
                    st.session_state["stoch_collapse_above"] = False
                else:
                    stoch_status_placeholder.markdown("")

    # ==================== EXPLORE TAB ====================
    with explore_tab:
        open_collapse_above = st.session_state.get("open_collapse_above", False)
        if _require_champion_health(key_prefix="explore"):
            st.subheader(
                "Explore open-source dataset (both approaches)",
                help=OPEN_SOURCE_DATASET_INFO,
            )
            st.markdown(
                "And select a date in the open-source dataset. Corresponding history and ahead inputs are automatically selected."
            )

            try:
                data_df = load_open_source_dataset()
            except Exception as exc:
                st.error(f"Failed to load dataset: {exc}")
                return

            if data_df.empty:
                st.warning(
                    "No data available for the configured April–December window."
                )
                return

            display_df = data_df[
                data_df["Date"].dt.month.between(
                    OPEN_SOURCE_START_MONTH, OPEN_SOURCE_END_MONTH
                )
            ]
            render_open_source_overview(
                data_df=display_df,
                collapse_above=open_collapse_above,
            )

            available_days = sorted(display_df["Date"].dt.date.unique())
            selected_day = st.date_input(
                "Select date for which to generate schedule",
                value=available_days[0],
                min_value=available_days[0],
                max_value=available_days[-1],
                key="open_source_selected_day",
            )

            day_start = pd.Timestamp(selected_day)
            day_end = day_start + pd.Timedelta(days=1)

            controls = _stochastic_controls(
                key_prefix="open",
                batteries=sidebar_batteries,
                show_timestep=False,
                collapse_above=open_collapse_above,
            )
            if controls is None:
                return
            batteries, opts, override = controls

            # Determine history_days from champion policy or override
            if os.path.exists(CHAMPION_POLICY_PATH):
                champion_spec = json.load(
                    open(CHAMPION_POLICY_PATH, "r", encoding="utf-8")
                )
                history_days = champion_spec["history_days"]
            else:
                history_days = 3
            if override and "history_days" in override:
                history_days = int(override["history_days"])

            # Trim history data to the determined number of days before the selected day
            history_start = day_start - pd.Timedelta(days=history_days)
            history_df = data_df[
                (data_df["Date"] >= history_start) & (data_df["Date"] < day_start)
            ][["Date"] + HIST_REQUIRED_COLS].copy()
            ahead_df = data_df[
                (data_df["Date"] >= day_start) & (data_df["Date"] < day_end)
            ][["Date"] + AHEAD_REQUIRED_COLS].copy()

            if ahead_df.empty:
                st.error(
                    "No ahead prices found for the selected date in the open-source dataset."
                )
                return
            if history_df.empty:
                st.error(
                    "Not enough history data before selected date. Try a later date or lower history_days in override."
                )
                return

            render_history_preview(
                hist_df=history_df,
                ahead_df=ahead_df,
                collapse_above=open_collapse_above,
            )

            run_col, status_col = st.columns([1, 3], vertical_alignment="center")
            with run_col:
                run_open_source = st.button("Run scheduling", key="run_open_source")
            with status_col:
                open_status_placeholder = st.empty()
                open_status = st.session_state.get("open_run_status", "")
                if open_status:
                    open_status_placeholder.markdown(open_status)

            if run_open_source:
                st.session_state["open_collapse_above"] = True
                st.session_state["open_run_pending"] = True
                st.rerun()

            if st.session_state.get("open_run_pending", False):
                st.session_state["open_run_pending"] = False
                open_status_placeholder.markdown("⏳ Running schedule...")
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
                        st.session_state["open_run_status"] = "❌ Failed"
                        _display_api_error(exc)
                        st.stop()
                st.session_state["open_run_status"] = "✅ Completed"

                open_status_placeholder.markdown(st.session_state["open_run_status"])
                with st.expander("Schedule output", expanded=True):
                    out_plot, out_analytics, out_table = st.tabs(
                        ["Plot", "Analytics", "Table"]
                    )
                    with out_plot:
                        chart = build_four_panel_chart(ahead_df.copy(), output_df)
                        st.plotly_chart(chart, width='stretch')
                    with out_analytics:
                        render_schedule_analytics(
                            input_df=ahead_df,
                            output_df=output_df,
                            batteries=batteries,
                            timestep_hours_hint=opts.get("timestep_hours"),
                        )
                    with out_table:
                        st.dataframe(
                            output_df, width='stretch', height=320
                        )
                st.session_state["open_collapse_above"] = False
            else:
                open_status_placeholder.markdown("")
