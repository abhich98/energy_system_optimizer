"""Analytics computation and visualization for scheduling results."""

from __future__ import annotations

from typing import Any, Optional
import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from esms.eval import OptimizationCostCalculator
from esms.eval import DeterministicPerformanceCalculator

from scheduling_config import CHART_COLORS

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


def _compute_schedule_metrics(
    output_df: pd.DataFrame,
    batteries: list[dict],
    timestep_hours: float,
) -> dict:
    """Compute all KPIs and series for a single schedule using existing calculators.

    Returns a dict with: costs, performance, baseline series, scheduled series,
    charge/discharge totals, and timestep.
    """
    load_col = first_present(output_df, ["load", "expected_load"])
    pv_col = first_present(output_df, ["pv", "expected_pv"])
    import_price_col = first_present(output_df, ["import_price"])
    export_price_col = first_present(output_df, ["export_price"])
    grid_import_col = first_present(output_df, ["grid_import", "expected_grid_import"])
    grid_export_col = first_present(output_df, ["grid_export", "expected_grid_export"])

    load_series = pd.to_numeric(output_df[load_col], errors="coerce").fillna(0.0)
    pv_series = pd.to_numeric(output_df[pv_col], errors="coerce").fillna(0.0)
    import_price_series = pd.to_numeric(
        output_df[import_price_col], errors="coerce"
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
            output_df[export_price_col], errors="coerce"
        ).fillna(0.0)
    else:
        export_price_series = pd.Series(0.0, index=output_df.index)

    # Use calculators on renamed df
    data_df = output_df.copy()
    data_df.rename(
        columns={col: col.replace("expected_", "") for col in data_df.columns},
        inplace=True,
    )

    cost_calc = OptimizationCostCalculator(dt_hours=timestep_hours)
    costs = cost_calc.calculate_from_dataframe(
        data_df,
        degradation_costs={b["id"]: b["degradation_cost"] for b in batteries},
    )

    perf_calc = DeterministicPerformanceCalculator(dt_hours=timestep_hours)
    performance = perf_calc.calculate_from_dataframe(data_df)

    # Baseline (no-battery)
    baseline_import = (load_series - pv_series).clip(lower=0.0)
    baseline_export = (pv_series - load_series).clip(lower=0.0)
    baseline_cost_series = (
        baseline_import * import_price_series - baseline_export * export_price_series
    ) * timestep_hours
    baseline_cost = float(baseline_cost_series.sum())
    baseline_peak = float(baseline_import.max()) if not baseline_import.empty else 0.0

    # Scheduled cost series (explicit, includes degradation)
    scheduled_cost_series = (
        scheduled_import * import_price_series - scheduled_export * export_price_series
    ) * timestep_hours
    for bat in batteries:
        charge_series = output_df[f"{bat['id']}_charge"]
        discharge_series = output_df[f"{bat['id']}_discharge"]
        scheduled_cost_series += charge_series * bat["degradation_cost"] * timestep_hours
        scheduled_cost_series += (
            discharge_series * bat["degradation_cost"] * timestep_hours
        )

    scheduled_cost = costs.total_cost
    scheduled_peak = performance.peak_grid_import_kw
    throughput = performance.battery_throughput_kwh
    self_consumption_pct = performance.self_consumption_ratio * 100.0

    savings = baseline_cost - scheduled_cost
    savings_pct = (savings / baseline_cost * 100.0) if baseline_cost != 0 else 0.0
    peak_reduction = baseline_peak - scheduled_peak
    peak_reduction_pct = (
        (peak_reduction / baseline_peak * 100.0) if baseline_peak > 0 else 0.0
    )

    charge_total, discharge_total = total_battery_flows(data_df, batteries)

    return {
        "costs": costs,
        "performance": performance,
        "baseline_import": baseline_import,
        "baseline_cost_series": baseline_cost_series,
        "scheduled_import": scheduled_import,
        "scheduled_cost_series": scheduled_cost_series,
        "import_price_series": import_price_series,
        "charge_total": charge_total,
        "discharge_total": discharge_total,
        "baseline_cost": baseline_cost,
        "baseline_peak": baseline_peak,
        "scheduled_cost": scheduled_cost,
        "scheduled_peak": scheduled_peak,
        "throughput": throughput,
        "self_consumption_pct": self_consumption_pct,
        "savings": savings,
        "savings_pct": savings_pct,
        "peak_reduction": peak_reduction,
        "peak_reduction_pct": peak_reduction_pct,
        "timestep_hours": timestep_hours,
    }


