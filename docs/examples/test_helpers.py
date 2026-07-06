"""External test functions for the example notebook exercises."""

from __future__ import annotations


def test_multiply_basic(multiply) -> tuple[bool, str]:
    """Test basic multiplication."""
    result = multiply(3, 4)
    return result == 12, f"Expected 12, got {result}"


def test_multiply_zero(multiply) -> tuple[bool, str]:
    """Test multiplication by zero."""
    result = multiply(5, 0)
    return result == 0, f"Expected 0, got {result}"


def test_multiply_negative(multiply) -> tuple[bool, str]:
    """Test multiplication with negative numbers."""
    result = multiply(-2, 3)
    return result == -6, f"Expected -6, got {result}"
