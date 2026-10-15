"""The v1 budget for ``why`` (docs/02 section 9)."""

WHY_BUDGET_MS = 100.0


def over_budget(elapsed_ms: float, *, budget_ms: float = WHY_BUDGET_MS) -> bool:
    """Return True when ``elapsed_ms`` is not under ``budget_ms``.

    Under means strictly below the budget. 100.0 ms is a miss.
    """
    return elapsed_ms >= budget_ms
