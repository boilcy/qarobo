"""Never interruption strategy for disable interruption."""

from pipecat.audio.interruptions.base_interruption_strategy import (
    BaseInterruptionStrategy,
)


class NeverInterruptionStrategy(BaseInterruptionStrategy):
    """Interruption strategy based on disable interruption.

    This is an interruption strategy based on disable interruption.
    That is, the strategy will be always false.
    """

    async def should_interrupt(self) -> bool:
        """Check if the user should interrupt the bot."""
        return False

    async def reset(self):
        """Reset the strategy for the next analysis cycle."""
        pass
