"""Temporary: proves CI fails on a failing test. Removed before merge."""


def test_ci_must_fail() -> None:
    assert False, "deliberate CI failure check"
