"""Helper module for external test loading in test_runner tests."""

from __future__ import annotations


def test_add_via_external_module(add) -> bool:
    """Test function loaded from external module for testing the runner."""
    return add(2, 3) == 5


def test_with_message_via_external_module(add) -> tuple[bool, str]:
    """Test function that returns a tuple with message."""
    result = add(10, 20)
    return result == 30, f"Expected 30, got {result}"
