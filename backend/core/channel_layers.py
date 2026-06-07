from channels_redis.core import RedisChannelLayer as BaseRedisChannelLayer


class RedisChannelLayer(BaseRedisChannelLayer):
    """Redis channel layer with configurable blocking pop timeout."""

    def __init__(self, *args, brpop_timeout=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.brpop_timeout = brpop_timeout
