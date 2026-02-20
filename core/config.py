# config.py
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, get_type_hints

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.context import Context


class ConfigNode:
    """配置节点：dict → 强类型属性访问（极简版）"""

    _SCHEMA_CACHE: dict[type, dict[str, type]] = {}

    @classmethod
    def _schema(cls) -> dict[str, type]:
        return cls._SCHEMA_CACHE.setdefault(cls, get_type_hints(cls))

    def __init__(self, data: MutableMapping[str, Any]):
        object.__setattr__(self, "_data", data)
        for key in self._schema():
            if key in data:
                continue
            if hasattr(self.__class__, key):
                continue
            logger.warning(f"[config:{self.__class__.__name__}] 缺少字段: {key}")

    def __getattr__(self, key: str) -> Any:
        if key in self._schema():
            return self._data.get(key)
        raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in self._schema():
            self._data[key] = value
            return
        object.__setattr__(self, key, value)


# ============ 插件自定义配置 ==================


class PluginConfig(ConfigNode):
    group_whitelist: list[str]
    need_different: bool
    thresholds: dict[str, int]
    reread_prob: float
    interrupt_prob: float

    def __init__(self, cfg: AstrBotConfig, context: Context):
        super().__init__(cfg)
        self.context = context
        self.supported_type = list(self.thresholds.keys())

    def get_threshold(self, seg_type: str) -> int:
        return self.thresholds.get(seg_type, 0)

    def is_supported_type(self, seg_type: str) -> bool:
        return seg_type in self.supported_type

    def is_white_group(self, group_id: str) -> bool:
        return group_id in self.group_whitelist
