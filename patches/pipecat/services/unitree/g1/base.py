"""Unitree G1 基础管理模块

管理 ChannelFactory 和 AudioClient 的生命周期，提供单例模式的全局访问。
"""

from typing import Optional
from loguru import logger
from pydantic import BaseModel

from .utils import Singleton

try:
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from patches.unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error("In order to use Unitree G1, you need to install unitree_sdk2py.")
    raise Exception(f"Missing module: {e}")


class UniTreeG1AudioConfig(BaseModel):
    """G1 音频配置参数"""

    netiface: str = "eth0"  # 网络接口名称
    domain_id: int = 0  # DDS Domain ID
    timeout: float = 10.0  # AudioClient 超时时间（秒）


class UniTreeG1AudioManager(Singleton):
    """G1 音频管理器 - 单例模式

    管理 ChannelFactory 初始化和 AudioClient 实例的生命周期。
    确保在整个应用程序中只有一个 AudioClient 实例，并在 STT 和 TTS 之间共享。

    使用方式:
        # 初始化管理器
        config = UniTreeG1AudioConfig(netiface="enp60s0")
        manager = UniTreeG1AudioManager.initialize(config)

        # 获取 AudioClient 实例
        audio_client = manager.get_audio_client()

        # 在应用退出时清理
        manager.cleanup()
    """

    def __init__(self, config: UniTreeG1AudioConfig):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._config = config
        self._audio_client: Optional[AudioClient] = None
        self._channel_factory_initialized = False
        self._initialized = False

    @classmethod
    def initialize(cls, config: UniTreeG1AudioConfig) -> "UniTreeG1AudioManager":
        instance = cls(config)

        if instance._initialized:
            logger.warning(
                "UniTreeG1AudioManager already initialized, returning existing instance"
            )
            return instance

        logger.info("Initializing UniTreeG1AudioManager...")

        # 初始化 ChannelFactory
        instance._initialize_channel_factory()

        # 创建并初始化 AudioClient
        instance._initialize_audio_client()

        # 标记为已完全初始化
        instance._initialized = True

        logger.info("UniTreeG1AudioManager initialized")
        return instance

    def _initialize_channel_factory(self):
        """初始化 DDS ChannelFactory"""
        if self._channel_factory_initialized:
            logger.warning("ChannelFactory already initialized")
            return

        logger.info(
            f"Initializing ChannelFactory (domain_id={self._config.domain_id}, "
            f"netiface={self._config.netiface})"
        )

        try:
            ChannelFactoryInitialize(self._config.domain_id, self._config.netiface)
            self._channel_factory_initialized = True
            logger.info("ChannelFactory initialized successfully")
        except Exception as e:
            logger.error(f"ChannelFactory initialization failed: {e}")
            raise

    def _initialize_audio_client(self):
        """创建并初始化 AudioClient"""
        if self._audio_client is not None:
            logger.warning("AudioClient already initialized")
            return

        logger.info("Creating and initializing AudioClient...")

        try:
            self._audio_client = AudioClient()
            self._audio_client.SetTimeout(self._config.timeout)
            self._audio_client.Init()
            logger.info("AudioClient initialized successfully")
        except Exception as e:
            logger.error(f"AudioClient initialization failed: {e}")
            raise

    def get_audio_client(self) -> AudioClient:
        """获取 AudioClient 实例

        Returns:
            AudioClient 实例

        Raises:
            RuntimeError: 如果 AudioClient 未初始化
        """
        if self._audio_client is None:
            raise RuntimeError(
                "AudioClient not initialized, please call UniTreeG1AudioManager.initialize()"
            )
        return self._audio_client

    def cleanup(self):
        """清理资源"""
        logger.info("Cleaning up UniTreeG1AudioManager resources...")

        # 清理 AudioClient
        if self._audio_client is not None:
            # AudioClient 可能没有显式的清理方法
            # 但我们可以释放引用让 Python GC 处理
            self._audio_client = None
            logger.debug("AudioClient cleaned up")

        # 重置初始化标志
        self._initialized = False
        self._channel_factory_initialized = False

        logger.info("UniTreeG1AudioManager resources cleaned up")
