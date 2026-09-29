import math

import numpy as np
import pandas as pd
import pytest

from src.corporate_actions import actions_to_frame
from src.models import CorporateAction
from src.reconstruction import prepare_price_data


def reconstruct(closes, multipliers):
    dates = pd.date_range("2020-01-02", periods=len(closes), freq="B")
    history = pd.DataFrame({
        "Open": closes, "High": closes, "Low": closes, "Close": closes,
        "Adj Close": closes, "Volume": 1000, "Dividends": 0.0, "Stock Splits": 0.0,
    }, index=dates)
    actions = actions_to_frame([
        CorporateAction(date=dates[position], action_type=kind, share_multiplier=factor, include_in_reconstruction=True)
        for position, kind, factor in multipliers
    ])
    return prepare_price_data(history, actions)[0]


@pytest.mark.parametrize(
    "closes,actions,expected",
    [
        ([100, 50], [(1, "stock_split", 2.0)], [100, 100]),
        ([10, 100], [(1, "reverse_split", 0.1)], [10, 10]),
        ([100, 50], [(1, "bonus_issue", 2.0)], [100, 100]),
        ([10, 11], [], [10, 11]),
    ],
)
def test_split_continuity(closes, actions, expected):
    prices = reconstruct(closes, actions)
    assert np.allclose(prices["no_split_close"], expected)


def test_multiple_sequential_splits():
    prices = reconstruct([120, 60, 40, 10], [(1, "stock_split", 2), (2, "stock_split", 1.5), (3, "stock_split", 4)])
    assert np.allclose(prices["cumulative_split_factor"], [1, 2, 3, 12])
    assert math.isclose(prices["cumulative_split_factor"].iloc[-1], 12)
