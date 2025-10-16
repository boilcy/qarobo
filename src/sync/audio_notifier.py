"""Audio notifier implementation for playing local audio files.

This module provides an implementation of BaseNotifier that plays
local audio files as notification sounds.
"""

import asyncio
import wave
from pathlib import Path
from typing import Optional

import pyaudio
from loguru import logger

from src.sync.base_notifier import BaseNotifier


class AudioNotifier(BaseNotifier):
    """Audio notifier that plays local audio files.

    This notifier plays a WAV file when notify() is called.
    Useful for providing audio feedback when wake/idle phrases are detected.
    """

    def __init__(self, audio_file: str, volume: float = 1.0):
        """Initialize the audio notifier.

        Args:
            audio_file: Path to the WAV file to play.
            volume: Volume level (0.0 to 1.0). Default is 1.0.
        """
        self._audio_file = Path(audio_file)
        self._volume = max(0.0, min(1.0, volume))  # Clamp between 0 and 1
        self._is_playing = False
        self._play_task: Optional[asyncio.Task] = None

        if not self._audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        # Validate it's a WAV file
        try:
            with wave.open(str(self._audio_file), "rb") as wf:
                self._channels = wf.getnchannels()
                self._sample_width = wf.getsampwidth()
                self._framerate = wf.getframerate()
        except Exception as e:
            raise ValueError(f"Invalid WAV file: {e}")

        logger.info(f"AudioNotifier initialized with {audio_file}")

    async def notify(self):
        """Play the audio notification.

        Starts playing the audio file asynchronously. If already playing,
        restarts from the beginning.
        """
        # Cancel any existing playback
        if self._play_task and not self._play_task.done():
            self._play_task.cancel()
            try:
                await self._play_task
            except asyncio.CancelledError:
                pass

        # Start new playback
        self._play_task = asyncio.create_task(self._play_audio())
        logger.debug(f"Audio notification triggered: {self._audio_file}")

    async def wait(self):
        """Wait for the audio notification to complete.

        Blocks until the audio has finished playing.
        """
        if self._play_task:
            try:
                await self._play_task
            except asyncio.CancelledError:
                pass

    async def _play_audio(self):
        """Internal method to play the audio file."""
        try:
            self._is_playing = True

            # Run the blocking audio playback in a thread
            await asyncio.to_thread(self._play_audio_sync)

        except Exception as e:
            logger.error(f"Error playing audio: {e}")
        finally:
            self._is_playing = False

    def _play_audio_sync(self):
        """Synchronous audio playback using PyAudio."""
        try:
            # Open the WAV file
            with wave.open(str(self._audio_file), "rb") as wf:
                # Initialize PyAudio
                p = pyaudio.PyAudio()

                # Open stream
                stream = p.open(
                    format=p.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True,
                )

                # Read and play audio in chunks
                chunk_size = 1024
                data = wf.readframes(chunk_size)

                while data:
                    # Apply volume if needed
                    if self._volume < 1.0:
                        # Simple volume adjustment (for demonstration)
                        import array

                        audio_data = array.array("h", data)
                        for i in range(len(audio_data)):
                            audio_data[i] = int(audio_data[i] * self._volume)
                        data = audio_data.tobytes()

                    stream.write(data)
                    data = wf.readframes(chunk_size)

                # Cleanup
                stream.stop_stream()
                stream.close()
                p.terminate()

        except Exception as e:
            logger.error(f"Error in synchronous audio playback: {e}")
            raise
