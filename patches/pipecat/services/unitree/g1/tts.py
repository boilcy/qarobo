#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Unitree G1 text-to-speech service implementation."""

from typing import AsyncGenerator

from loguru import logger

from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.services.tts_service import TTSService
from pipecat.utils.tracing.service_decorators import traced_tts

try:
    from patches.unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error("In order to use Unitree G1, you need to install unitree_sdk2py.")
    raise Exception(f"Missing module: {e}")


class UnitreeG1TTSService(TTSService):
    """Unitree G1 text-to-speech service.

    Provides text-to-speech synthesis using G1's native audio service.
    Supports streaming audio playback through G1's audio system.
    """

    def __init__(
        self,
        *,
        audio_client: AudioClient,
        speaker_id: int = 0,
        **kwargs,
    ):
        """Initialize the Unitree G1 TTS service.

        Args:
            netiface: Network interface name. Defaults to "eth0".
            speaker_id: G1 speaker ID for voice selection. Defaults to 0.
            app_name: Application name for audio playback identification.
            sample_rate: Audio sample rate in Hz. Defaults to 16000.
            **kwargs: Additional arguments passed to parent TTSService class.
        """
        super().__init__(**kwargs)
        self._audio_client = audio_client
        self._speaker_id = speaker_id

    def can_generate_metrics(self) -> bool:
        """Check if the service can generate metrics.

        Returns:
            True, as Deepgram TTS service supports metrics generation.
        """
        return True

    @traced_tts
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Generate speech from text using G1's TTS API.

        Args:
            text: The text to synthesize into speech.

        Yields:
            Frame: Audio frames containing the synthesized speech, plus start/stop frames.
        """
        logger.debug(f"{self}: Generating TTS [{text}]")

        try:
            await self.start_ttfb_metrics()
            await self.start_tts_usage_metrics(text)

            yield TTSStartedFrame()

            # Note: G1's TtsMaker handles the audio playback internally
            # We don't receive raw PCM data back, so we signal completion
            # If G1's API provides audio data in the future, we would yield
            # TTSAudioRawFrame here with the actual audio data
            # Call G1's TTS maker API
            code = self._audio_client.TtsMaker(text, self._speaker_id)
            await self.stop_ttfb_metrics()

            if code != 0:
                logger.error(f"G1 TTS API returned error code: {code}")
                yield ErrorFrame(f"G1 TTS error: {code}")
                return

            yield TTSStoppedFrame()

            logger.debug(f"{self}: TTS completed for [{text}]")

        except Exception as e:
            logger.exception(f"{self} exception: {e}")
            yield ErrorFrame(f"Error generating speech: {str(e)}")
