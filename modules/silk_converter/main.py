#!/usr/bin/env python
"""silk 转换器 — 音频文件转 silk v3 (QQ 语音格式), 跨平台

插件中获取:
    silk = bot.module_manager.get("silk_converter")
    path, duration = await silk.to_silk("audio.mp3")            # 任意音频 → .silk
    path, duration = await silk.to_wav("voice.silk")            # silk → .wav

也可独立命令行使用 (无需启动框架):
    python -m modules.silk_converter.converter input.mp3 [output.silk]
"""

__module_meta__ = {
    'name': 'silk 转换器',
    'description': '音频文件转 silk v3 (QQ 语音格式), 支持 mp3/wav/m4a/flac/ogg 等, 跨平台',
    'version': '1.0.0',
    'author': 'ElainaBot',
}

import asyncio

from core.base.logger import EXTENSION, get_logger
from modules.silk_converter.converter import DEFAULT_RATE, audio_to_silk, silk_to_wav

log = get_logger(EXTENSION, 'silk转换器')


class SilkConverter:
    """异步封装 (编码在线程池执行, 不阻塞事件循环)"""

    async def to_silk(self, src, out_path=None, rate=DEFAULT_RATE):
        """音频文件转 silk v3, 返回 (silk 路径, 时长秒)"""
        return await asyncio.to_thread(audio_to_silk, src, out_path, rate)

    async def to_wav(self, src, out_path=None):
        """silk v3 转 WAV, 返回 (wav 路径, 时长秒)"""
        return await asyncio.to_thread(silk_to_wav, src, out_path)


async def setup(ctx):
    log.info('silk 转换器已加载')
    return SilkConverter()
