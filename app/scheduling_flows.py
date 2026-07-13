"""Data import flows and input preview rendering."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scheduling_config import (
    AHEAD_REQUIRED_COLS,
    CHART_COLORS,
    DETERM_REQUIRED_COLS,
    HIST_REQUIRED_COLS,
    OPEN_SOURCE_DATASET_PATH,
    OPEN_SOURCE_DATE_COL,
    OPEN_SOURCE_LOAD_COL,
    OPEN_SOURCE_PRICE_COL,
    OPEN_SOURCE_PV_COL,
    OPEN_SOURCE_SHEET,
)
from scheduling_ui import solver_opts_editor

# Color palette for dark blue background
COLOR_PV = CHART_COLORS["pv"]
COLOR_LOAD = CHART_COLORS["load"]
COLOR_PRICE = CHART_COLORS["price"]


def _validate_required_columns(
    df: pd.DataFrame, required_cols: list[str], label: str
) -> bool:
    """Validate required columns and render a consistent error message if missing."""
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        st.error(
            f"{label} is missing required columns: {', '.join(missing)}. "
            f"Expected: {', '.join(required_cols)}"
        )
        return False
    return True


def import_forecasts_flow(
    sidebar_batteries: Optional[list[dict]],
    collapse_above: bool,
) -> Optional[Tuple[pd.DataFrame, list[dict], dict]]:
    """Import and validate deterministic forecasts (PV, load, prices)."""
    st.subheader("Forecast-based (deterministic) approach")
    st.markdown(
        "If good forecasts of PV generation and load (consumption) are available.  \n"
        "Requires `pv` generation and `load` forecasts, and `import_price` (electricity prices), for the next day."
    )

    file_col, _ = st.columns(2)
    with file_col:
        uploaded = st.file_uploader(
            "Upload CSV file",
            help="(Required columns: "
            + ", ".join(DETERM_REQUIRED_COLS)
            + ", Date (date-time, optional))",
            type=["csv"],
            key="forecast_upl",
            max_upload_size=10,  # 10 MB
        )
    if uploaded is None:
        st.info("Upload a forecasts CSV file to continue.")
        return None

    forecasts_df = pd.read_csv(uploaded)
    if not _validate_required_columns(
        forecasts_df,
        DETERM_REQUIRED_COLS,
        "Forecast CSV",
    ):
        return None

    st.caption(f"Loaded `{uploaded.name}` ({len(forecasts_df)} rows)")
    has_date = "Date" in forecasts_df.columns
    if has_date:
        opts: Optional[dict] = {"timestep_hours": None}
    else:
        with st.expander("Options", expanded=not collapse_above):
            st.info(
                "Warning: `Date` column missing in one or both files, assuming data belongs to the next day. Set correct `timestep_hours` in the options."
            )
            opts = solver_opts_editor(key_prefix="det")

        if opts is None:
            st.info("Fix validation errors above to continue.")
            return None

        tomo = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
        forecasts_df["Date"] = pd.date_range(
            start=tomo, periods=len(forecasts_df), freq=f"{opts['timestep_hours']}h"
        )

    if sidebar_batteries is None or opts is None:
        st.info("Fix validation errors above to continue.")
        return None
    return forecasts_df, sidebar_batteries, opts


def import_history_flow(
    sidebar_batteries: Optional[list[dict]],
    collapse_above: bool,
    stochastic_controls_renderer: Callable[
        [str, Optional[list[dict]], bool, bool],
        Optional[Tuple[list[dict], dict, Optional[dict]]],
    ],
) -> Optional[Tuple[pd.DataFrame, pd.DataFrame, list[dict], dict, Optional[dict]]]:
    """Import and validate history and ahead prices for stochastic approach."""
    st.subheader("History-based (stochastic) approach")
    st.markdown(
        "If history of PV generation and load (consumption) is available.  \n"
        "Requires `pv` generation and `load` data from immediate past (5-10 days recommended). Also requires `import_price` (electricity prices) for the next day."
    )

    hist_col, ahead_col = st.columns(2)
    with hist_col:
        hist_u = st.file_uploader(
            "Upload history CSV",
            help="(Required columns: "
            + ", ".join(HIST_REQUIRED_COLS)
            + ", Date (date-time, optional))",
            type=["csv"],
            max_upload_size=10,  # 10 MB
            key="hist_upl",
        )
    with ahead_col:
        ahead_u = st.file_uploader(
            "Upload tomorrow's electricity prices CSV",
            help="(Required columns: "
            + ", ".join(AHEAD_REQUIRED_COLS)
            + ", Date (date-time, optional))",
            type=["csv"],
            max_upload_size=10,  # 10 MB
            key="ahead_upl",
        )
    if hist_u is None or ahead_u is None:
        st.info("Upload both history and tomorrow's prices files to continue.")
        return None

    hist_df = pd.read_csv(hist_u)
    ahead_df = pd.read_csv(ahead_u)
    if not _validate_required_columns(
        hist_df,
        HIST_REQUIRED_COLS,
        "History CSV",
    ):
        return None
    if not _validate_required_columns(
        ahead_df,
        AHEAD_REQUIRED_COLS,
        "Tomorrow prices CSV",
    ):
        return None

    st.caption(
        f"Loaded history `{hist_u.name}` ({len(hist_df)} rows) and tomorrow's prices `{ahead_u.name}` ({len(ahead_df)} rows)"
    )

    has_hist_date = "Date" in hist_df.columns
    has_ahead_date = "Date" in ahead_df.columns
    needs_timestep = (not has_hist_date) or (not has_ahead_date)

    controls = stochastic_controls_renderer(
        "stoch",
        sidebar_batteries,
        needs_timestep,
        collapse_above,
    )
    if controls is None:
        return None
    batteries, opts, override = controls

    if needs_timestep:
        tomo = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)

        hist_df["Date"] = pd.date_range(
            end=tomo - pd.Timedelta(hours=opts["timestep_hours"]),
            periods=len(hist_df),
            freq=f"{opts['timestep_hours']}h",
        )
        ahead_df["Date"] = pd.date_range(
            start=tomo, periods=len(ahead_df), freq=f"{opts['timestep_hours']}h"
        )

    if override is not None and "history_days" in override:
        # Trim history data to the determined number of days
        history_days = int(override["history_days"])
        day_ahead = ahead_df["Date"].min().normalize()
        history_start = day_ahead - pd.Timedelta(days=history_days)
        hist_df = hist_df[
            (hist_df["Date"] >= history_start) & (hist_df["Date"] < day_ahead)
        ].copy()

    return hist_df, ahead_df, batteries, opts, override


@st.cache_data(show_spinner=False)
def load_open_source_dataset() -> pd.DataFrame:
    """Load and prepare open-source dataset."""
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


def render_forecast_preview(forecasts_df: pd.DataFrame, collapse_above: bool) -> None:
    """Render deterministic forecast inputs (PV, load, prices)."""
    with st.expander("Inputs Preview", expanded=not collapse_above):
        plot_tab, table_tab = st.tabs(["Plot", "Table"])
        with plot_tab:
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08
            )
            x = (
                forecasts_df["Date"]
                if "Date" in forecasts_df.columns
                else forecasts_df.index
            )
            if all(c in forecasts_df.columns for c in ["pv", "load"]):
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=forecasts_df["pv"],
                        name="Forecasted PV",
                        line=dict(color=COLOR_PV),
                    ),
                    row=1,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=forecasts_df["load"],
                        name="Forecasted Load",
                        line=dict(color=COLOR_LOAD),
                    ),
                    row=1,
                    col=1,
                )
            fig.update_yaxes(title_text="Power (kW)", row=1, col=1)
            if "import_price" in forecasts_df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=forecasts_df["import_price"],
                        name="Import Price",
                        line=dict(color=COLOR_PRICE),
                    ),
                    row=2,
                    col=1,
                )
            fig.update_yaxes(title_text="Price (EUR/kWh)", row=2, col=1)
            fig.update_layout(height=600, margin=dict(t=40, b=20))
            st.plotly_chart(fig, width="stretch")
        with table_tab:
            st.dataframe(forecasts_df.head(300), width="stretch", height=260)


def render_history_preview(
    hist_df: pd.DataFrame, ahead_df: pd.DataFrame, collapse_above: bool
) -> None:
    """Render stochastic history and ahead price inputs."""
    with st.expander("Inputs Preview", expanded=not collapse_above):
        plot_tab, table_tab = st.tabs(["Plot", "Table"])
        with plot_tab:
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08
            )
            xh = hist_df["Date"] if "Date" in hist_df.columns else hist_df.index
            xa = ahead_df["Date"] if "Date" in ahead_df.columns else ahead_df.index
            if all(c in hist_df.columns for c in ["pv", "load"]):
                fig.add_trace(
                    go.Scatter(
                        x=xh,
                        y=hist_df["pv"],
                        name="PV (history)",
                        line=dict(color=COLOR_PV),
                    ),
                    row=1,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=xh,
                        y=hist_df["load"],
                        name="Load (history)",
                        line=dict(color=COLOR_LOAD),
                    ),
                    row=1,
                    col=1,
                )
            fig.update_yaxes(title_text="Power (kW)", row=1, col=1)
            if "import_price" in ahead_df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=xa,
                        y=ahead_df["import_price"],
                        name="Import Price (ahead)",
                        line=dict(color=COLOR_PRICE),
                    ),
                    row=2,
                    col=1,
                )
            fig.update_yaxes(title_text="Price (EUR/kWh)", row=2, col=1)
            fig.update_layout(height=600, margin=dict(t=40, b=20))
            st.plotly_chart(fig, width="stretch")
        with table_tab:
            st.write("History (first rows)")
            st.dataframe(hist_df.head(200), width="stretch", height=200)
            st.write("Ahead/tomorrow's prices (first rows)")
            st.dataframe(ahead_df.head(200), width="stretch", height=200)


def render_open_source_overview(data_df: pd.DataFrame, collapse_above: bool) -> None:
    """Render open-source dataset overview."""
    with st.expander(
        "Open-source dataset preview (April–December)", expanded=not collapse_above
    ):
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08)
        fig.add_trace(
            go.Scatter(
                x=data_df["Date"],
                y=data_df["pv"],
                name="PV",
                line=dict(color=COLOR_PV),
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=data_df["Date"],
                y=data_df["load"],
                name="Consumption",
                line=dict(color=COLOR_LOAD),
            ),
            row=1,
            col=1,
        )
        fig.update_yaxes(title_text="Power (kW)", row=1, col=1)
        fig.add_trace(
            go.Scatter(
                x=data_df["Date"],
                y=data_df["import_price"],
                name="Import Price",
                line=dict(color=COLOR_PRICE),
            ),
            row=2,
            col=1,
        )
        fig.update_yaxes(title_text="Price (EUR/kWh)", row=2, col=1)
        fig.update_layout(height=600, margin=dict(t=40, b=20))
        st.plotly_chart(fig, width="stretch")
