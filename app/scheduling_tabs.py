"""Main scheduling UI orchestration and tab rendering."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional, Tuple

import pandas as pd
import streamlit as st
from scheduling_analytics import render_schedule_analytics, render_comparative_analytics
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
from scheduling_ui import build_output_panel_chart, solver_opts_editor

from esms.models.battery import BATTERY_UNITS


def _tab_state_key(tab_prefix: str, suffix: str) -> str:
    """Build consistent session-state keys for a tab."""
    return f"{tab_prefix}_{suffix}"


def _render_run_controls(button_key: str, status_key: str) -> tuple[bool, Any]:
    """Render run button with inline status and return button click + placeholder."""
    run_col, status_col = st.columns([1, 3], vertical_alignment="center")
    with run_col:
        clicked = st.button("Run scheduling", key=button_key)
    with status_col:
        status_placeholder = st.empty()
        status_text = st.session_state.get(status_key, "")
        if status_text:
            status_placeholder.markdown(status_text)
    return clicked, status_placeholder


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


def _inputs_signature(*args: Any) -> str:
    """Create a lightweight signature from input arguments to detect changes.

    DataFrames are hashed by shape + columns (fast, catches file swaps).
    Everything else is stringified.
    """
    parts: list[str] = []
    for arg in args:
        if isinstance(arg, pd.DataFrame):
            parts.append(f"df:{arg.shape}:{list(arg.columns)}")
        else:
            parts.append(str(arg))
    return "|".join(parts)


def _clear_if_inputs_changed(tab_prefix: str, *args: Any) -> None:
    """Clear stored output + status if any input changed since last run."""
    sig_key = _tab_state_key(tab_prefix, "input_sig")
    output_key = _tab_state_key(tab_prefix, "output_df")
    status_key = _tab_state_key(tab_prefix, "run_status")

    current_sig = _inputs_signature(*args)
    if st.session_state.get(sig_key) != current_sig:
        st.session_state[output_key] = None
        st.session_state[status_key] = ""
    st.session_state[sig_key] = current_sig


def _execute_pending_run(
    pending_key: str,
    status_key: str,
    status_placeholder: Any,
    output_key: str,
    run_call: Callable[[], Any],
) -> Any:
    """Execute pending run or return stored output.

    On pending: runs the API call, stores result in session_state.
    Otherwise: returns stored output if it exists (survives non-run reruns).
    """
    if st.session_state.get(pending_key, False):
        st.session_state[pending_key] = False
        status_placeholder.markdown("⏳ Running schedule...")
        with st.spinner("Calling API... (up to 5 minutes)"):
            try:
                output_df = run_call()
            except Exception as exc:
                st.session_state[status_key] = "❌ Failed"
                st.session_state[output_key] = None
                _display_api_error(exc)
                st.stop()
        st.session_state[status_key] = "✅ Completed"
        st.session_state[output_key] = output_df

    output_df = st.session_state.get(output_key)
    if output_df is not None:
        status_text = st.session_state.get(status_key, "")
        if status_text:
            status_placeholder.markdown(status_text)
    else:
        status_placeholder.markdown("")
    return output_df


def _render_battery_download(
    output_df: pd.DataFrame, batteries: list[dict], key_suffix: str
) -> None:
    """Render a download button for a CSV containing only battery columns."""
    battery_colname_suffixes = ("charge", "discharge", "soc")

    battery_cols: list[str] = []
    for bat in batteries:
        bid = str(bat["id"])
        for suffix in battery_colname_suffixes:
            col = f"{bid}_{suffix}"
            if col in output_df.columns:
                battery_cols.append(col)

    if not battery_cols:
        return

    download_df = output_df[battery_cols].copy()

    column_units = {
        "charge": f"{BATTERY_UNITS['max_charge']}",
        "discharge": f"{BATTERY_UNITS['max_discharge']}",
        "soc": f"{BATTERY_UNITS['capacity']}",
    }
    download_df.rename(
        columns={
            col: f"{col}_{column_units[col.split('_')[-1]]}" for col in battery_cols
        },
        inplace=True,
    )

    date = output_df.index[0].strftime("%Y%m%d")
    st.download_button(
        label="Download battery schedule (CSV)",
        data=download_df.to_csv(index=True),
        file_name=f"battery_schedule_{date}.csv",
        mime="text/csv",
        key=f"download_battery_{key_suffix}",
    )


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
            "Override champion policy for this run (optional).",
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
        check_now = st.button("Check health", key=f"{key_prefix}_check_champion_health")
        if check_now:
            with st.spinner("Checking champion policy on server, could take a few minutes..."):
                st.session_state[ready_key] = is_champion_healthy()

    champion_ready = st.session_state[ready_key]
    if champion_ready is None:
        status_text = "ℹ️ Health check: Not checked."
    elif champion_ready:
        status_text = "✅ Health check: Champion policy is available."
    else:
        status_text = "⚠️ Health check: Backend is taking longer than expected to wake up, please try again in 2 mins."

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
        det_collapse_key = _tab_state_key("det", "collapse_above")
        det_pending_key = _tab_state_key("det", "run_pending")
        det_status_key = _tab_state_key("det", "run_status")

        det_collapse_above = st.session_state.get(det_collapse_key, False)
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
            run_det, det_status_placeholder = _render_run_controls(
                button_key="run_det",
                status_key=det_status_key,
            )

            if run_det:
                st.session_state[det_collapse_key] = True
                st.session_state[det_pending_key] = True
                st.rerun()

            _clear_if_inputs_changed("det", forecasts_df, batteries, opts)
            output_df = _execute_pending_run(
                pending_key=det_pending_key,
                status_key=det_status_key,
                status_placeholder=det_status_placeholder,
                output_key=_tab_state_key("det", "output_df"),
                run_call=lambda: call_deterministic_api(
                    batteries, forecasts_df, opts.get("timestep_hours")
                ),
            )
            if output_df is not None:
                with st.expander("Schedule output", expanded=True):
                    _render_battery_download(output_df, batteries, key_suffix="det")
                    out_plot, out_analytics, out_table = st.tabs(
                        ["Plots", "Analytics", "Table"]
                    )
                    with out_plot:
                        chart = build_output_panel_chart(
                            forecasts_df,
                            output_df,
                            batteries=batteries,
                            pv_label="Provided PV forecast",
                            load_label="Provided Load forecast",
                        )
                        st.plotly_chart(chart, width="stretch")
                    with out_analytics:
                        render_schedule_analytics(
                            input_df=forecasts_df,
                            output_df=output_df,
                            batteries=batteries,
                            timestep_hours_hint=opts.get("timestep_hours"),
                        )
                    with out_table:
                        st.dataframe(output_df, width="stretch", height=320)
                st.session_state[det_collapse_key] = False

    # ==================== STOCHASTIC TAB ====================
    with stoch_tab:
        stoch_collapse_key = _tab_state_key("stoch", "collapse_above")
        stoch_pending_key = _tab_state_key("stoch", "run_pending")
        stoch_status_key = _tab_state_key("stoch", "run_status")

        stoch_collapse_above = st.session_state.get(stoch_collapse_key, False)
        if _require_champion_health(key_prefix="stoch"):
            stoch_inputs = import_history_flow(
                sidebar_batteries=sidebar_batteries,
                collapse_above=stoch_collapse_above,
                stochastic_controls_renderer=_stochastic_controls,
            )
            if stoch_inputs is not None:
                hist_df, ahead_df, batteries, opts, override = stoch_inputs
                render_history_preview(
                    hist_df=hist_df,
                    ahead_df=ahead_df,
                    collapse_above=stoch_collapse_above,
                )
                run_stoch, stoch_status_placeholder = _render_run_controls(
                    button_key="run_stoch",
                    status_key=stoch_status_key,
                )

                if run_stoch:
                    st.session_state[stoch_collapse_key] = True
                    st.session_state[stoch_pending_key] = True
                    st.rerun()

                _clear_if_inputs_changed(
                    "stoch", hist_df, ahead_df, batteries, opts, override
                )
                output_df = _execute_pending_run(
                    pending_key=stoch_pending_key,
                    status_key=stoch_status_key,
                    status_placeholder=stoch_status_placeholder,
                    output_key=_tab_state_key("stoch", "output_df"),
                    run_call=lambda: call_stochastic_api(
                        batteries,
                        hist_df,
                        ahead_df,
                        override,
                        opts.get("timestep_hours"),
                    ),
                )
                if output_df is not None:
                    with st.expander("Schedule output", expanded=True):
                        _render_battery_download(
                            output_df, batteries, key_suffix="stoch"
                        )
                        out_plot, out_analytics, out_table = st.tabs(
                            ["Plots", "Analytics", "Table"]
                        )
                        with out_plot:
                            chart = build_output_panel_chart(
                                ahead_df.copy(),
                                output_df,
                                batteries=batteries,
                                pv_label="Expected PV (from history)",
                                load_label="Expected Load (from history)",
                            )
                            st.plotly_chart(chart, width="stretch")
                        with out_analytics:
                            render_schedule_analytics(
                                input_df=ahead_df,
                                output_df=output_df,
                                batteries=batteries,
                                timestep_hours_hint=opts.get("timestep_hours"),
                            )
                        with out_table:
                            st.dataframe(output_df, width="stretch", height=320)
                    st.session_state[stoch_collapse_key] = False

    # ==================== EXPLORE TAB ====================
    with explore_tab:
        open_collapse_key = _tab_state_key("open", "collapse_above")
        open_pending_key = _tab_state_key("open", "run_pending")
        open_status_key = _tab_state_key("open", "run_status")

        open_collapse_above = st.session_state.get(open_collapse_key, False)
        if _require_champion_health(key_prefix="explore"):
            st.subheader(
                "Explore open-source dataset (both approaches)",
                help=OPEN_SOURCE_DATASET_INFO,
            )
            st.markdown(
                "And select a date, corresponding history and prices are automatically selected."
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

            available_days = sorted(display_df["Date"].dt.date.unique())
            render_open_source_overview(
                data_df=display_df,
                collapse_above=st.session_state.get("open_source_selected_day")
                is not None,
            )

            selected_day = st.date_input(
                "Select date for which to generate/optimize schedule",
                value=None,
                min_value=available_days[0],
                max_value=available_days[-1],
                key="open_source_selected_day",
            )
            if selected_day is None:
                st.info(
                    "Pick a date above to load the corresponding inputs and options."
                )
                return

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
                with open(CHAMPION_POLICY_PATH, "r", encoding="utf-8") as file:
                    champion_spec = json.load(file)
                history_days = champion_spec["history_days"]
            else:
                history_days = 3
            if override and "history_days" in override:
                history_days = int(override["history_days"])

            # Trim history data to the determined number of days before the selected day
            history_start = day_start - pd.Timedelta(days=history_days)
            history_df = data_df[
                (data_df["Date"] >= history_start) & (data_df["Date"] < day_start)
            ][["Date"] + HIST_REQUIRED_COLS + AHEAD_REQUIRED_COLS].copy()
            ahead_df = data_df[
                (data_df["Date"] >= day_start) & (data_df["Date"] < day_end)
            ][["Date"] + HIST_REQUIRED_COLS + AHEAD_REQUIRED_COLS].copy()

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
                plot_all=True,
                collapse_above=open_collapse_above,
            )

            run_open_source, open_status_placeholder = _render_run_controls(
                button_key="run_open_source",
                status_key=open_status_key,
            )

            if run_open_source:
                st.session_state[open_collapse_key] = True
                st.session_state[open_pending_key] = True
                st.rerun()

            _clear_if_inputs_changed(
                "open", history_df, ahead_df, batteries, opts, override
            )

            def _run_both_optimizations() -> tuple[pd.DataFrame, pd.DataFrame]:
                """Run both perfect foresight (deterministic) and stochastic optimizations."""
                ts = opts.get("timestep_hours")
                det_output = call_deterministic_api(batteries, ahead_df, ts)
                stoch_output = call_stochastic_api(
                    batteries, history_df, ahead_df, override, ts
                )
                return det_output, stoch_output

            output_dfs = _execute_pending_run(
                pending_key=open_pending_key,
                status_key=open_status_key,
                status_placeholder=open_status_placeholder,
                output_key=_tab_state_key("open", "output_df"),
                run_call=_run_both_optimizations,
            )
            if output_dfs is not None:
                det_output, stoch_output = output_dfs
                with st.expander("Schedule output", expanded=True):
                    # _render_battery_download(
                    #     stoch_output, batteries, key_suffix="open_stoch"
                    # )
                    out_pf_plot, out_stoch_plot, out_analytics, out_table = st.tabs(
                        ["Perfect Forecasts/Foresight - Plots", "Scheduling based on history (stochastic) - Plots", "Analytics", "Table"]
                    )
                    with out_pf_plot:
                        chart_pf = build_output_panel_chart(
                            ahead_df.copy(),
                            det_output,
                            batteries=batteries,
                            pv_label="PV (perfect foresight)",
                            load_label="Load (perfect foresight)",
                        )
                        st.plotly_chart(chart_pf, width="stretch")
                    with out_stoch_plot:
                        chart_stoch = build_output_panel_chart(
                                ahead_df.copy(),
                                stoch_output,
                                batteries=batteries,
                                pv_label="Expected PV (from history)",
                                load_label="Expected Load (from history)",
                            )
                        st.plotly_chart(chart_stoch, width="stretch")

                    with out_analytics:
                        render_comparative_analytics(
                            actual_df=ahead_df,
                            det_output=det_output,
                            stoch_output=stoch_output,
                            batteries=batteries,
                            timestep_hours_hint=opts.get("timestep_hours"),
                        )
                    with out_table:
                        st.write("Perfect Foresight schedule")
                        st.dataframe(det_output, width="stretch", height=320)
                        st.write("Stochastic (from history) schedule")
                        st.dataframe(stoch_output, width="stretch", height=320)
                st.session_state[open_collapse_key] = False
