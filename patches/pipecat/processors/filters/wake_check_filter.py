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

import asyncio
import re
import time
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
            last_activity_time: Timestamp of last received transcription.
        """

        def __init__(self, participant_id: str):
            """Initialize participant state.

            Args:
                participant_id: Unique identifier for the participant.
            """
            self.participant_id = participant_id
            self.state = WakeCheckFilter.WakeState.IDLE
            self.accumulator = ""
            self.last_activity_time = time.time()

    def __init__(
        self,
        wake_phrases: List[str],
        idle_phrases: List[str],
        wake_notifier: Optional["BaseNotifier"] = None,
        idle_notifier: Optional["BaseNotifier"] = None,
        wake_timeout: Optional[float] = None,
    ):
        """Initialize the wake phrase filter.

        Args:
            wake_phrases: List of wake phrases to detect in transcriptions.
            idle_phrases: List of idle phrases to detect to stop passing frames.
            wake_notifier: Optional notifier to trigger when wake phrase is detected.
                If provided, frames containing wake phrases will NOT be passed through.
            idle_notifier: Optional notifier to trigger when idle phrase is detected.
                If provided, frames containing idle phrases will NOT be passed through.
            wake_timeout: Optional timeout in seconds. If set, the filter will automatically
                switch from AWAKE to IDLE state after this duration of no user input.
        """
        super().__init__()
        self._participant_states = {}
        self._wake_patterns = []
        self._idle_patterns = []
        self._wake_notifier = wake_notifier
        self._idle_notifier = idle_notifier
        self._wake_timeout = wake_timeout
        self._timeout_check_task = None

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

        # 如果设置了超时，启动超时检查任务
        if self._wake_timeout:
            self._timeout_check_task = asyncio.create_task(self._check_timeout_loop())
            logger.info(f"Wake timeout check enabled, timeout: {self._wake_timeout}s")

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

                # 更新活动时间
                p.last_activity_time = time.time()
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

    async def _check_timeout_loop(self):
        """定期检查是否有参与者在 AWAKE 状态下超时未活动。"""
        try:
            while True:
                await asyncio.sleep(1)  # 每秒检查一次
                current_time = time.time()

                for participant_id, p in list(self._participant_states.items()):
                    # 只检查处于 AWAKE 状态的参与者
                    if p.state == WakeCheckFilter.WakeState.AWAKE:
                        time_since_last_activity = current_time - p.last_activity_time

                        # 如果超过超时时间，自动切换到 IDLE 状态
                        if time_since_last_activity >= self._wake_timeout:
                            logger.info(
                                f"Participant {participant_id} timed out in AWAKE state "
                                f"({time_since_last_activity:.1f}s), switching to IDLE"
                            )
                            p.state = WakeCheckFilter.WakeState.IDLE
                            p.accumulator = ""

                            # 如果设置了 idle_notifier，触发通知
                            if self._idle_notifier:
                                logger.debug("Triggering timeout idle notifier")
                                await self._idle_notifier.notify()

        except asyncio.CancelledError:
            logger.debug("Timeout check task cancelled")
        except Exception as e:
            logger.exception(f"Error in timeout check loop: {e}")

    async def cleanup(self):
        """清理资源，取消超时检查任务。"""
        if self._timeout_check_task:
            self._timeout_check_task.cancel()
            try:
                await self._timeout_check_task
            except asyncio.CancelledError:
                pass
            logger.debug("Timeout check task cleaned up")
        await super().cleanup()
