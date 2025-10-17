"""Keyword interruption strategy for keyword-based interruptions."""

import re
from typing import List
from pipecat.audio.interruptions.base_interruption_strategy import (
    BaseInterruptionStrategy,
)


class KeywordInterruptionStrategy(BaseInterruptionStrategy):
    """Interruption strategy based on keyword-based interruptions."""

    def __init__(self, *, keywords: List[str]):
        """Initialize the keyword interruption strategy.

        Args:
            keywords: List of keywords required to trigger an interruption.
        """
        super().__init__()
        self._keywords = keywords
        self._keywords_patterns = []
        for keyword in keywords:
            self._keywords_patterns.append(
                re.compile(
                    r"\b"
                    + r"\s*".join(re.escape(keyword) for keyword in keyword.split())
                    + r"\b",
                    re.IGNORECASE,
                )
            )

        self._text = ""

    async def append_text(self, text: str):
        """Append text for word count analysis.

        Args:
            text: Text string to append to the accumulated text.

        Note: Not all strategies need to handle text.
        """
        self._text += text

    async def should_interrupt(self) -> bool:
        for pattern in self._keywords_patterns:
            match = pattern.search(self._text)
            if match:
                return True
        return False

    async def reset(self):
        """Reset the accumulated text for the next analysis cycle."""
        self._text = ""
