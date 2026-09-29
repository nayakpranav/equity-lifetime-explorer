import math

import pandas as pd

from src.corporate_actions import _normalize_provider_actions, actions_to_frame, load_manual_actions


def test_provider_splits_and_dividend_isolation():
    history = pd.DataFrame(
        {"Stock Splits": [2.0, 1.5, 10.0, 0.1, 0.0], "Dividends": [0, 0, 0, 0, 1.25]},
        index=pd.date_range("2020-01-01", periods=5),
    )
    actions = actions_to_frame(_normalize_provider_actions(history, "USD"))
    shares = actions[actions["included_in_reconstruction"]]
    assert shares["share_multiplier"].tolist() == [2.0, 1.5, 10.0, 0.1]
    assert actions.loc[actions["action_type"] == "cash_dividend", "included_in_reconstruction"].eq(False).all()


def test_bonus_ratio_becomes_share_multiplier():
    actions = load_manual_actions(
        "TEST",
        records=[{
            "ticker": "TEST", "date": "2020-01-02", "action_type": "bonus_issue",
            "ratio_numerator": 1, "ratio_denominator": 1,
        }],
    )
    assert math.isclose(actions[0].share_multiplier, 2.0)