def _render_price_duration_plot(
    metrics: dict, charge_series: pd.Series, discharge_series: pd.Series
) -> go.Figure:
    """Build price-duration plot with charge/discharge markers."""
    import_price_series = metrics["import_price_series"]
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

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=duration_df["rank"],
            y=duration_df["price"],
            name="Import Price",
            mode="lines",
            line=dict(color=CHART_COLORS["price"]),
        )
    )
    charge_pts = duration_df[duration_df["charge"] > 0]
    discharge_pts = duration_df[duration_df["discharge"] > 0]
    if not charge_pts.empty:
        fig.add_trace(
            go.Scatter(
                x=charge_pts["rank"],
                y=charge_pts["price"],
                name="Charge",
                mode="markers",
                marker=dict(symbol="triangle-up", size=8, color=CHART_COLORS["charge"]),
            )
        )
    if not discharge_pts.empty:
        fig.add_trace(
            go.Scatter(
                x=discharge_pts["rank"],
                y=discharge_pts["price"],
                name="Discharge",
                mode="markers",
                marker=dict(symbol="triangle-down", size=8, color=CHART_COLORS["discharge"]),
            )
        )
    fig.update_layout(
        title="Price-Duration Plot with Charge/Discharge Markers",
        margin=dict(t=40, b=20),
        xaxis_title="Rank (sorted by price)",
        yaxis_title="Electricity Price (EUR/kWh)",
    )
    return fig


def _render_grid_and_cumulative_plot(
    metrics: dict,
    x_axis: Any,
    label: Optional[str] = None,
    extra_scheduled_import: Optional[pd.Series] = None,
    extra_label: Optional[str] = None,
    extra_cost_series: Optional[pd.Series] = None,
) -> go.Figure:
    """Build two-subplot figure: grid import + cumulative cost.

    If extra_scheduled_import is provided, overlays a third schedule on both subplots.
    """
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08
    )

    # Row 1: Grid import
    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=metrics["baseline_import"],
            name="Baseline Grid Import",
            mode="lines",
            line=dict(dash="dot", color=CHART_COLORS["export_price"]),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=metrics["scheduled_import"],
            name="Scheduled Grid Import" if label is None else f"{label} Grid Import",
            mode="lines",
            line=dict(color=CHART_COLORS["load"]),
        ),
        row=1,
        col=1,
    )
    if extra_scheduled_import is not None and extra_label is not None:
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=extra_scheduled_import,
                name=f"{extra_label} Grid Import",
                mode="lines",
                line=dict(dash="dash", color=CHART_COLORS["discharge"]),
            ),
            row=1,
            col=1,
        )
    fig.update_yaxes(title_text="Power (kW)", row=1, col=1)

    # Row 2: Cumulative cost
    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=metrics["baseline_cost_series"].cumsum(),
            name="Baseline Cumulative Cost",
            mode="lines",
            line=dict(dash="dot", color=CHART_COLORS["export_price"]),
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=metrics["scheduled_cost_series"].cumsum(),
            name="Scheduled Cumulative Cost" if label is None else f"{label} Cumulative Cost",
            mode="lines",
            line=dict(color=CHART_COLORS["load"]),
        ),
        row=2,
        col=1,
    )
    if extra_cost_series is not None and extra_label is not None:
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=extra_cost_series.cumsum(),
                name=f"{extra_label} Cumulative Cost",
                mode="lines",
                line=dict(dash="dash", color=CHART_COLORS["discharge"]),
            ),
            row=2,
            col=1,
        )
    fig.update_yaxes(title_text="Cost (€)", row=2, col=1)
    fig.update_layout(height=600, margin=dict(t=40, b=20))
    return fig


