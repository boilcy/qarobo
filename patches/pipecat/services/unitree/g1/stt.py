import asyncio
from datetime import datetime
from loguru import logger
from pydantic import BaseModel

from pipecat.processors.frame_processor import FrameProcessor
from pipecat.frames.frames import (
    Frame,
    FrameDirection,
    StartFrame,
    EndFrame,
    StopFrame,
    CancelFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    SystemFrame,
    TranscriptionFrame,
)

try:
    from unitree_sdk2py.core.channel import ChannelSubscriber
    from unitree_sdk2py.idl.std_msgs.msg.dds_ import String_
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error("In order to use Unitree G1, you need to install unitree_sdk2py.")
    raise Exception(f"Missing module: {e}")

G1_AUDIO_SUBSCRIBE_TOPIC: str = "rt/audio_msg"


class UnitreeG1STTServiceParams(BaseModel):
    """G1 STT 服务参数"""

    audio_subscribe_topic: str = G1_AUDIO_SUBSCRIBE_TOPIC


class UnitreeG1STTService(FrameProcessor):
    """G1 STT Service - 直接接收来自 G1 机器人的 STT 识别结果

    G1 的特殊之处在于它的 ASR 模块直接输出文本结果，而不是音频流。
    我们通过 DDS 订阅 'rt/audio_msg' 主题来接收识别结果。

    注意: ChannelFactoryInitialize 应该在外部完成（通常在 base.py 中）
    """

    def __init__(self, params: UnitreeG1STTServiceParams, **kwargs):
        super().__init__(**kwargs)

        self._params = params

        # DDS 订阅者
        self._subscriber: ChannelSubscriber = None

        # 使用队列在回调线程和异步上下文之间传递消息
        self._message_queue: asyncio.Queue = asyncio.Queue()

        # 消息处理任务
        self._process_task = None

        # Track bot speaking state for interruption logic
        self._bot_speaking = False

        # Track user speaking state for interruption logic
        self._user_speaking = False

        # If the transport is stopped with `StopFrame` we might still be
        # receiving frames from the transport but we really don't want to push
        # them downstream until we get another `StartFrame`.
        self._paused = False

    async def start(self, frame: StartFrame):
        """启动 STT Service，初始化 DDS 订阅者"""
        self._paused = False
        self._user_speaking = False

        # 创建 DDS 订阅者
        self._subscriber = ChannelSubscriber(
            self._params.audio_subscribe_topic, String_
        )

        # 初始化订阅者，设置消息处理回调
        self._subscriber.Init(self._audio_handler, 10)
        logger.info(
            f"UnitreeG1STTService: Subscribed to topic '{self._params.audio_subscribe_topic}'"
        )

        # 启动消息处理任务
        self._process_task = asyncio.create_task(self._process_messages())

    async def stop(self, frame: EndFrame):
        """停止 ASR Transport 并清理资源

        Args:
            frame: The end frame signaling transport shutdown.
        """
        logger.info("UnitreeG1STTService: Stopping...")

        # 停止消息处理任务
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
            self._process_task = None

        # 清理订阅者
        if self._subscriber:
            # ChannelSubscriber 可能没有显式的清理方法，但我们可以释放引用
            self._subscriber = None

        logger.info("UnitreeG1STTService: Stopped")

    async def pause(self, frame: StopFrame):
        """暂时暂停 Transport

        Args:
            frame: The stop frame signaling transport pause.
        """
        self._paused = True
        logger.debug("UnitreeG1STTService: Paused")

    async def cancel(self, frame: CancelFrame):
        """取消 Transport 并停止所有处理

        Args:
            frame: The cancel frame signaling immediate cancellation.
        """
        await self.stop(frame)

    async def cleanup(self):
        """清理资源"""
        await super().cleanup()

    def _audio_handler(self, msg: String_):
        """DDS 消息回调处理器（在 DDS 线程中调用）

        由于这是在回调线程中调用的，我们不能直接使用 await。
        将消息放入队列，由异步任务处理。

        Args:
            msg: 接收到的 DDS 消息，包含 STT 识别结果
        """
        try:
            # 将消息放入队列（线程安全）
            asyncio.get_event_loop().call_soon_threadsafe(
                self._message_queue.put_nowait, msg.data
            )
        except Exception as e:
            logger.error(f"UnitreeG1STTService: Error in audio handler: {e}")

    async def _process_messages(self):
        """异步处理消息队列中的 STT 结果"""
        try:
            while True:
                # 从队列中获取消息
                text = await self._message_queue.get()

                # 如果已暂停，跳过处理
                if self._paused:
                    logger.debug(
                        f"UnitreeG1STTService: Paused, skipping message: {text}"
                    )
                    continue

                logger.info(f"UnitreeG1STTService: Received STT result: {text}")

                # 推送转录帧到下游
                await self.push_frame(
                    TranscriptionFrame(
                        text=text, user_id="user", timestamp=datetime.now().isoformat()
                    )
                )

        except asyncio.CancelledError:
            logger.debug("UnitreeG1STTService: Message processing task cancelled")
            raise
        except Exception as e:
            logger.error(f"UnitreeG1STTService: Error processing messages: {e}")

    #
    # Frame processor
    #

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames and handle transport-specific logic.

        Args:
            frame: The frame to process.
            direction: The direction of frame flow in the pipeline.
        """
        await super().process_frame(frame, direction)

        # Specific system frames
        if isinstance(frame, StartFrame):
            # Push StartFrame before start(), because we want StartFrame to be
            # processed by every processor before any other frame is processed.
            await self.push_frame(frame, direction)
            await self.start(frame)
        elif isinstance(frame, CancelFrame):
            await self.cancel(frame)
            await self.push_frame(frame, direction)
        elif isinstance(frame, BotStartedSpeakingFrame):
            await self._handle_bot_started_speaking(frame)
            await self.push_frame(frame, direction)
        elif isinstance(frame, BotStoppedSpeakingFrame):
            await self._handle_bot_stopped_speaking(frame)
            await self.push_frame(frame, direction)
        # All other system frames
        elif isinstance(frame, SystemFrame):
            await self.push_frame(frame, direction)
        # Control frames
        elif isinstance(frame, EndFrame):
            # Push EndFrame before stop(), because stop() waits on the task to
            # finish and the task finishes when EndFrame is processed.
            await self.push_frame(frame, direction)
            await self.stop(frame)
        elif isinstance(frame, StopFrame):
            await self.push_frame(frame, direction)
            await self.pause(frame)
        # Other frames
        else:
            await self.push_frame(frame, direction)

    #
    # Handle bot speaking state
    #

    async def _handle_bot_started_speaking(self, frame: BotStartedSpeakingFrame):
        """Update bot speaking state when bot starts speaking."""
        self._bot_speaking = True

    async def _handle_bot_stopped_speaking(self, frame: BotStoppedSpeakingFrame):
        """Update bot speaking state when bot stops speaking."""
        self._bot_speaking = False
