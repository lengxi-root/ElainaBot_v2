#!/usr/bin/env python
"""媒体上传 / 图片尺寸检测"""

import asyncio
import base64
import contextlib
import hashlib
import os
import struct
import tempfile

from core.base.logger import FRAMEWORK, get_logger

log = get_logger(FRAMEWORK, '媒体上传')

# 分片上传阈值
CHUNK_THRESHOLD = 5 * 1024 * 1024  # 5MB


# ==================== 上传 ====================


async def upload_media_bytes(sender, file_bytes, file_type, endpoint, *, file_name=None, event=None):
    """上传媒体 bytes, 返回 file_info (>5MB 自动分片)"""
    if not file_bytes:
        return None
    if not isinstance(file_bytes, bytes | str):
        return None
    # 大文件走分片 (带重试)
    if isinstance(file_bytes, bytes) and len(file_bytes) > CHUNK_THRESHOLD:
        last_err = None
        for retry in range(3):
            try:
                result = await _chunked_upload_from_bytes(sender, file_bytes, file_type, endpoint, file_name=file_name)
                if result:
                    return result
            except Exception as e:
                last_err = e
                log.warning(f'[{sender._appid}] 分片上传第{retry + 1}次失败: {e}')
                if retry < 2:
                    await asyncio.sleep(2 * (retry + 1))
        log.warning(f'[{sender._appid}] 分片上传3次均失败, 最后错误: {last_err}')
        return None

    req_data = {
        'srv_send_msg': False,
        'file_type': file_type,
    }
    if isinstance(file_bytes, bytes):
        req_data['file_data'] = await asyncio.get_running_loop().run_in_executor(
            None, lambda: base64.b64encode(file_bytes).decode()
        )
    elif isinstance(file_bytes, str):
        req_data['url'] = file_bytes  # 兼容使用url来发送
    if file_name:
        req_data['file_name'] = file_name
    # 最多 2 次 (QQ API 偶发返回空 body)
    last_resp = None
    for attempt in range(2):
        success, resp = await sender.post_json(endpoint, req_data)
        last_resp = resp
        if not success:
            if event:
                event.error = resp
            else:
                log.warning(f'[{sender._appid}] 上传API失败: {resp} (endpoint={endpoint})')
            return None
        file_info = resp.get('file_info')
        if file_info:
            return file_info
        if attempt == 0:
            log.debug(f'[{sender._appid}] 上传返回无 file_info, 重试 (resp={resp})')
            await asyncio.sleep(0.15)
    if event:
        event.error = last_resp
    else:
        log.warning(f'[{sender._appid}] 上传失败: 无 file_info (endpoint={endpoint}, resp={last_resp})')
    return None


def _resolve_upload_ep(group_id=None, user_id=None, event=None):
    """解析媒体上传端点"""
    if group_id:
        return f'/v2/groups/{group_id}/files'
    if user_id:
        return f'/v2/users/{user_id}/files'
    return event.media_upload_endpoint if event else ''


async def upload_media_via_url(
    sender,
    event,
    url,
    file_type,
    *,
    file_name=None,
    target_user_id=None,
    target_group_id=None,
):
    """通过 URL 上传媒体, 返回 file_info"""
    endpoint = _resolve_upload_ep(target_group_id, target_user_id, event)
    if not endpoint:
        return None
    req_data = {'srv_send_msg': False, 'file_type': file_type, 'url': url}
    if file_name:
        req_data['file_name'] = file_name
    success, resp = await sender.post_json(endpoint, req_data)
    if success:
        return resp.get('file_info')
    if event:
        event.error = resp
    return None


# ==================== 分片上传 ====================


async def _chunked_upload_from_bytes(sender, file_bytes, file_type, endpoint, *, file_name=None):
    """内存数据分片上传 (写临时文件)"""
    suffix = os.path.splitext(file_name)[1] if file_name else ''

    def _write_tmp():
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(file_bytes)
            return f.name

    def _remove_tmp(path):
        with contextlib.suppress(OSError):
            os.remove(path)

    tmp_path = None
    try:
        tmp_path = await asyncio.to_thread(_write_tmp)
        return await chunked_upload(
            sender,
            tmp_path,
            file_type,
            endpoint,
            file_name=file_name or os.path.basename(tmp_path),
        )
    finally:
        if tmp_path:
            await asyncio.to_thread(_remove_tmp, tmp_path)


