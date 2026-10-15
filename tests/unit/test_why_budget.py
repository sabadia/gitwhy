"""The why budget check fails closed at 100 ms (docs/02 section 9)."""

from tests.bench.budget import WHY_BUDGET_MS, over_budget


def test_exactly_the_budget_is_a_miss() -> None:
    assert WHY_BUDGET_MS == 100.0
    assert over_budget(100.0)
    assert over_budget(100.1)
    assert not over_budget(99.9)
