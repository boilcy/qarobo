"""
配置加载器
使用 OmegaConf 加载和解析 YAML 配置文件，支持环境变量替换和结构化访问
"""

from pathlib import Path
from typing import Any, Optional

from loguru import logger
from omegaconf import OmegaConf, DictConfig


class ConfigLoader:
    """配置加载器类，基于 OmegaConf"""

    def __init__(self, config_path: str = "config/default.yaml"):
        """
        初始化配置加载器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config: Optional[DictConfig] = None
        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        # 使用 OmegaConf 加载配置
        self.config = OmegaConf.load(self.config_path)

        # OmegaConf 自动支持环境变量解析
        # 使用 ${env:VAR_NAME} 或 ${oc.env:VAR_NAME} 格式
        OmegaConf.resolve(self.config)

        logger.info(f"Config file loaded: {self.config_path}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值，支持点号分隔的嵌套键

        Args:
            key: 配置键，如 "llm.params.model"
            default: 默认值

        Returns:
            配置值
        """
        try:
            return OmegaConf.select(self.config, key, default=default)
        except Exception as e:
            logger.warning(f"Failed to get config {key}: {e}")
            return default

    def get_transport_config(self) -> DictConfig:
        """获取 Transport 配置"""
        return self.config.transport if self.config else OmegaConf.create({})

    def get_stt_config(self) -> DictConfig:
        """获取 STT 配置"""
        return self.config.stt if self.config else OmegaConf.create({})

    def get_llm_config(self) -> DictConfig:
        """获取 LLM 配置"""
        return self.config.llm if self.config else OmegaConf.create({})

    def get_tts_config(self) -> DictConfig:
        """获取 TTS 配置"""
        return self.config.tts if self.config else OmegaConf.create({})

    def get_stt_mute_config(self) -> DictConfig:
        return self.config.stt_mute if self.config else OmegaConf.create({})

    def get_wake_check_config(self) -> DictConfig:
        """获取唤醒词配置"""
        return self.config.wake_check if self.config else OmegaConf.create({})

    def get_interruption_strategies_config(self) -> DictConfig:
        """获取中断策略配置"""
        return (
            self.config.interruption_strategies if self.config else OmegaConf.create({})
        )

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self.get("system_prompt", "")

    def get_welcome_message(self) -> str:
        """获取欢迎消息"""
        return self.get("welcome_message", "")

    def get_pipeline_config(self) -> DictConfig:
        """获取 Pipeline 配置"""
        return self.config.pipeline if self.config else OmegaConf.create({})

    def get_logging_config(self) -> DictConfig:
        """获取日志配置"""
        return self.config.logging if self.config else OmegaConf.create({})

    def reload(self):
        """重新加载配置文件"""
        self._load_config()
        logger.info("Config reloaded")

    def to_dict(self) -> dict:
        """
        将配置转换为普通字典

        Returns:
            配置字典
        """
        return OmegaConf.to_container(self.config, resolve=True)

    def merge_from_dict(self, config_dict: dict):
        """
        从字典合并配置

        Args:
            config_dict: 配置字典
        """
        if self.config is None:
            self.config = OmegaConf.create(config_dict)
        else:
            self.config = OmegaConf.merge(self.config, config_dict)

        logger.info("Config merged from dict")

    def __repr__(self) -> str:
        """返回配置的字符串表示"""
        return OmegaConf.to_yaml(self.config) if self.config else ""
