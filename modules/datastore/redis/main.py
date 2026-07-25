#!/usr/bin/env python
"""Redis 异步客户端组件

基于 redis.asyncio (redis-py 5.x), 完整迁移 function/redis_pool.py 所有能力。
由 datastore 主模块统一管理生命周期, 不单独作为模块使用。

完整操作: 基础 Key / Hash / List / Set / Sorted Set / Pipeline / 管理命令
"""

import asyncio
import contextlib
import time

_DEFAULTS = {
    'host': '127.0.0.1',
    'port': 6379,
    'password': '',
    'db': 0,
    'max_connections': 200,
    'pool_timeout': 30,
    'socket_timeout': 5,
    'socket_connect_timeout': 5,
    'health_check_interval': 30,
    'decode_responses': True,
}

_COMMENTS = {
    'host': 'Redis 服务器地址',
    'port': 'Redis 端口号',
    'password': '连接密码, 无密码留空',
    'db': '数据库编号 (0-15)',
    'max_connections': '最大连接数 (过小会在并发高峰耗尽连接池)',
    'pool_timeout': '连接池耗尽时等待空闲连接的超时 (秒)',
    'socket_timeout': '读写超时 (秒)',
    'socket_connect_timeout': '连接超时 (秒)',
    'health_check_interval': '健康检查间隔 (秒)',
    'decode_responses': '是否自动解码响应为字符串',
}


class _SafePipeline:
    """Pipeline 代理: execute 失败时记录日志并按命令数返回 None 占位, 不向调用方抛异常"""

    __slots__ = ('_pipe', '_log', '_owner')

    def __init__(self, pipe, log, owner=None):
        self._pipe = pipe
        self._log = log
        self._owner = owner

    def __getattr__(self, name):
        return getattr(self._pipe, name)

    async def __aenter__(self):
        await self._pipe.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._pipe.__aexit__(exc_type, exc_val, exc_tb)

    async def execute(self, raise_on_error=True):
        n = len(self._pipe.command_stack)
        try:
            result = await self._pipe.execute(raise_on_error=raise_on_error)
            if self._owner is not None:
                self._owner._mark_ok()
            return result
        except Exception as e:
            self._log.warning(f'PIPELINE 执行失败 ({n}条命令): {e}')
            with contextlib.suppress(Exception):
                await self._pipe.reset()
            if self._owner is not None and _is_pool_exhausted(e):
                await self._owner._on_pool_exhausted()
            return [None] * n


def _is_pool_exhausted(e):
    return 'No connection available' in str(e)


