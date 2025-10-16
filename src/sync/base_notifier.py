"""Base notifier interface for wake/idle phrase notifications.

This module provides the base interface for notifiers that can be used
to signal wake phrase detection and idle phrase detection events.
"""

from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    """Abstract base class for notifiers.

    Notifiers are used to provide feedback when wake phrases or idle phrases
    are detected, such as playing audio cues or visual indicators.
    """

    @abstractmethod
    async def notify(self):
        """Trigger a notification.

        This method should be called when a wake phrase or idle phrase is detected.
        Implementation should be non-blocking and return quickly.
        """
        pass

    @abstractmethod
    async def wait(self):
        """Wait for the notification to complete.

        This method should block until the notification has finished playing/displaying.
        """
        pass
