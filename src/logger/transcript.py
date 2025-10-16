from loguru import logger

from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.frames.frames import Frame, TranscriptionFrame, InterimTranscriptionFrame


class TranscriptionLogger(FrameProcessor):
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            logger.debug(
                f"Transcription: user: {frame.user_id}, text: {frame.text}, language {frame.language}, skip_tts {frame.skip_tts}"
            )
        elif isinstance(frame, InterimTranscriptionFrame):
            logger.debug(f"Transcription: {frame.text}")

        await self.push_frame(frame, direction)