class RedisPool:
    """Redis 异步客户端封装 — 完整能力"""

    # 连接池持续耗尽超过此时长后重建连接池自愈 (秒)
    _EXHAUST_GRACE = 60

    __slots__ = ('_cfg', '_client', '_available', '_log',
                 '_exhausted_since', '_reinit_lock')

    def __init__(self, cfg, log):
        self._cfg = cfg
        self._client = None
        self._available = False
        self._log = log
        self._exhausted_since = None
        self._reinit_lock = asyncio.Lock()

    async def initialize(self):
        try:
            from redis.asyncio import BlockingConnectionPool, Redis
        except ImportError:
            self._log.error('redis 未安装 (pip install redis>=5.0)')
            return
        try:
            password = self._cfg.get('password') or None
            pool = BlockingConnectionPool(
                host=self._cfg.get('host', '127.0.0.1'),
                port=int(self._cfg.get('port', 6379)),
                password=password,
                db=int(self._cfg.get('db', 0)),
                max_connections=int(self._cfg.get('max_connections', 200)),
                timeout=int(self._cfg.get('pool_timeout', 30)),
                socket_timeout=int(self._cfg.get('socket_timeout', 5)),
                socket_connect_timeout=int(self._cfg.get('socket_connect_timeout', 5)),
                health_check_interval=int(self._cfg.get('health_check_interval', 30)),
                decode_responses=bool(self._cfg.get('decode_responses', True)),
            )
            self._client = Redis(connection_pool=pool)
            await self._client.ping()
            self._available = True
        except Exception as e:
            self._log.error(f'Redis 初始化失败: {e}')
            self._client = None
            self._available = False

    def is_available(self):
        return self._available and self._client is not None

    def get_client(self):
        """获取底层 redis.asyncio.Redis 实例"""
        return self._client if self.is_available() else None

    async def close(self):
        self._available = False
        if self._client:
            client, self._client = self._client, None
            with contextlib.suppress(Exception):
                await client.aclose()

    # ==================== 内部 ====================

    async def _safe(self, op, coro, default=None, key=None):
        if not self.is_available():
            return default
        try:
            result = await coro
            self._mark_ok()
            return result
        except Exception as e:
            self._log.warning(f'{op} 失败 [{key}]: {e}' if key else f'{op} 失败: {e}')
            if _is_pool_exhausted(e):
                await self._on_pool_exhausted()
            return default

    def _mark_ok(self):
        self._exhausted_since = None

    def pool_stats(self):
        """连接池状态 (诊断用)"""
        try:
            pool = self._client.connection_pool
            return (f'in_use={len(pool._in_use_connections)} '
                    f'available={len(pool._available_connections)} '
                    f'max={pool.max_connections}')
        except Exception:
            return 'unknown'

    async def _on_pool_exhausted(self):
        """连接池耗尽处置: 记录池状态; 持续耗尽超过 _EXHAUST_GRACE 秒则重建连接池,
        回收因异常/取消未归还的泄漏连接"""
        now = time.monotonic()
        if self._exhausted_since is None:
            self._exhausted_since = now
            self._log.error(f'Redis 连接池耗尽: {self.pool_stats()}')
            return
        if now - self._exhausted_since < self._EXHAUST_GRACE or self._reinit_lock.locked():
            return
        async with self._reinit_lock:
            if self._exhausted_since is None \
                    or time.monotonic() - self._exhausted_since < self._EXHAUST_GRACE:
                return
            self._log.error(
                f'Redis 连接池持续耗尽超 {self._EXHAUST_GRACE}s, '
                f'重建连接池自愈: {self.pool_stats()}')
            self._exhausted_since = None
            self._available = False
            old, self._client = self._client, None
            if old is not None:
                with contextlib.suppress(Exception):
                    await old.aclose()
            await self.initialize()

    # ==================== 基础操作 ====================

    async def get(self, key, default=None):
        if not self.is_available():
            return default
        v = await self._safe('GET', self._client.get(key), default=default, key=key)
        return v if v is not None else default

    async def set(self, key, value, ex=None, px=None, nx=False, xx=False):
        return bool(
            await self._safe(
                'SET',
                self._client.set(key, value, ex=ex, px=px, nx=nx, xx=xx),
                default=False,
                key=key,
            )
        )

    async def delete(self, *keys):
        if not keys:
            return 0
        return await self._safe('DELETE', self._client.delete(*keys), default=0)

    async def exists(self, *keys):
        if not keys:
            return 0
        return await self._safe('EXISTS', self._client.exists(*keys), default=0)

    async def expire(self, key, seconds):
        return bool(await self._safe('EXPIRE', self._client.expire(key, seconds), default=False, key=key))

    async def expireat(self, key, when):
        """设置过期时间点 (Unix 时间戳)"""
        return bool(await self._safe('EXPIREAT', self._client.expireat(key, when), default=False, key=key))

    async def ttl(self, key):
        return await self._safe('TTL', self._client.ttl(key), default=-2, key=key)

    async def incr(self, key, amount=1):
        return await self._safe('INCR', self._client.incrby(key, amount), default=None, key=key)

    async def decr(self, key, amount=1):
        return await self._safe('DECR', self._client.decrby(key, amount), default=None, key=key)

    async def keys(self, pattern='*'):
        return await self._safe('KEYS', self._client.keys(pattern), default=[])

    async def scan_iter(self, match=None, count=None):
        """扫描键 — 返回异步迭代器"""
        if not self.is_available():
            return
        async for key in self._client.scan_iter(match=match, count=count):
            yield key

    # ==================== Hash ====================

    async def hget(self, name, key, default=None):
        if not self.is_available():
            return default
        v = await self._safe('HGET', self._client.hget(name, key), default=default, key=f'{name}.{key}')
        return v if v is not None else default

    async def hset(self, name, key=None, value=None, mapping=None):
        return await self._safe(
            'HSET',
            self._client.hset(name, key=key, value=value, mapping=mapping),
            default=0,
            key=name,
        )

    async def hdel(self, name, *keys):
        if not keys:
            return 0
        return await self._safe('HDEL', self._client.hdel(name, *keys), default=0, key=name)

    async def hgetall(self, name):
        return await self._safe('HGETALL', self._client.hgetall(name), default={}, key=name)

    async def hexists(self, name, key):
        return bool(
            await self._safe(
                'HEXISTS',
                self._client.hexists(name, key),
                default=False,
                key=f'{name}.{key}',
            )
        )

    async def hincrby(self, name, key, amount=1):
        return await self._safe(
            'HINCRBY',
            self._client.hincrby(name, key, amount),
            default=None,
            key=f'{name}.{key}',
        )

    async def hkeys(self, name):
        return await self._safe('HKEYS', self._client.hkeys(name), default=[], key=name)

    async def hlen(self, name):
        return await self._safe('HLEN', self._client.hlen(name), default=0, key=name)

    # ==================== List ====================

    async def lpush(self, name, *values):
        if not values:
            return 0
        return await self._safe('LPUSH', self._client.lpush(name, *values), default=0, key=name)

    async def rpush(self, name, *values):
        if not values:
            return 0
        return await self._safe('RPUSH', self._client.rpush(name, *values), default=0, key=name)

    async def lpop(self, name, count=None):
        return await self._safe('LPOP', self._client.lpop(name, count), default=None, key=name)

    async def rpop(self, name, count=None):
        return await self._safe('RPOP', self._client.rpop(name, count), default=None, key=name)

    async def lrange(self, name, start, end):
        return await self._safe('LRANGE', self._client.lrange(name, start, end), default=[], key=name)

    async def llen(self, name):
        return await self._safe('LLEN', self._client.llen(name), default=0, key=name)

    # ==================== Set ====================

    async def sadd(self, name, *values):
        if not values:
            return 0
        return await self._safe('SADD', self._client.sadd(name, *values), default=0, key=name)

    async def srem(self, name, *values):
        if not values:
            return 0
        return await self._safe('SREM', self._client.srem(name, *values), default=0, key=name)

    async def smembers(self, name):
        return await self._safe('SMEMBERS', self._client.smembers(name), default=set(), key=name)

    async def sismember(self, name, value):
        return bool(
            await self._safe(
                'SISMEMBER',
                self._client.sismember(name, value),
                default=False,
                key=name,
            )
        )

    async def scard(self, name):
        return await self._safe('SCARD', self._client.scard(name), default=0, key=name)

    # ==================== Sorted Set ====================

    async def zadd(self, name, mapping, nx=False, xx=False):
        return await self._safe('ZADD', self._client.zadd(name, mapping, nx=nx, xx=xx), default=0, key=name)

    async def zrem(self, name, *values):
        if not values:
            return 0
        return await self._safe('ZREM', self._client.zrem(name, *values), default=0, key=name)

    async def zrange(self, name, start, end, withscores=False):
        return await self._safe(
            'ZRANGE',
            self._client.zrange(name, start, end, withscores=withscores),
            default=[],
            key=name,
        )

    async def zrevrange(self, name, start, end, withscores=False):
        return await self._safe(
            'ZREVRANGE',
            self._client.zrevrange(name, start, end, withscores=withscores),
            default=[],
            key=name,
        )

    async def zscore(self, name, value):
        return await self._safe('ZSCORE', self._client.zscore(name, value), default=None, key=name)

    async def zincrby(self, name, amount, value):
        return await self._safe('ZINCRBY', self._client.zincrby(name, amount, value), default=None, key=name)

    async def zcard(self, name):
        return await self._safe('ZCARD', self._client.zcard(name), default=0, key=name)

    # ==================== Pipeline / 管理 ====================

    def pipeline(self, transaction=True):
        """获取管道对象 (async with pool.pipeline() as pipe), execute 失败返回 None 占位列表"""
        if not self.is_available():
            return None
        return _SafePipeline(self._client.pipeline(transaction=transaction), self._log, owner=self)

    async def flushdb(self, asynchronous=False):
        """清空当前数据库"""
        return bool(
            await self._safe(
                'FLUSHDB',
                self._client.flushdb(asynchronous=asynchronous),
                default=False,
            )
        )

    async def info(self, section=None):
        """获取服务器信息"""
        if section:
            return await self._safe('INFO', self._client.info(section), default={})
        return await self._safe('INFO', self._client.info(), default={})

    async def dbsize(self):
        """获取键数量"""
        return await self._safe('DBSIZE', self._client.dbsize(), default=0)

    async def ping(self):
        """连通性测试"""
        return bool(await self._safe('PING', self._client.ping(), default=False))