async def chunked_upload(sender, file_path, file_type, endpoint, *, file_name=None):
    """分片上传本地文件, 返回 file_info"""
    file_size = os.path.getsize(file_path)
    fname = file_name or os.path.basename(file_path)
    hashes = await asyncio.get_running_loop().run_in_executor(None, compute_file_hashes, file_path, file_size)

    # 提取 scope 路径: /v2/groups/{id}/files -> /v2/groups/{id}
    scope = endpoint.rsplit('/files', 1)[0]

    # 1. 申请上传 (带重试)
    prep_data = {
        'file_type': file_type,
        'file_name': fname,
        'file_size': file_size,
        **hashes,
    }
    prep = None
    for prep_retry in range(3):
        success, prep = await sender.post_json(f'{scope}/upload_prepare', prep_data)
        if success:
            break
        log.warning(f'[{sender._appid}] upload_prepare 第{prep_retry + 1}次失败: {prep}')
        if prep_retry < 2:
            await asyncio.sleep(1.5 * (prep_retry + 1))
    if not success:
        raise Exception(f'upload_prepare failed: {prep}')

    upload_id = prep['upload_id']
    block_size = int(prep['block_size'])
    parts = prep['parts']

    # 2. 逐片上传
    for part in parts:
        idx = part['index']
        offset = (idx - 1) * block_size
        chunk_size = min(block_size, file_size - offset)
        chunk = await asyncio.get_running_loop().run_in_executor(None, _read_chunk, file_path, offset, chunk_size)

        for retry in range(3):
            try:
                resp = await sender._client.put(
                    part['presigned_url'],
                    content=chunk,
                    headers={'Content-Length': str(len(chunk))},
                    timeout=300.0,
                )
                if resp.status_code >= 400:
                    raise Exception(f'PUT {resp.status_code}')
                break
            except Exception:
                if retry >= 2:
                    raise
                await asyncio.sleep(1 * (2**retry))

        await sender.post_json(
            f'{scope}/upload_part_finish',
            {
                'upload_id': upload_id,
                'part_index': idx,
                'block_size': len(chunk),
                'md5': hashlib.md5(chunk).hexdigest(),
            },
        )

    # 3. 完成上传
    success, result = await sender.post_json(f'{scope}/files', {'upload_id': upload_id})
    if success:
        return result.get('file_info')
    return None


# ==================== 文件 I/O (同步, executor 中运行) ====================


def _read_chunk(file_path, offset, size):
    with open(file_path, 'rb') as f:
        f.seek(offset)
        return f.read(size)


# ==================== 文件哈希 (同步, executor 中运行) ====================


def compute_file_hashes(file_path, file_size):
    """计算文件 MD5/SHA1/MD5-10M"""
    md5_h = hashlib.md5()
    sha1_h = hashlib.sha1()
    md5_10m_h = hashlib.md5()
    _10m = 10_002_432
    need_10m = file_size > _10m
    bytes_read = 0
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            md5_h.update(chunk)
            sha1_h.update(chunk)
            if need_10m:
                remaining = _10m - bytes_read
                if remaining > 0:
                    md5_10m_h.update(chunk[:remaining] if remaining < len(chunk) else chunk)
            bytes_read += len(chunk)
    md5 = md5_h.hexdigest()
    return {
        'md5': md5,
        'sha1': sha1_h.hexdigest(),
        'md5_10m': md5_10m_h.hexdigest() if need_10m else md5,
    }


# ==================== 图片尺寸 ====================


def _jpeg_size(data):
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack('>HH', data[i + 5 : i + 9])
            return w, h
        i += 2 + struct.unpack('>H', data[i + 2 : i + 4])[0]
    return None


def _webp_size(data):
    fmt = data[12:16]
    if fmt == b'VP8X':
        return int.from_bytes(data[24:27], 'little') + 1, int.from_bytes(data[27:30], 'little') + 1
    if fmt == b'VP8 ':
        w, h = struct.unpack('<HH', data[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if fmt == b'VP8L':
        bits = int.from_bytes(data[21:25], 'little')
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def _parse_image_size(data):
    """解析图片头获取宽高 (PNG/JPEG/GIF/WEBP)"""
    size = None
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        size = struct.unpack('>II', data[16:24])
    elif data[:6] in (b'GIF87a', b'GIF89a'):
        size = struct.unpack('<HH', data[6:10])
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        size = _webp_size(data)
    elif data[:2] == b'\xff\xd8':
        size = _jpeg_size(data)
    if not size:
        return None
    w, h = size
    return {'width': w, 'height': h, 'px': f'#{w}px #{h}px'}


async def get_image_size(client, image_input):
    """获取图片尺寸 (支持 bytes/URL/路径, 解析文件头)"""
    try:
        if isinstance(image_input, str):
            if image_input.startswith(('http://', 'https://')):
                resp = await client.get(image_input, headers={'Range': 'bytes=0-65535'})
                image_input = resp.content
            else:
                # 本地文件 → 线程池读取头部
                image_input = await asyncio.to_thread(_read_chunk, image_input, 0, 65536)
        if isinstance(image_input, bytes):
            return _parse_image_size(image_input)
    except Exception as e:
        log.debug(f'获取图片尺寸失败: {e}')
    return None
