from __future__ import annotations

import streamlit as st
from scheduling_tabs import render_scheduling_tabs
from scheduling_ui import apply_theme_and_header, battery_editor


def _render_instructions() -> None:
    with st.expander("Instructions", expanded=False):
        st.markdown("""
            - For household battery scheduling, provide PV generation, load (consumption), electricity price data
            - Set battery specifications in the left sidebar.
            - Under *dynamic* electricity pricing, the prices are tied to EPEX spot day-ahead market prices. The electricity provider informs the household of the next day's prices. If you have a general *fixed tariff* contract, provide the value from your contract.
            - It is assumed that provided data has following units: PV generation and load are in **kW** (kilowatts); prices are in **EUR/kWh**.

            **NOTE**: No claims or guarantees are made.
            """)


def _render_sidebar_batteries() -> list[dict] | None:
    with st.sidebar:
        st.subheader("Battery Specifications")
        st.caption("Shared across all tabs")
        return battery_editor(key_prefix="sidebar_global")


def main() -> None:
    apply_theme_and_header()
    sidebar_batteries = _render_sidebar_batteries()
    _render_instructions()

    st.markdown("**Try one of the two approaches or explore open-source data:**")

    # Future extension point:
    # Add top-level home routing here (e.g., Open-source exploration page vs Scheduling page).
    render_scheduling_tabs(sidebar_batteries=sidebar_batteries)


if __name__ == "__main__":
    main()
