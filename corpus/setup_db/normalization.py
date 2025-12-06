"""
Text normalization utilities for corpus processing.
"""

import re
from enum import Enum
from typing import Any
import regex as re_unicode


class NormalizationStrategy(Enum):
    """
    Defines the available normalization strategies.
    The value of each member is the compiled regex pattern.
    """

    ALPHANUMERIC_STRICT = re.compile(r"[^a-z0-9]+")
    """Only allows basic a-z and 0-9. (Fastest)"""

    UNICODE_WORDS = re.compile(r"[^\w]+")
    """Allows Unicode letters, numbers, and underscores."""

    ALPHANUMERIC_LOOSE = re_unicode.compile(r"[^\p{L}\p{N}]+", re_unicode.UNICODE)
    """Allows only Unicode letters and numbers. (Recommended)"""

    def normalize(self, v: Any) -> str:
        """Helper method to normalize a value using this strategy."""
        if not isinstance(v, str):
            v = str(v)
        v = v.strip().lower()
        # self.value is the compiled regex
        v = self.value.sub(" ", v)
        return v.strip()


# Global instance for convenience
DEFAULT_NORMALIZATION_STRATEGY = NormalizationStrategy.ALPHANUMERIC_STRICT


def set_normalization_strategy(strategy: NormalizationStrategy):
    """
    Globally sets the normalization strategy.

    Convenience function for backward compatibility.
    """
    global DEFAULT_NORMALIZATION_STRATEGY
    DEFAULT_NORMALIZATION_STRATEGY = strategy


def normalize_value(v: Any) -> str:
    """
    Normalize a value using the global strategy.

    Convenience function for backward compatibility.
    """
    return DEFAULT_NORMALIZATION_STRATEGY.normalize(v)
