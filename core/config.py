# config.py
from __future__ import annotations

import random
from collections.abc import MutableMapping
from typing import Any, get_type_hints

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig


class ConfigNode:
    _SCHEMA_CACHE: dict[type, dict[str, type]] = {}

    @classmethod
    def _schema(cls) -> dict[str, type]:
        return cls._SCHEMA_CACHE.setdefault(
            cls,
            {
                key: tp
                for key, tp in get_type_hints(cls).items()
                if not key.startswith("_")
            },
        )

    def __init__(self, data: MutableMapping[str, Any]):
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_children", {})
        for key in self._schema():
            if key in data:
                continue
            if hasattr(self.__class__, key):
                continue
            logger.warning(f"[config:{self.__class__.__name__}] miss key: {key}")

    def __getattr__(self, key: str) -> Any:
        if key in self._schema():
            value = self._data.get(key, getattr(self.__class__, key, None))
            tp = self._schema()[key]

            if isinstance(tp, type) and issubclass(tp, ConfigNode):
                children: dict[str, ConfigNode] = self.__dict__["_children"]
                if key not in children:
                    if not isinstance(value, MutableMapping):
                        value = {}
                        self._data[key] = value
                    children[key] = tp(value)
                return children[key]

            return value
        raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in self._schema():
            self._data[key] = value
            return
        object.__setattr__(self, key, value)


class FollowConfig(ConfigNode):
    weight: int


class InterruptConfig(ConfigNode):
    weight: int
    text: str


class BanConfig(ConfigNode):
    weight: int
    duration: int
    prompt: str


class PluginConfig(ConfigNode):
    group_whitelist: list[str]
    need_different: bool
    thresholds: dict[str, int]
    reread_prob: float
    follow: FollowConfig
    interrupt: InterruptConfig
    ban: BanConfig

    def __init__(self, cfg: AstrBotConfig):
        super().__init__(cfg)
        self.supported_type = list(self.thresholds.keys())
        self.window_sizes = {
            seg_type: self.get_threshold(seg_type) for seg_type in self.supported_type
        }

    def get_threshold(self, seg_type: str) -> int:
        return self.thresholds.get(seg_type, 0)

    def get_window_size(self, seg_type: str) -> int:
        return self.window_sizes.get(seg_type, 0)

    def should_reread(self) -> bool:
        return self.reread_prob > 0 and random.random() < self.reread_prob

    def weight_of(self, action: str) -> int:
        return {
            "follow": self.follow.weight,
            "interrupt": self.interrupt.weight,
            "ban": self.ban.weight if self.ban.duration > 0 else 0,
        }[action]

    def is_supported_type(self, seg_type: str) -> bool:
        return seg_type in self.supported_type

    def is_white_group(self, group_id: str) -> bool:
        return group_id in self.group_whitelist