def render_schedule_analytics(
    input_df: pd.DataFrame,
    output_df: pd.DataFrame,
    batteries: list[dict],
    timestep_hours_hint: Optional[float],
) -> None:
    """Render 3-row analytics for a single schedule result.

    Row 1: Cost KPIs (scheduled cost, savings, peak reduction, self-consumption)
    Row 2: Battery KPIs (throughput, degradation) + price-duration plot
    Row 3: Grid import + cumulative cost (two subplots)
    """
    load_col = first_present(output_df, ["load", "expected_load"])
    pv_col = first_present(output_df, ["pv", "expected_pv"])
    import_price_col = first_present(output_df, ["import_price"])
    grid_import_col = first_present(output_df, ["grid_import", "expected_grid_import"])

    required = [load_col, pv_col, import_price_col, grid_import_col]
    if any(col is None for col in required):
        st.info("Analytics needs load, pv, import_price, and grid_import columns.")
        return

    timestep_hours = resolve_timestep_hours(output_df, timestep_hours_hint)
    metrics = _compute_schedule_metrics(output_df, batteries, timestep_hours)

    x_axis = output_df["Date"] if "Date" in output_df.columns else output_df.index

    # Row 1: Cost KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Scheduled Cost", f"€{metrics['scheduled_cost']:.2f}")
    k2.metric(
        "Savings vs Baseline",
        f"€{metrics['savings']:.2f}",
        f"{metrics['savings_pct']:.1f}%",
    )
    k3.metric(
        "Peak Import Reduction",
        f"{metrics['peak_reduction']:.2f} kW",
        f"{metrics['peak_reduction_pct']:.1f}%",
    )
    k4.metric("Self-Consumption", f"{metrics['self_consumption_pct']:.1f}%")

    # Row 2: Battery KPIs + price-duration plot
    k5, k6, k7 = st.columns([1, 1, 2])
    k5.metric("Battery Throughput", f"{metrics['throughput']:.2f} kWh")
    k6.metric("Battery Degradation Cost", f"€{metrics['costs'].degradation_cost:.2f}")
    with k7:
        fig_pd = _render_price_duration_plot(
            metrics, metrics["charge_total"], metrics["discharge_total"]
        )
        st.plotly_chart(fig_pd, width="stretch")

    # Row 3: Grid import + cumulative cost
    fig_grid_cum = _render_grid_and_cumulative_plot(metrics, x_axis)
    st.plotly_chart(fig_grid_cum, width="stretch")


def _recompute_grid_flows_with_actual(
    stoch_output: pd.DataFrame,
    actual_df: pd.DataFrame,
    batteries: list[dict],
) -> pd.DataFrame:
    """Recompute grid import/export using actual PV/load + stochastic battery schedule.

    The stochastic battery schedule (charge/discharge/SOC) is kept as-is, but grid
    flows are recomputed using actual PV/load from the open-source dataset:
        grid = load_actual - pv_actual + charge - discharge
        grid_import = max(grid, 0)
        grid_export = max(-grid, 0)

    Returns a copy of stoch_output with pv, load, grid_import, grid_export replaced
    by actual-based values. All columns use the non-prefixed names (expected_ stripped)
    so that downstream calculators find them consistently.
    """
    eval_df = stoch_output.copy()
    if "Date" not in eval_df.columns and eval_df.index.name == "Date":
        eval_df = eval_df.reset_index()
    eval_df = eval_df.reset_index(drop=True)
    actual_df = actual_df.reset_index(drop=True)

    # Strip expected_ prefix so all columns use consistent names
    eval_df.rename(
        columns={col: col.replace("expected_", "") for col in eval_df.columns},
        inplace=True,
    )

    # Replace PV/load with actual values
    eval_df["pv"] = pd.to_numeric(actual_df["pv"], errors="coerce").fillna(0.0).values
    eval_df["load"] = pd.to_numeric(actual_df["load"], errors="coerce").fillna(0.0).values

    # Recompute grid flows from actual PV/load + battery schedule
    charge_total, discharge_total = total_battery_flows(eval_df, batteries)
    grid = eval_df["load"] - eval_df["pv"] + charge_total - discharge_total
    eval_df["grid_import"] = grid.clip(lower=0.0)
    eval_df["grid_export"] = (-grid).clip(lower=0.0)

    return eval_df


