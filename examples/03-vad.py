#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from loguru import logger
from datetime import datetime

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.cartesia import CartesiaSTTService
from pipecat.services.deepseek import DeepSeekLLMService
from pipecat.services.deepgram import DeepgramSTTService, DeepgramTTSService
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from pipecat.frames.frames import (
    Frame,
    MetricsFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    InputAudioRawFrame,
)
from pipecat.metrics.metrics import (
    LLMUsageMetricsData,
    ProcessingMetricsData,
    TTFBMetricsData,
    TTSUsageMetricsData,
)

from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext


from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)

load_dotenv(override=True)

logger.remove(0)
CURRENT_DIR = Path(__file__).resolve().parent
LOG_DIR = os.path.join(CURRENT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logger.add(sys.stderr, level="DEBUG")
logger.add(log_file, level="DEBUG")


class MetricsLogger(FrameProcessor):
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, MetricsFrame):
            for d in frame.data:
                if isinstance(d, TTFBMetricsData):
                    print(f"!!! MetricsFrame: {frame}, ttfb: {d.value}")
                elif isinstance(d, ProcessingMetricsData):
                    print(f"!!! MetricsFrame: {frame}, processing: {d.value}")
                elif isinstance(d, LLMUsageMetricsData):
                    tokens = d.value
                    print(
                        f"!!! MetricsFrame: {frame}, tokens: {tokens.prompt_tokens}, characters: {tokens.completion_tokens}"
                    )
                elif isinstance(d, TTSUsageMetricsData):
                    print(f"!!! MetricsFrame: {frame}, characters: {d.value}")
        elif isinstance(frame, InterimTranscriptionFrame) or isinstance(
            frame, TranscriptionFrame
        ):
            logger.debug(frame)
        elif not isinstance(frame, InputAudioRawFrame):
            logger.debug(frame)
        await self.push_frame(frame, direction)


async def main():
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_in_passthrough=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(
                sample_rate=16000, params=VADParams(stop_secs=0.2)
            ),
            input_device_index=1,
        )
    )

    # stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    stt = CartesiaSTTService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",
    )

    llm = DeepSeekLLMService(api_key=os.getenv("DEEPSEEK_API_KEY"))

    tts = DeepgramTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
    )

    ml = MetricsLogger()

    messages = [
        {
            "role": "system",
            "content": "You are a helpful LLM in a WebRTC call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a creative and helpful way.",
        },
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),
            ml,
        ]
    )
    """ stt,
    context_aggregator.user(),
    llm,
    tts,
    transport.output(),
    context_aggregator.assistant(), """

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=300,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        # Kick off the conversation.
        messages.append(
            {"role": "system", "content": "Please introduce yourself to the user."}
        )
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False if sys.platform == "win32" else True)

    await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
