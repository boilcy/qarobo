#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Wake phrase detection filter for Pipecat transcription processing.

This module provides a frame processor that filters transcription frames,
only allowing them through between wake phrases and idle phrases detection.
Frames containing wake phrases and idle phrases can either be passed through
or replaced with notifier signals depending on configuration.
"""

import re
from enum import Enum
from typing import List, Optional

from loguru import logger

from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

try:
    from src.sync.base_notifier import BaseNotifier
except ImportError:
    # Fallback for when running from different context
    try:
        from pipecat.sync.base_notifier import BaseNotifier
    except ImportError:
        BaseNotifier = None


class WakeCheckFilter(FrameProcessor):
    """Frame processor that filters transcription frames based on wake phrase detection.

    This filter monitors transcription frames for configured wake phrases and idle phrases.
    Frames are only passed through between wake phrase detection and idle phrase detection.

    If a notifier is provided:
        - Frames containing wake/idle phrases are NOT passed through
        - Instead, the notifier is triggered to provide feedback
    If no notifier is provided:
        - Frames containing wake/idle phrases ARE passed through
    """

    class WakeState(Enum):
        """Enumeration of wake detection states.

        Parameters:
            IDLE: No wake phrase detected, filtering active.
            AWAKE: Wake phrase detected, allowing frames through.
        """

        IDLE = 1
        AWAKE = 2

    class ParticipantState:
        """State tracking for individual participants.

        Parameters:
            participant_id: Unique identifier for the participant.
            state: Current wake state (IDLE or AWAKE).
            accumulator: Accumulated text for wake/idle phrase matching.
        """

        def __init__(self, participant_id: str):
            """Initialize participant state.

            Args:
                participant_id: Unique identifier for the participant.
            """
            self.participant_id = participant_id
            self.state = WakeCheckFilter.WakeState.IDLE
            self.accumulator = ""

    def __init__(
        self,
        wake_phrases: List[str],
        idle_phrases: List[str],
        wake_notifier: Optional["BaseNotifier"] = None,
        idle_notifier: Optional["BaseNotifier"] = None,
    ):
        """Initialize the wake phrase filter.

        Args:
            wake_phrases: List of wake phrases to detect in transcriptions.
            idle_phrases: List of idle phrases to detect to stop passing frames.
            wake_notifier: Optional notifier to trigger when wake phrase is detected.
                If provided, frames containing wake phrases will NOT be passed through.
            idle_notifier: Optional notifier to trigger when idle phrase is detected.
                If provided, frames containing idle phrases will NOT be passed through.
        """
        super().__init__()
        self._participant_states = {}
        self._wake_patterns = []
        self._idle_patterns = []
        self._wake_notifier = wake_notifier
        self._idle_notifier = idle_notifier

        for name in wake_phrases:
            pattern = re.compile(
                r"\b" + r"\s*".join(re.escape(word) for word in name.split()) + r"\b",
                re.IGNORECASE,
            )
            self._wake_patterns.append(pattern)

        for name in idle_phrases:
            pattern = re.compile(
                r"\b" + r"\s*".join(re.escape(word) for word in name.split()) + r"\b",
                re.IGNORECASE,
            )
            self._idle_patterns.append(pattern)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames, filtering transcriptions based on wake detection.

        Args:
            frame: The frame to process.
            direction: The direction of frame flow in the pipeline.
        """
        await super().process_frame(frame, direction)

        try:
            if isinstance(frame, TranscriptionFrame):
                p = self._participant_states.get(frame.user_id)
                if p is None:
                    p = WakeCheckFilter.ParticipantState(frame.user_id)
                    self._participant_states[frame.user_id] = p

                p.accumulator += frame.text

                # 如果当前处于 AWAKE 状态
                if p.state == WakeCheckFilter.WakeState.AWAKE:
                    # 检查是否包含关闭词
                    idle_detected = False
                    for pattern in self._idle_patterns:
                        match = pattern.search(p.accumulator)
                        if match:
                            logger.debug(f"Idle phrase detected: {match.group()}")
                            idle_detected = True
                            # 切换到 IDLE 状态
                            p.state = WakeCheckFilter.WakeState.IDLE
                            p.accumulator = ""

                            # 如果设置了 idle_notifier，触发通知而不推送 frame
                            if self._idle_notifier:
                                logger.debug(
                                    "Triggering idle notifier instead of pushing frame"
                                )
                                await self._idle_notifier.notify()
                            else:
                                # 没有 notifier，推送包含关闭词的 frame
                                await self.push_frame(frame)
                            return

                    # 没有检测到关闭词，继续推送 frame
                    if not idle_detected:
                        logger.debug(f"In AWAKE state, pushing frame: {frame.text}")
                        await self.push_frame(frame)
                        return

                # 如果当前处于 IDLE 状态，检查唤醒词
                else:
                    for pattern in self._wake_patterns:
                        match = pattern.search(p.accumulator)
                        if match:
                            logger.debug(f"Wake phrase triggered: {match.group()}")
                            # 检测到唤醒词，切换到 AWAKE 状态
                            p.state = WakeCheckFilter.WakeState.AWAKE

                            # 如果设置了 wake_notifier，触发通知而不推送包含唤醒词的 frame
                            if self._wake_notifier:
                                logger.debug(
                                    "Triggering wake notifier instead of pushing frame"
                                )
                                await self._wake_notifier.notify()
                                # 从唤醒词之后的文本开始处理
                                text_after_wake = p.accumulator[match.end() :].strip()
                                p.accumulator = ""
                                # 如果唤醒词后还有文本，创建新的 frame 推送
                                if text_after_wake:
                                    frame.text = text_after_wake
                                    await self.push_frame(frame)
                            else:
                                # 没有 notifier，推送包含唤醒词的 frame
                                frame.text = p.accumulator[match.start() :]
                                p.accumulator = ""
                                await self.push_frame(frame)
                            return

                    # 没有检测到唤醒词，不推送 frame
                    logger.debug(
                        f"In IDLE state, no wake phrase detected. Dropping frame: {frame.text}"
                    )
            else:
                await self.push_frame(frame, direction)
        except Exception as e:
            error_msg = f"Error in wake word filter: {e}"
            logger.exception(error_msg)
            await self.push_error(ErrorFrame(error_msg))