def render_comparative_analytics(
    actual_df: pd.DataFrame,
    det_output: pd.DataFrame,
    stoch_output: pd.DataFrame,
    batteries: list[dict],
    timestep_hours_hint: Optional[float],
) -> None:
    """Render comparative 3-row analytics for Explore tab.

    Compares perfect foresight vs stochastic (evaluated with actual PV/load)
    vs no-battery baseline.

    Row 1: Cost KPIs (perfect foresight / stochastic / baseline)
    Row 2: Battery KPIs + price-duration (stochastic only)
    Row 3: Grid import + cumulative cost (baseline + both schedules)
    """
    timestep_hours = resolve_timestep_hours(det_output, timestep_hours_hint)

    # Perfect foresight metrics (already uses actual data)
    pf_metrics = _compute_schedule_metrics(det_output, batteries, timestep_hours)

    # Stochastic evaluated with actual PV/load
    stoch_eval_df = _recompute_grid_flows_with_actual(
        stoch_output, actual_df, batteries
    )
    stoch_metrics = _compute_schedule_metrics(
        stoch_eval_df, batteries, timestep_hours
    )

    x_axis = det_output["Date"] if "Date" in det_output.columns else det_output.index

    metric_heading_color = "#e8e9eb"
    metric_value_color = "#f8fafc"
    metric_positive_delta_color = "#34d399"  # green for positive delta
    metric_negative_delta_color = "#fb7185"  # red for negative delta
    metric_border_color = "#f59e0b"

    # Row 1: Cost KPIs — perfect foresight, stochastic, baseline
    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric(
            "Total Cost (Baseline / PF / Stoch)",
            f"€{pf_metrics['baseline_cost']:.2f} / €{pf_metrics['scheduled_cost']:.2f} / €{stoch_metrics['scheduled_cost']:.2f}",
            help="Baseline: no battery, PF: perfect foresight schedule, Stoch: history based stochastic schedule evaluated with actual PV/load",
        )
    with k2:
        delta_color = metric_positive_delta_color if pf_metrics["savings"] >= 0 else metric_negative_delta_color
        st.markdown(
            f'<div style="border-left:3px solid {delta_color};padding-left:10px">'
            f'<div style="font-size:0.8rem;color:{metric_heading_color}">Savings vs Baseline (PF)</div>'
            f'<div style="font-size:1.5rem;font-weight:bold">€{pf_metrics["savings"]:.2f} '
            f'<span style="font-size:1.1rem;color:{delta_color}">({pf_metrics["savings_pct"]:.1f}%)</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with k3:
        delta_color = metric_positive_delta_color if stoch_metrics["savings"] >= 0 else metric_negative_delta_color
        st.markdown(
            f'<div style="border-left:3px solid {delta_color};padding-left:10px" '
            f'title="Savings for stochastic schedule are computed by evaluating the stochastic schedule with actual PV/load data. '
            f'This could be negative (i.e., costlier than having no battery) on certain days when the actual data from the day deviates significantly from the immediate history.">'
            f'<div style="font-size:0.8rem;color:{metric_heading_color}">Savings vs Baseline (Stoch)</div>'
            f'<div style="font-size:1.5rem;font-weight:bold">€{stoch_metrics["savings"]:.2f} '
            f'<span style="font-size:1.1rem;color:{delta_color}">({stoch_metrics["savings_pct"]:.1f}%)</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # k4.metric(
    #     "Peak Import Reduction (PF)",
    #     f"{pf_metrics['peak_reduction']:.2f} kW",
    #     f"{pf_metrics['peak_reduction_pct']:.1f}%",
    # )

    # Row 2: Battery KPIs (left, stacked) + price-duration plot (right, stochastic only)
    st.markdown("##### Battery and other KPIs")
    k5, k6 = st.columns([1, 2])
    with k5:
        st.markdown(
            f'<div style="border-left:3px solid {metric_border_color};padding-left:10px;margin-bottom:8px">'
            f'<div style="font-size:0.8rem;color:{metric_heading_color}">Battery Throughput (PF / Stoch)</div>'
            f'<div style="font-size:1.5rem;font-weight:bold">{pf_metrics["throughput"]:.2f} / {stoch_metrics["throughput"]:.2f} kWh</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.space()
        st.markdown(
            f'<div style="border-left:3px solid {metric_border_color};padding-left:10px;margin-bottom:8px">'
            f'<div style="font-size:0.8rem;color:{metric_heading_color}">Battery Degradation Cost (PF / Stoch)</div>'
            f'<div style="font-size:1.5rem;font-weight:bold">€{pf_metrics["costs"].degradation_cost:.2f} / €{stoch_metrics["costs"].degradation_cost:.2f}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.space()
        st.markdown(
            f'<div style="border-left:3px solid {metric_border_color};padding-left:10px" '
            f'title="Self-consumption is the percentage of PV generation that is consumed on-site (not exported to the grid).">'
            f'<div style="font-size:0.8rem;color:{metric_heading_color}">PV Self-Consumption (PF / Stoch)</div>'
            f'<div style="font-size:1.5rem;font-weight:bold">{pf_metrics["self_consumption_pct"]:.1f}% / {stoch_metrics["self_consumption_pct"]:.1f}%</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with k6:
        fig_pd = _render_price_duration_plot(
            stoch_metrics, stoch_metrics["charge_total"], stoch_metrics["discharge_total"]
        )
        st.plotly_chart(fig_pd, width="stretch")
        # st.info(
        #     "Price-duration curve: import prices sorted from lowest to highest. "
        #     "▲ markers show timesteps where the battery charges (low prices), "
        #     "▼ markers show timesteps where it discharges (high prices)."
        # )

    # Row 3: Grid import + cumulative cost (baseline + both schedules)
    st.markdown("##### Grid Import and Cumulative Cost")
    fig_grid_cum = _render_grid_and_cumulative_plot(
        pf_metrics,
        x_axis,
        label="PF",
        extra_scheduled_import=stoch_metrics["scheduled_import"],
        extra_label="Stochastic (history based)",
        extra_cost_series=stoch_metrics["scheduled_cost_series"],
    )
    st.plotly_chart(fig_grid_cum, width="stretch")
