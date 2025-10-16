#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Kokoro TTS service implementation."""

import os
import re
import sys
from typing import AsyncGenerator, Optional

import librosa
import numpy as np
import torch
from loguru import logger

from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.services.tts_service import TTSService
from pipecat.utils.tracing.service_decorators import traced_tts

# Kokoro 相关导入
try:
    from kokoro import KModel, KPipeline
except ImportError:
    logger.error("Kokoro library not found. Please install it first.")
    raise


# 默认配置
KOKORO_ZH_REPO_ID = "hexgrad/Kokoro-82M-v1.1-zh"
KOKORO_ZH_DEFAULT_VOICE = "zf_001"
KOKORO_NATIVE_SAMPLE_RATE = 24000


class KokoroLocalTTSService(TTSService):
    """Kokoro Local TTS service implementation."""

    def __init__(
        self,
        *,
        model_name: str = KOKORO_ZH_REPO_ID,
        voice: Optional[str] = None,
        device: str = "cuda",
        torch_dtype: str = "float16",
        compile_mode: Optional[str] = None,
        sample_rate: Optional[int] = KOKORO_NATIVE_SAMPLE_RATE,
        use_speed_adjustment: bool = True,
        **kwargs,
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)

        # 检查编译模式
        if compile_mode and sys.platform != "linux":
            logger.warning(
                "Torch compile is only available on Linux. Disabling compile mode."
            )
            compile_mode = None

        # 设置设备
        self.device = device if torch.cuda.is_available() else "cpu"
        if device == "cuda" and self.device == "cpu":
            logger.warning("CUDA not available, falling back to CPU")

        self.torch_dtype = getattr(torch, torch_dtype)
        self.compile_mode = compile_mode
        self.voice_id = voice if voice is not None else KOKORO_ZH_DEFAULT_VOICE
        self.use_speed_adjustment = use_speed_adjustment

        logger.info(f"Loading Kokoro model {model_name} on {self.device}")

        # 加载模型
        self.voice = None
        if os.path.exists(model_name) or os.path.exists(os.path.expanduser(model_name)):
            # 从本地路径加载
            model_dir = os.path.expanduser(model_name)
            model_weights_path = os.path.join(model_dir, "kokoro-v1_1-zh.pth")
            model_config_path = os.path.join(model_dir, "config.json")
            self.model = (
                KModel(
                    model=model_weights_path,
                    config=model_config_path,
                    repo_id=KOKORO_ZH_REPO_ID,
                )
                .to(self.device)
                .eval()
            )
            # 加载语音
            voice_path = os.path.join(model_dir, f"voices/{self.voice_id}.pt")
            if os.path.exists(voice_path):
                self.voice = torch.load(voice_path, weights_only=True)
        else:
            # 从 HuggingFace 加载
            self.model = KModel(repo_id=model_name).to(self.device).eval()

        # 配置编译模式
        if self.compile_mode:
            self.model.generation_config.cache_implementation = "static"
            self.model.forward = torch.compile(
                self.model.forward, mode=self.compile_mode, fullgraph=True
            )

        # 创建 pipeline
        self.en_pipeline = KPipeline(
            lang_code="a", repo_id=KOKORO_ZH_REPO_ID, model=False
        )
        self.zh_pipeline = KPipeline(
            lang_code="z",
            repo_id=KOKORO_ZH_REPO_ID,
            model=self.model,
            en_callable=self._en_callable,
        )

        # 预热模型
        self._warmup()

        self._settings = {
            "model_name": model_name,
            "device": self.device,
            "voice": self.voice_id,
        }

    def _en_callable(self, text: str) -> str:
        """英文文本的音素处理回调"""
        if text == "Kokoro":
            return "kˈOkəɹO"
        elif text == "Sol":
            return "sˈOl"
        return next(self.en_pipeline(text)).phonemes

    def _speed_callable(self, len_ps: int) -> float:
        """根据音素长度调整语速的回调函数"""
        if not self.use_speed_adjustment:
            return 1.0

        speed = 0.8
        if len_ps <= 83:
            speed = 1
        elif len_ps < 183:
            speed = 1 - (len_ps - 83) / 500
        return speed * 1.1

    def _warmup(self):
        """预热模型"""
        logger.info(f"Warming up {self.__class__.__name__}")

        try:
            dummy_text = "这是一个测试句子。"
            generator = self.zh_pipeline(
                dummy_text, voice=self.voice, speed=self._speed_callable
            )
            result = next(generator)
            _ = result.audio
            logger.info(f"{self.__class__.__name__}: warmed up successfully")
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")

    def _cleanup_sentence(self, text: str) -> str:
        """
        清理句子，以防止 TTS 合成意外停止。
        主要针对中文场景，去除换行符、多余空格、特殊标点等。
        """
        # 将所有换行符替换为空格
        cleaned_sentence = text.replace("\n", "").replace("\r", "")
        # 将多个连续的空格替换为单个空格（中文场景下直接移除）
        cleaned_sentence = re.sub(r"\s+", "", cleaned_sentence)
        # 去除句子两端的空格
        cleaned_sentence = cleaned_sentence.strip()
        # 移除一些可能干扰 TTS 的特殊控制字符或不可见字符
        cleaned_sentence = re.sub(r"[\u0000-\u001F\u007F-\u009F]", "", cleaned_sentence)
        return cleaned_sentence

    def can_generate_metrics(self) -> bool:
        """检查此服务是否可以生成处理指标。

        Returns:
            True，Kokoro 服务支持指标生成。
        """
        return True

    @traced_tts
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """使用 Kokoro 本地模型从文本生成语音。

        Args:
            text: 要转换为语音的文本。

        Yields:
            Frame: 包含合成语音的音频帧和状态帧。
        """
        logger.debug(f"{self}: Generating TTS [{text}]")

        try:
            # 清理文本
            cleaned_text = self._cleanup_sentence(text)
            if not cleaned_text:
                logger.warning("Empty text after cleaning, skipping TTS")
                return

            await self.start_ttfb_metrics()
            await self.start_tts_usage_metrics(text)

            # 选择语言 pipeline
            pipeline = self.zh_pipeline

            # 生成音频
            generator = pipeline(
                cleaned_text, voice=self.voice, speed=self._speed_callable
            )

            result = next(generator)
            audio = result.audio

            if audio is None or audio.numel() == 0:
                logger.warning("Generated empty audio")
                yield ErrorFrame("Generated empty audio")
                return

            # 转换为 numpy
            audio_numpy = audio.cpu().numpy()

            # 重采样（如果需要）
            if self.sample_rate != KOKORO_NATIVE_SAMPLE_RATE:
                audio_resampled = librosa.resample(
                    audio_numpy,
                    orig_sr=KOKORO_NATIVE_SAMPLE_RATE,
                    target_sr=self.sample_rate,
                )
            else:
                audio_resampled = audio_numpy

            # 转换为 int16 格式
            audio_int16 = (audio_resampled * 32768).astype(np.int16)

            # 转换为 bytes
            audio_bytes = audio_int16.tobytes()

            # 发送音频帧
            yield TTSStartedFrame()

            CHUNK_SIZE = self.chunk_size
            for i in range(0, len(audio_bytes), CHUNK_SIZE):
                chunk = audio_bytes[i : i + CHUNK_SIZE]
                if len(chunk) > 0:
                    if i == 0:
                        await self.stop_ttfb_metrics()
                    yield TTSAudioRawFrame(chunk, self.sample_rate, 1)

        except Exception as e:
            logger.error(f"Error in run_tts: {e}", exc_info=True)
            yield ErrorFrame(error=str(e))
        finally:
            logger.debug(f"{self}: Finished TTS [{text}]")
            await self.stop_ttfb_metrics()
            yield TTSStoppedFrame()
