import numpy as np
import pandas as pd
import pytest

from household_battery.policies import PolicySpec
from household_battery.schedule import generate_daily_scenarios


def _make_history_df(start_date: str, days: int, time_points_per_day: int) -> pd.DataFrame:
    # Build a simple repeating pattern for load/pv over multiple days
    timestamps = []
    loads = []
    pvs = []
    for d in range(days):
        day_start = pd.Timestamp(start_date) + pd.Timedelta(days=d)
        for t in range(time_points_per_day):
            ts = day_start + pd.Timedelta(hours=24 * t / time_points_per_day)
            timestamps.append(ts)
            loads.append(1.0 + 0.1 * d + 0.01 * t)  # small variation by day and step
            pvs.append(max(0.0, 0.5 - 0.02 * abs(t - time_points_per_day // 2)))
    return pd.DataFrame({"Date": timestamps, "load": loads, "pv": pvs})


def test_equal_probabilities_when_history_equals_num_scenarios():
    P = 5
    T = 50
    history_df = _make_history_df("2025-01-01", P, T)

    spec = PolicySpec(
        id="test_policy",
        history_days=P,
        num_scenarios=P,
        pv_coeff=0.5,
        load_coeff=0.5,
        solver="scip",
        seed=123,
    )

    load_scen, pv_scen, probabilities = generate_daily_scenarios(spec, history_df, T)

    # Basic shape checks
    assert load_scen.shape == (P, T)
    assert pv_scen.shape == (P, T)
    assert probabilities.shape == (P,)

    # When the number of scenarios equals the number of history days,
    # each scenario should represent exactly one day => equal probabilities
    expected = np.full(P, 1.0 / P)
    assert np.allclose(probabilities, expected, atol=1e-8)


if __name__ == "__main__":
    # Allow running directly for debugging
    pytest.main([__file__, "-v", "-s"])