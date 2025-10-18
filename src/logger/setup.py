"""
日志配置模块
提供统一的 loguru logger 配置
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from loguru import logger


def setup_logger(
    log_level: str = "INFO",
    log_dir: Optional[str] = None,
    enable_file_logging: bool = True,
    enable_console_logging: bool = True,
) -> None:
    """
    配置 loguru logger

    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: 日志文件目录，默认为项目根目录下的 logs/
        enable_file_logging: 是否启用文件日志
        enable_console_logging: 是否启用控制台日志
    """
    # 移除默认的 logger
    logger.remove()

    # 配置控制台日志
    if enable_console_logging:
        logger.add(
            sys.stdout,
            level=log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>",
            colorize=True,
        )

    # 配置文件日志
    if enable_file_logging:
        if log_dir is None:
            # 默认日志目录
            project_root = Path(__file__).resolve().parent.parent.parent
            log_dir = project_root / "logs"
        else:
            log_dir = Path(log_dir)

        log_dir.mkdir(parents=True, exist_ok=True)

        # 创建日志文件名（带时间戳）
        log_file = log_dir / f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        logger.add(
            log_file,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}",
            rotation="100 MB",  # 日志文件达到 100MB 时轮转
            retention="30 days",  # 保留 30 天的日志
            compression="zip",  # 压缩旧日志
        )

        logger.info(f"Log file: {log_file}")

    logger.info(f"Log level: {log_level}")


def get_logger():
    """
    获取 logger 实例

    Returns:
        logger 实例
    """
    return logger
