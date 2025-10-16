#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Silero Voice Activity Detection (VAD) implementation for Pipecat.

This module provides a VAD analyzer based on the Silero VAD ONNX model,
which can detect voice activity in audio streams with high accuracy.
Supports 8kHz and 16kHz sample rates.
"""

import time
from typing import Optional

import numpy as np
from loguru import logger

from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams

# How often should we reset internal model state
_MODEL_RESET_STATES_TIME = 5.0

try:
    import torch

except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error(
        "In order to use Silero VAD, you need to `pip install pipecat-ai[silero]`."
    )
    raise Exception(f"Missing module(s): {e}")


class SileroVADAnalyzer(VADAnalyzer):
    """Voice Activity Detection analyzer using the Silero VAD model.

    Implements VAD analysis using the pre-trained Silero ONNX model for
    accurate voice activity detection. Supports 8kHz and 16kHz sample rates
    with automatic model state management and periodic resets.
    """

    def __init__(
        self, *, sample_rate: Optional[int] = None, params: Optional[VADParams] = None
    ):
        """Initialize the Silero VAD analyzer.

        Args:
            sample_rate: Audio sample rate (8000 or 16000 Hz). If None, will be set later.
            params: VAD parameters for detection thresholds and timing.
        """
        super().__init__(sample_rate=sample_rate, params=params)

        logger.debug("Loading Silero VAD model...")

        self._model, _ = torch.hub.load(
            "G:/models/silero-vad", "silero_vad", source="local"
        )

        self._last_reset_time = 0

        logger.debug("Loaded Silero VAD")

    #
    # VADAnalyzer
    #

    def set_sample_rate(self, sample_rate: int):
        """Set the sample rate for audio processing.

        Args:
            sample_rate: Audio sample rate (must be 8000 or 16000 Hz).

        Raises:
            ValueError: If sample rate is not 8000 or 16000 Hz.
        """
        if sample_rate != 16000 and sample_rate != 8000:
            raise ValueError(
                f"Silero VAD sample rate needs to be 16000 or 8000 (sample rate: {sample_rate})"
            )

        super().set_sample_rate(sample_rate)

    def num_frames_required(self) -> int:
        """Get the number of audio frames required for VAD analysis.

        Returns:
            Number of frames required (512 for 16kHz, 256 for 8kHz).
        """
        return 512 if self.sample_rate == 16000 else 256

    def voice_confidence(self, buffer) -> float:
        """Calculate voice activity confidence for the given audio buffer.

        Args:
            buffer: Audio buffer to analyze.

        Returns:
            Voice confidence score between 0.0 and 1.0.
        """
        try:
            audio_int16 = np.frombuffer(buffer, np.int16)
            # Divide by 32768 because we have signed 16-bit data.
            audio_float32 = (
                np.frombuffer(audio_int16, dtype=np.int16).astype(np.float32) / 32768.0
            )
            audio_float32_tensor = torch.from_numpy(audio_float32)
            new_confidence = self._model(audio_float32_tensor, self.sample_rate).item()

            # We need to reset the model from time to time because it doesn't
            # really need all the data and memory will keep growing otherwise.
            curr_time = time.time()
            diff_time = curr_time - self._last_reset_time
            if diff_time >= _MODEL_RESET_STATES_TIME:
                self._model.reset_states()
                self._last_reset_time = curr_time

            return new_confidence
        except Exception as e:
            # This comes from an empty audio array
            logger.error(f"Error analyzing audio with Silero VAD: {e}")
            return 0
