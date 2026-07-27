#!/usr/bin/env python
"""音频转 silk v3 (QQ 语音格式) — 跨平台核心实现

任意格式音频 → 16bit 单声道 PCM → silk v3 (tencent 变体, 可直接作为 QQ 语音发送)。

解码链 (按可用性自动选择, 任一可用即可):
    1. 系统 PATH 中的 ffmpeg
    2. imageio-ffmpeg (pip 包, 自带各平台 ffmpeg 二进制)
    3. PyAV (pip 包 av, 自带 FFmpeg 库)
    4. 标准库 wave (无任何依赖, 仅支持 16bit WAV)

编码使用 pilk (silk v3 编解码, 提供各平台预编译 wheel)。

命令行:
    python -m modules.silk_converter.converter input.mp3 [output.silk]
"""

import argparse
import array
import contextlib
import os
import shutil
import subprocess
import tempfile
import wave

import pilk

SUPPORTED_RATES = (8000, 12000, 16000, 24000, 32000, 44100, 48000)
DEFAULT_RATE = 24000  # QQ 语音常用采样率


# ==================== 解码: 任意音频 → 16bit 单声道 PCM ====================


def _find_ffmpeg():
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _decode_ffmpeg(exe, src, rate):
    cmd = [exe, '-v', 'error', '-i', src, '-f', 's16le', '-ar', str(rate), '-ac', '1', '-']
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f'ffmpeg 解码失败: {proc.stderr.decode(errors="replace").strip()}')
    return proc.stdout


def _decode_pyav(src, rate):
    import av

    pcm = bytearray()
    with av.open(src) as container:
        stream = next(s for s in container.streams if s.type == 'audio')
        resampler = av.AudioResampler(format='s16', layout='mono', rate=rate)
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                pcm.extend(bytes(out.planes[0]))
    if not pcm:
        raise RuntimeError('PyAV 解码结果为空')
    return bytes(pcm)


def _decode_wav(src, rate):
    """标准库兜底 (不依赖 audioop, 兼容 Python 3.13+): 仅支持 16bit WAV"""
    with wave.open(src, 'rb') as w:
        channels, width, src_rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        data = w.readframes(w.getnframes())
    if width != 2:
        raise RuntimeError(f'无 ffmpeg 时仅支持 16bit WAV, 当前位宽: {width * 8}bit')
    samples = array.array('h')
    samples.frombytes(data)
    if channels == 2:
        samples = array.array('h', ((samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples) - 1, 2)))
    elif channels != 1:
        raise RuntimeError(f'WAV 声道数不支持: {channels}')
    if src_rate != rate:
        n = int(len(samples) * rate / src_rate)
        samples = array.array('h', (samples[min(int(i * src_rate / rate), len(samples) - 1)] for i in range(n)))
    return samples.tobytes()


def to_pcm(src, rate=DEFAULT_RATE):
    """解码任意音频文件为 16bit 单声道 PCM 字节流"""
    exe = _find_ffmpeg()
    if exe:
        return _decode_ffmpeg(exe, src, rate)
    try:
        return _decode_pyav(src, rate)
    except ImportError:
        pass
    try:
        return _decode_wav(src, rate)
    except wave.Error:
        raise RuntimeError(
            '无法解码该音频: 未找到 ffmpeg / imageio-ffmpeg / PyAV, 标准库仅支持 WAV。'
            '请安装任一解码依赖: pip install imageio-ffmpeg 或 pip install av'
        ) from None


# ==================== 编码: PCM → silk v3 ====================


def pcm_to_silk(pcm, out_path, rate=DEFAULT_RATE):
    """16bit 单声道 PCM 字节流编码为 silk v3 文件, 返回时长(秒)"""
    if rate not in SUPPORTED_RATES:
        raise ValueError(f'采样率 {rate} 不受支持, 可选: {SUPPORTED_RATES}')
    fd, pcm_path = tempfile.mkstemp(suffix='.pcm')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(pcm)
        pilk.encode(pcm_path, out_path, pcm_rate=rate, tencent=True)
    finally:
        with contextlib.suppress(OSError):
            os.remove(pcm_path)
    return pilk.get_duration(out_path) / 1000


def audio_to_silk(src, out_path=None, rate=DEFAULT_RATE):
    """音频文件转 silk v3, 返回 (silk 文件路径, 时长秒)"""
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    if out_path is None:
        out_path = os.path.splitext(src)[0] + '.silk'
    pcm = to_pcm(src, rate)
    duration = pcm_to_silk(pcm, out_path, rate)
    return out_path, duration


def silk_to_wav(src, out_path=None):
    """silk v3 转 WAV (反向转换)"""
    if out_path is None:
        out_path = os.path.splitext(src)[0] + '.wav'
    pilk.silk_to_wav(src, out_path)
    return out_path, pilk.get_duration(src) / 1000


# ==================== CLI ====================


def main():
    parser = argparse.ArgumentParser(description='音频文件转 silk v3 (QQ 语音格式)')
    parser.add_argument('input', help='输入音频文件 (mp3/wav/m4a/flac/ogg 等)')
    parser.add_argument('output', nargs='?', default=None, help='输出 silk 文件 (默认同名 .silk)')
    parser.add_argument('-r', '--rate', type=int, default=DEFAULT_RATE, choices=SUPPORTED_RATES, help='采样率')
    parser.add_argument('-d', '--decode', action='store_true', help='反向: silk 转 wav')
    args = parser.parse_args()
    if args.decode:
        out, duration = silk_to_wav(args.input, args.output)
    else:
        out, duration = audio_to_silk(args.input, args.output, args.rate)
    print(f'{out} ({duration:.1f}s)')


if __name__ == '__main__':
    main()
