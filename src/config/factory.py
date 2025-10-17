"""
组件工厂
根据配置动态创建 Pipeline 组件
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from loguru import logger

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.deepseek.llm import DeepSeekLLMService
from pipecat.services.openai import OpenAILLMService
from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)
from pipecat.audio.interruptions.base_interruption_strategy import (
    BaseInterruptionStrategy,
)
from pipecat.audio.interruptions.min_words_interruption_strategy import (
    MinWordsInterruptionStrategy,
)

from patches.pipecat.services.kokoro import KokoroLocalTTSService
from patches.pipecat.processors.filters.wake_check_filter import WakeCheckFilter
from patches.pipecat.audio.interruptions.keyword_interruption_strategy import (
    KeywordInterruptionStrategy,
)
from patches.pipecat.audio.interruptions.never_interruption_strategy import (
    NeverInterruptionStrategy,
)
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
            raise ValueError(f"Unsupported Transport type: {transport_type}")

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

        logger.info(f"Creating Transport: {transport_type}")
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
            logger.info(f"Creating Whisper STT: {params.get('model')}")
            return WhisperSTTService(
                model=params.get("model", "base"),
                language=params.get("language", "zh"),
            )
        else:
            raise ValueError(f"Unsupported STT type: {stt_type}")

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
            logger.info(f"Creating OpenAI LLM: {params.get('model')}")
            return OpenAILLMService(
                base_url=params.get("base_url"),
                api_key=params.get("api_key"),
                model=params.get("model", "gpt-4o-mini"),
            )
        elif llm_type == "deepseek":
            logger.info(
                f"Creating DeepSeek LLM: {params.get('model', 'deepseek-chat')}"
            )
            return DeepSeekLLMService(
                api_key=params.get("api_key"),
                model=params.get("model", "deepseek-chat"),
            )
        else:
            raise ValueError(f"Unsupported LLM type: {llm_type}")

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
            logger.info(f"Creating Kokoro TTS: {params.get('model_name')}")
            return KokoroLocalTTSService(
                model_name=params.get("model_name"),
                voice=params.get("voice", "zf_001"),
                use_speed_adjustment=params.get("use_speed_adjustment", False),
            )
        elif tts_type == "deepgram":
            # 需要添加 import
            from pipecat.services.deepgram.tts import DeepgramTTSService

            logger.info(f"Creating Deepgram TTS: {params.get('voice')}")
            return DeepgramTTSService(
                api_key=params.get("api_key"),
                voice=params.get("voice", "aura-asteria-zh"),
            )
        else:
            raise ValueError(f"Unsupported TTS type: {tts_type}")

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
            logger.info("Wake word filter disabled")
            return None

        wake_words = config.get("wake_words", [])
        idle_words = config.get("idle_words", [])
        audio_config = config.get("audio", {})
        wake_timeout = config.get("wake_timeout", None)

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
            logger.info(f"Creating wake audio notifier: {wake_audio_path}")
        else:
            logger.warning(f"Wake audio file not found: {wake_audio_path}")

        if idle_audio_path.exists():
            idle_notifier = AudioNotifier(str(idle_audio_path), volume=volume)
            logger.info(f"Creating idle audio notifier: {idle_audio_path}")
        else:
            logger.warning(f"Idle audio file not found: {idle_audio_path}")

        # 构建日志消息
        log_msg = f"Creating wake word filter: wake={wake_words}, idle={idle_words}"
        if wake_timeout:
            log_msg += f", timeout={wake_timeout}s"
        logger.info(log_msg)

        return WakeCheckFilter(
            wake_phrases=wake_words,
            idle_phrases=idle_words,
            wake_notifier=wake_notifier,
            idle_notifier=idle_notifier,
            wake_timeout=wake_timeout,
        )

    @staticmethod
    def create_interruption_strategies(
        config: List[Dict[str, Any]],
    ) -> List[BaseInterruptionStrategy]:
        """
        创建中断策略列表

        Args:
            config: 中断策略配置列表，每个策略包含 type 和 params

        Returns:
            BaseInterruptionStrategy 列表

        Example config:
            - type: "keyword"
              params:
                keywords: ["小白小白"]
            - type: "min_words"
              params:
                min_words: 4
        """
        if not config:
            logger.info("No interruption strategies configured")
            return []

        strategies = []

        for strategy_config in config:
            strategy_type = strategy_config.get("type")
            params = strategy_config.get("params", {})

            if strategy_type == "keyword":
                keywords = params.get("keywords", [])
                if not keywords:
                    logger.warning(
                        "Keyword interruption strategy has no keywords, skipping"
                    )
                    continue
                strategy = KeywordInterruptionStrategy(keywords=keywords)
                logger.info(
                    f"Creating keyword interruption strategy: keywords={keywords}"
                )
                strategies.append(strategy)

            elif strategy_type == "min_words":
                min_words = params.get("min_words", 3)
                strategy = MinWordsInterruptionStrategy(min_words=min_words)
                logger.info(
                    f"Creating min words interruption strategy: min_words={min_words}"
                )
                strategies.append(strategy)

            elif strategy_type == "never":
                strategy = NeverInterruptionStrategy()
                logger.info("Creating never interruption strategy")
                strategies.append(strategy)

            else:
                logger.warning(
                    f"Unsupported interruption strategy type: {strategy_type}"
                )

        if not strategies:
            logger.warning("No interruption strategies created")
        else:
            logger.info(f"Created {len(strategies)} interruption strategies")

        return strategies

    @staticmethod
    def create_tools(
        config: Dict[str, Any],
    ) -> Tuple[Optional[ToolsSchema], List[Tuple[str, Callable]]]:
        """
        根据配置创建工具模式和函数列表

        Args:
            config: 函数配置字典

        Returns:
            (ToolsSchema, 函数列表) - 工具模式对象和需要注册的函数列表
            函数列表格式: [(function_name, function_callable), ...]
            如果未启用任何函数，返回 (None, [])
        """
        if not config or not config.get("enabled", False):
            logger.info("Function calling feature not enabled")
            return None, []

        enabled_groups = config.get("enabled_groups", [])
        if not enabled_groups:
            logger.warning("No enabled function groups configured")
            return None, []

        all_schemas = []
        all_functions = []

        # 根据启用的函数组加载对应的函数
        for group in enabled_groups:
            if group == "calculator":
                from src.functions.calculator import (
                    get_calculator_tools,
                    calculate_add,
                    calculate_subtract,
                    calculate_multiply,
                    calculate_divide,
                )

                # 获取函数模式
                calculator_tools = get_calculator_tools()
                all_schemas.extend(calculator_tools.standard_tools)

                # 添加函数实现
                all_functions.extend(
                    [
                        ("calculate_add", calculate_add),
                        ("calculate_subtract", calculate_subtract),
                        ("calculate_multiply", calculate_multiply),
                        ("calculate_divide", calculate_divide),
                    ]
                )
                logger.info("loaded calculator functions")

            elif group == "weather":
                from src.functions.weather import (
                    get_weather_tools,
                    get_current_weather,
                    get_weather_forecast,
                )

                # 获取函数模式
                weather_tools = get_weather_tools()
                all_schemas.extend(weather_tools.standard_tools)

                # 添加函数实现
                all_functions.extend(
                    [
                        ("get_current_weather", get_current_weather),
                        ("get_weather_forecast", get_weather_forecast),
                    ]
                )
                logger.info("loaded weather functions")

            # 未来可以添加更多函数组
            # elif group == "search":
            #     from src.functions.search import ...
            #     ...
            else:
                logger.warning(f"Unknown function group: {group}")

        if not all_schemas:
            logger.warning("No functions loaded")
            return None, []

        # 创建 ToolsSchema
        tools_schema = ToolsSchema(standard_tools=all_schemas)
        logger.info(f"Created tools schema with {len(all_schemas)} functions")

        return tools_schema, all_functions
