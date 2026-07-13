"""Analytics computation and visualization for scheduling results."""

from __future__ import annotations

from typing import Optional
import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from esms.eval import OptimizationCostCalculator
from esms.eval import DeterministicPerformanceCalculator

logger = logging.getLogger(__name__)


def first_present(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Return the first column name from candidates that exists in df."""
    for col in candidates:
        if col in df.columns:
            return col
    return None


def resolve_timestep_hours(df: pd.DataFrame, fallback: Optional[float]) -> float:
    """Infer timestep in hours from Date column or use fallback."""
    if "Date" in df.columns:
        date_series = pd.to_datetime(df["Date"], errors="coerce")
        diffs = date_series.diff().dt.total_seconds().dropna()
        if not diffs.empty:
            median_hours = float(diffs.median() / 3600.0)
            if median_hours > 0:
                return median_hours
    if fallback and fallback > 0:
        return float(fallback)
    return 1.0


def total_battery_flows(
    output_df: pd.DataFrame, batteries: list[dict]
) -> tuple[pd.Series, pd.Series]:
    """Sum all battery charge and discharge columns across all batteries."""
    charge_cols = [f"{b['id']}_charge" for b in batteries]
    discharge_cols = [f"{b['id']}_discharge" for b in batteries]

    missing_charge = [col for col in charge_cols if col not in output_df.columns]
    missing_discharge = [col for col in discharge_cols if col not in output_df.columns]
    if missing_charge:
        logger.warning("Missing charge columns in output: %s", missing_charge)
    if missing_discharge:
        logger.warning("Missing discharge columns in output: %s", missing_discharge)

    present_charge_cols = [col for col in charge_cols if col in output_df.columns]
    present_discharge_cols = [col for col in discharge_cols if col in output_df.columns]

    if present_charge_cols:
        charge_series = output_df[present_charge_cols].sum(axis=1)
    else:
        charge_series = pd.Series(0.0, index=output_df.index)
    if present_discharge_cols:
        discharge_series = output_df[present_discharge_cols].sum(axis=1)
    else:
        discharge_series = pd.Series(0.0, index=output_df.index)

    return charge_series, discharge_series


def render_schedule_analytics(
    input_df: pd.DataFrame,
    output_df: pd.DataFrame,
    batteries: list[dict],
    timestep_hours_hint: Optional[float],
) -> None:
    """Render KPI metrics and decision-quality plots for schedule results."""

    # Resolve column names from deterministic or stochastic outputs
    load_col = first_present(output_df, ["load", "expected_load"])
    pv_col = first_present(output_df, ["pv", "expected_pv"])

    import_price_col = first_present(output_df, ["import_price"])
    export_price_col = first_present(output_df, ["export_price"])

    grid_import_col = first_present(output_df, ["grid_import", "expected_grid_import"])
    grid_export_col = first_present(output_df, ["grid_export", "expected_grid_export"])

    required = [load_col, pv_col, import_price_col, grid_import_col]
    if any(col is None for col in required):
        st.info("Analytics needs load, pv, import_price, and grid_import columns.")
        return

    # Extract and coerce numeric series
    load_series = pd.to_numeric(output_df[load_col], errors="coerce").fillna(0.0)
    pv_series = pd.to_numeric(
        output_df[pv_col],
        errors="coerce",
    ).fillna(0.0)
    import_price_series = pd.to_numeric(
        output_df[import_price_col],
        errors="coerce",
    ).fillna(0.0)
    scheduled_import = pd.to_numeric(
        output_df[grid_import_col], errors="coerce"
    ).fillna(0.0)

    if grid_export_col and grid_export_col in output_df.columns:
        scheduled_export = pd.to_numeric(
            output_df[grid_export_col], errors="coerce"
        ).fillna(0.0)
    else:
        scheduled_export = pd.Series(0.0, index=output_df.index)

    if export_price_col:
        export_price_series = pd.to_numeric(
            output_df[export_price_col],
            errors="coerce",
        ).fillna(0.0)
    else:
        export_price_series = pd.Series(0.0, index=output_df.index)

    timestep_hours = resolve_timestep_hours(output_df, timestep_hours_hint)

    # USING EXISTING CALCULATORS TO COMPUTE COSTS AND KPIS
    data_df = output_df.copy()
    data_df.rename(
        columns={col: col.replace("expected_", "") for col in data_df.columns},
        inplace=True,
    )

    cost_calc = OptimizationCostCalculator(dt_hours=timestep_hours)
    logger.info("Calculating cost breakdown using OptimizationCostCalculator...")
    costs = cost_calc.calculate_from_dataframe(
        data_df,
        degradation_costs={b["id"]: b["degradation_cost"] for b in batteries},
    )

    perf_calc = DeterministicPerformanceCalculator(dt_hours=timestep_hours)
    logger.info(
        "Calculating performance breakdown using DeterministicPerformanceCalculator..."
    )
    performance = perf_calc.calculate_from_dataframe(data_df)

    # Compute baseline (no-battery) series — not available from calculators
    baseline_import = (load_series - pv_series).clip(lower=0.0)
    baseline_export = (pv_series - load_series).clip(lower=0.0)

    baseline_cost_series = (
        baseline_import * import_price_series - baseline_export * export_price_series
    ) * timestep_hours
    scheduled_cost_series = (
        scheduled_import * import_price_series - scheduled_export * export_price_series
    ) * timestep_hours
    for bat in batteries:
        charge_series = output_df[f"{bat['id']}_charge"]
        discharge_series = output_df[f"{bat['id']}_discharge"]
        scheduled_cost_series += (
            charge_series * bat["degradation_cost"] * timestep_hours
        )
        scheduled_cost_series += (
            discharge_series * bat["degradation_cost"] * timestep_hours
        )

    # Baseline KPIs (explicit)
    baseline_cost = float(baseline_cost_series.sum())
    baseline_peak = float(baseline_import.max()) if not baseline_import.empty else 0.0

    # Scheduled KPIs (from calculators)
    scheduled_cost = costs.total_cost
    scheduled_peak = performance.peak_grid_import_kw
    throughput = performance.battery_throughput_kwh
    self_consumption_pct = performance.self_consumption_ratio * 100.0

    # Derived savings KPIs
    savings = baseline_cost - scheduled_cost
    savings_pct = (savings / baseline_cost * 100.0) if baseline_cost != 0 else 0.0
    peak_reduction = baseline_peak - scheduled_peak
    peak_reduction_pct = (
        (peak_reduction / baseline_peak * 100.0) if baseline_peak > 0 else 0.0
    )

    # Render KPI cards
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Scheduled Cost", f"€{scheduled_cost:.2f}")
    k2.metric("Savings vs Baseline", f"€{savings:.2f}", f"{savings_pct:.1f}%")
    k3.metric(
        "Peak Import Reduction",
        f"{peak_reduction:.2f} kW",
        f"{peak_reduction_pct:.1f}%",
    )
    k4.metric("Self-Consumption", f"{self_consumption_pct:.1f}%")

    k5, k6 = st.columns(2)
    k5.metric("Battery Throughput", f"{throughput:.2f} kWh")
    k6.metric("Battery Degradation Cost", f"€{costs.degradation_cost:.2f}")

    # Render plots
    x_axis = output_df["Date"] if "Date" in output_df.columns else output_df.index
    if "Date" in output_df.columns:
        date_axis = pd.to_datetime(output_df["Date"], errors="coerce")
    else:
        date_axis = pd.Series(output_df.index)

    # Get battery flows from renamed data_df for price-duration plot
    charge_series, discharge_series = total_battery_flows(data_df, batteries)

    c1, c2 = st.columns(2)
    with c1:
        fig_grid = go.Figure()
        fig_grid.add_trace(
            go.Scatter(
                x=x_axis, y=baseline_import, name="Baseline Grid Import", mode="lines"
            )
        )
        fig_grid.add_trace(
            go.Scatter(
                x=x_axis, y=scheduled_import, name="Scheduled Grid Import", mode="lines"
            )
        )
        fig_grid.update_layout(
            title="Grid Import: Baseline vs Scheduled", margin=dict(t=40, b=20)
        )
        st.plotly_chart(fig_grid, width="stretch")

    with c2:
        duration_df = (
            pd.DataFrame(
                {
                    "price": import_price_series.values,
                    "charge": charge_series.values,
                    "discharge": discharge_series.values,
                }
            )
            .sort_values("price")
            .reset_index(drop=True)
        )
        duration_df["rank"] = range(1, len(duration_df) + 1)
        fig_duration = go.Figure()
        fig_duration.add_trace(
            go.Scatter(
                x=duration_df["rank"],
                y=duration_df["price"],
                name="Import Price",
                mode="lines",
            )
        )
        charge_pts = duration_df[duration_df["charge"] > 0]
        discharge_pts = duration_df[duration_df["discharge"] > 0]
        if not charge_pts.empty:
            fig_duration.add_trace(
                go.Scatter(
                    x=charge_pts["rank"],
                    y=charge_pts["price"],
                    name="Charge",
                    mode="markers",
                    marker=dict(symbol="triangle-up", size=8),
                )
            )
        if not discharge_pts.empty:
            fig_duration.add_trace(
                go.Scatter(
                    x=discharge_pts["rank"],
                    y=discharge_pts["price"],
                    name="Discharge",
                    mode="markers",
                    marker=dict(symbol="triangle-down", size=8),
                )
            )
        fig_duration.update_layout(
            title="Price-Duration with Charge/Discharge Markers",
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig_duration, width="stretch")

    fig_cum = go.Figure()
    fig_cum.add_trace(
        go.Scatter(
            x=date_axis,
            y=baseline_cost_series.cumsum(),
            name="Baseline Cumulative Cost",
            mode="lines",
        )
    )
    fig_cum.add_trace(
        go.Scatter(
            x=date_axis,
            y=scheduled_cost_series.cumsum(),
            name="Scheduled Cumulative Cost",
            mode="lines",
        )
    )
    fig_cum.update_layout(
        title="Cumulative Cost: Baseline vs Scheduled", margin=dict(t=40, b=20)
    )
    st.plotly_chart(fig_cum, width="stretch")
