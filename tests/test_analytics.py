import math

import pandas as pd

from src.analytics import _drawdown_episode_metrics, _period_return


def test_period_return_and_drawdown_episode_metrics():
    index = pd.to_datetime(["2020-01-01", "2021-01-01", "2022-01-01"])
    values = pd.Series([100.0, 110.0, 121.0], index=index)
    assert math.isclose(_period_return(values, 1), 0.10, rel_tol=2e-3)
    drawdown = pd.Series([0.0, -0.1, -0.25, -0.05, 0.0], index=pd.date_range("2020-01-01", periods=5))
    longest, episodes = _drawdown_episode_metrics(drawdown)
    assert longest == 3
    assert episodes == 1
