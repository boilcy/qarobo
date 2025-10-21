#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import asyncio
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

# !!!IMPORTANT: This import is aim to override the loguru logger that set by kokoro
from kokoro import KModel, KPipeline  # noqa: F401

from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)

from src.config.loader import ConfigLoader
from src.config.factory import ComponentFactory
from src.logger import MetricsLogger, TranscriptionLogger, setup_logger, get_logger

# 导入 G1 服务
from patches.pipecat.services.unitree.g1 import (
    UniTreeG1AudioConfig,
    UniTreeG1AudioManager,
    UnitreeG1TTSService,
    UnitreeG1STTServiceParams,
    UnitreeG1STTService,
)

load_dotenv(override=True)

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

CURRENT_DIR = Path(__file__).resolve().parent


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="QARobo Pipecat - 语音对话机器人",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                                    # 使用默认配置
  %(prog)s --verbose                          # 启用详细日志
  %(prog)s --config config/deepseek.yaml      # 使用自定义配置
  %(prog)s -v -c config/custom.yaml           # 组合使用
        """,
    )

    parser.add_argument(
        "-c",
        "--config",
        dest="config_path",
        default="config/g1.yaml",
        help="配置文件路径 (默认: config/g1.yaml)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="启用详细日志输出 (设置日志级别为 DEBUG)",
    )

    parser.add_argument(
        "--log-level",
        dest="log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="指定日志级别 (覆盖 --verbose 和配置文件设置)",
    )

    parser.add_argument(
        "--log-dir",
        dest="log_dir",
        help="日志文件目录 (默认: logs/)",
    )

    parser.add_argument(
        "--no-file-log",
        dest="enable_file_log",
        action="store_false",
        help="禁用文件日志，仅输出到控制台",
    )

    return parser.parse_args()


async def main():
    # 解析命令行参数
    args = parse_args()

    # 加载配置
    config = ConfigLoader(args.config_path)

    # 确定日志级别
    log_level = "INFO"  # 默认级别
    if args.log_level:
        # 命令行指定的日志级别优先
        log_level = args.log_level
    elif args.verbose:
        # --verbose 标志设置为 DEBUG
        log_level = "DEBUG"
    else:
        # 从配置文件读取
        logging_config = config.get_logging_config()
        log_level = logging_config.get("level", "INFO")

    # 确定日志目录
    log_dir = args.log_dir or config.get("logging.log_dir", "logs")

    # 设置 logger
    setup_logger(
        log_level=log_level,
        log_dir=log_dir,
        enable_file_logging=args.enable_file_log,
        enable_console_logging=True,
    )

    logger = get_logger()
    logger.info("=" * 60)
    logger.info("QARobo Pipecat starting...")
    logger.info(f"Config file: {args.config_path}")
    logger.info(f"Log level: {log_level}")
    logger.info("=" * 60)

    # 初始化 G1 音频管理器
    g1_audio_config_dict = config.get("g1_audio", {})
    g1_audio_config = UniTreeG1AudioConfig(
        netiface=g1_audio_config_dict.get("netiface", "eth0"),
        domain_id=g1_audio_config_dict.get("domain_id", 0),
        timeout=g1_audio_config_dict.get("timeout", 10.0),
    )

    # 初始化单例管理器
    g1_manager = UniTreeG1AudioManager.initialize(g1_audio_config)
    audio_client = g1_manager.get_audio_client()

    logger.info("G1 audio system initialized successfully")

    # 创建 STT 服务 - 使用 G1 原生 ASR
    stt_config_dict = config.get_stt_config()
    stt_params_dict = stt_config_dict.get("params", {})
    stt_params = UnitreeG1STTServiceParams(**stt_params_dict)
    stt = UnitreeG1STTService(params=stt_params)

    # 创建 LLM 服务
    llm = ComponentFactory.create_llm(config.get_llm_config())

    # 创建 TTS 服务 - 使用 G1 原生 TTS
    tts_config_dict = config.get_tts_config()
    tts_params_dict = tts_config_dict.get("params", {})
    tts = UnitreeG1TTSService(
        audio_client=audio_client,
        speaker_id=tts_params_dict.get("speaker_id", 0),
    )

    # 创建日志记录器
    tl = TranscriptionLogger()
    ml = MetricsLogger()

    # 创建函数工具和注册函数
    functions_config = config.get("functions", {})
    tools_schema, functions_list = ComponentFactory.create_tools(functions_config)

    # 注册函数到 LLM
    if functions_list:
        for function_name, function_callable in functions_list:
            llm.register_function(function_name, function_callable)
            logger.info(f"registered function: {function_name}")

        # 添加函数调用开始事件处理器
        @llm.event_handler("on_function_calls_started")
        async def on_function_calls_started(service, function_calls):
            logger.info(
                f"function calls started: {[fc.function_name for fc in function_calls]}"
            )
            await tts.queue_frame(TTSSpeakFrame("让我想一想"))

    # 从配置获取系统提示词
    system_prompt = config.get_system_prompt()
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
    ]

    hey_robot_filter = ComponentFactory.create_wake_check_filter(
        config.get_wake_check_config(), CURRENT_DIR
    )

    # 创建 LLM Context，如果有工具则传入
    context = (
        LLMContext(messages, tools_schema) if tools_schema else LLMContext(messages)
    )
    context_aggregator = LLMContextAggregatorPair(context)

    pipeline_components = [stt, tl]

    # 如果启用了唤醒词过滤器，添加到 pipeline
    if hey_robot_filter is not None:
        pipeline_components.append(hey_robot_filter)

    pipeline_components.extend(
        [
            context_aggregator.user(),
            llm,
            tts,
            ml,
            context_aggregator.assistant(),
        ]
    )

    pipeline = Pipeline(pipeline_components)

    interruption_strategies = ComponentFactory.create_interruption_strategies(
        config.get_interruption_strategies_config()
    )

    # 从配置获取 Pipeline 参数
    pipeline_config = config.get_pipeline_config()
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=pipeline_config.get("enable_metrics", True),
            enable_usage_metrics=pipeline_config.get("enable_usage_metrics", True),
            interruption_strategies=interruption_strategies,
        ),
        idle_timeout_secs=pipeline_config.get("idle_timeout_secs", 300),
        cancel_on_idle_timeout=False,
    )

    runner = PipelineRunner(handle_sigint=False if sys.platform == "win32" else True)

    # everything is ready, notify the user using audio
    if hey_robot_filter is not None:
        if hey_robot_filter._wake_notifier is not None:
            await hey_robot_filter._wake_notifier.notify()

    try:
        await runner.run(task)
    finally:
        # 清理 G1 音频资源
        logger.info("正在清理 G1 音频资源...")
        g1_manager.cleanup()
        logger.info("程序退出")


if __name__ == "__main__":
    asyncio.run(main())
