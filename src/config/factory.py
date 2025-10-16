"""
组件工厂
根据配置动态创建 Pipeline 组件
"""

from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.deepseek.llm import DeepSeekLLMService
from pipecat.services.openai import OpenAILLMService
from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)

from patches.pipecat.services.kokoro import KokoroLocalTTSService
from patches.pipecat.processors.filters.wake_check_filter import WakeCheckFilter
from src.sync.audio_notifier import AudioNotifier


class ComponentFactory:
    """组件工厂类"""

    @staticmethod
    def create_transport(config: Dict[str, Any]) -> LocalAudioTransport:
        """
        创建 Transport

        Args:
            config: Transport 配置

        Returns:
            LocalAudioTransport 实例
        """
        transport_type = config.get("type", "local_audio")
        params = config.get("params", {})

        if transport_type != "local_audio":
            raise ValueError(f"不支持的 Transport 类型: {transport_type}")

        # 创建 VAD analyzer
        vad_config = params.get("vad", {})
        vad_analyzer = SileroVADAnalyzer(
            sample_rate=vad_config.get("sample_rate", 16000),
            params=VADParams(stop_secs=vad_config.get("stop_secs", 0.2)),
        )

        # 创建 transport
        transport_params = LocalAudioTransportParams(
            audio_in_enabled=params.get("audio_in_enabled", True),
            audio_out_enabled=params.get("audio_out_enabled", True),
            vad_analyzer=vad_analyzer,
            input_device_index=params.get("input_device_index", None),
            output_device_index=params.get("output_device_index", None),
        )

        logger.info(f"创建 Transport: {transport_type}")
        return LocalAudioTransport(transport_params)

    @staticmethod
    def create_stt(config: Dict[str, Any]):
        """
        创建 STT 服务

        Args:
            config: STT 配置

        Returns:
            STT 服务实例
        """
        stt_type = config.get("type", "whisper")
        params = config.get("params", {})

        if stt_type == "whisper":
            logger.info(f"创建 Whisper STT: {params.get('model')}")
            return WhisperSTTService(
                model=params.get("model", "base"),
                language=params.get("language", "zh"),
            )
        else:
            raise ValueError(f"不支持的 STT 类型: {stt_type}")

    @staticmethod
    def create_llm(config: Dict[str, Any]):
        """
        创建 LLM 服务

        Args:
            config: LLM 配置

        Returns:
            LLM 服务实例
        """
        llm_type = config.get("type", "openai")
        params = config.get("params", {})

        if llm_type == "openai":
            logger.info(f"创建 OpenAI LLM: {params.get('model')}")
            return OpenAILLMService(
                base_url=params.get("base_url"),
                api_key=params.get("api_key"),
                model=params.get("model", "gpt-4o-mini"),
            )
        elif llm_type == "deepseek":
            logger.info(f"创建 DeepSeek LLM: {params.get('model', 'deepseek-chat')}")
            return DeepSeekLLMService(
                api_key=params.get("api_key"),
                model=params.get("model", "deepseek-chat"),
            )
        else:
            raise ValueError(f"不支持的 LLM 类型: {llm_type}")

    @staticmethod
    def create_tts(config: Dict[str, Any]):
        """
        创建 TTS 服务

        Args:
            config: TTS 配置

        Returns:
            TTS 服务实例
        """
        tts_type = config.get("type", "kokoro")
        params = config.get("params", {})

        if tts_type == "kokoro":
            logger.info(f"创建 Kokoro TTS: {params.get('model_name')}")
            return KokoroLocalTTSService(
                model_name=params.get("model_name"),
                voice=params.get("voice", "zf_001"),
                use_speed_adjustment=params.get("use_speed_adjustment", False),
            )
        elif tts_type == "deepgram":
            # 需要添加 import
            from pipecat.services.deepgram.tts import DeepgramTTSService

            logger.info(f"创建 Deepgram TTS: {params.get('voice')}")
            return DeepgramTTSService(
                api_key=params.get("api_key"),
                voice=params.get("voice", "aura-asteria-zh"),
            )
        else:
            raise ValueError(f"不支持的 TTS 类型: {tts_type}")

    @staticmethod
    def create_wake_check_filter(
        config: Dict[str, Any], current_dir: Path
    ) -> Optional[WakeCheckFilter]:
        """
        创建唤醒词过滤器

        Args:
            config: 唤醒词配置
            current_dir: 当前目录路径

        Returns:
            WakeCheckFilter 实例或 None
        """
        if not config.get("enabled", True):
            logger.info("唤醒词过滤器已禁用")
            return None

        wake_words = config.get("wake_words", [])
        idle_words = config.get("idle_words", [])
        audio_config = config.get("audio", {})

        # 创建音频通知器
        wake_notifier = None
        idle_notifier = None

        wake_audio_path = current_dir / audio_config.get(
            "wake_sound", "src/sync/data/wake.wav"
        )
        idle_audio_path = current_dir / audio_config.get(
            "idle_sound", "src/sync/data/idle.wav"
        )
        volume = audio_config.get("volume", 0.8)

        if wake_audio_path.exists():
            wake_notifier = AudioNotifier(str(wake_audio_path), volume=volume)
            logger.info(f"创建唤醒音频通知器: {wake_audio_path}")
        else:
            logger.warning(f"唤醒音频文件未找到: {wake_audio_path}")

        if idle_audio_path.exists():
            idle_notifier = AudioNotifier(str(idle_audio_path), volume=volume)
            logger.info(f"创建空闲音频通知器: {idle_audio_path}")
        else:
            logger.warning(f"空闲音频文件未找到: {idle_audio_path}")

        logger.info(f"创建唤醒词过滤器: wake={wake_words}, idle={idle_words}")
        return WakeCheckFilter(
            wake_phrases=wake_words,
            idle_phrases=idle_words,
            wake_notifier=wake_notifier,
            idle_notifier=idle_notifier,
        )
