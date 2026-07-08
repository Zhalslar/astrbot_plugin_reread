from __future__ import annotations

import random
from dataclasses import dataclass

from astrbot.api import logger
from astrbot.core.message.components import BaseMessageComponent, Face, Image, Plain

from .config import PluginConfig
from .state import GroupState


@dataclass(slots=True)
class ActionPlan:
    repeat_count: int
    action: str
    output_segment: BaseMessageComponent | None = None


class RereadEngine:
    ACTIONS = ("follow", "interrupt", "ban")

    def __init__(self, cfg: PluginConfig):
        self.cfg = cfg
        pool = []
        for action in self.ACTIONS:
            weight = cfg.weight_of(action)
            if weight > 0:
                pool.append((action, weight))

        self._actions, self._weights = zip(*pool) if pool else ((), ())
        if not self._actions:
            logger.warning(
                "[reread] all action weights are 0, reread actions are disabled"
            )

    @staticmethod
    def make_fingerprint(seg: BaseMessageComponent) -> str:
        if isinstance(seg, Plain):
            return f"text:{seg.text}"

        if isinstance(seg, Image):
            key = seg.file or seg.url or seg.path
            return f"image:{key}"

        if isinstance(seg, Face):
            return f"face:{seg.id}"

        return f"unknown:{seg.type}"

    def evaluate(
        self,
        state: GroupState,
        seg_type: str,
        send_id: str,
        seg: BaseMessageComponent,
    ) -> ActionPlan | None:
        state.clear_if_same_sender(seg_type, send_id, self.cfg.need_different)

        fingerprint = self.make_fingerprint(seg)
        state.push_message(seg_type, send_id, fingerprint)

        reread_threshold = self.cfg.get_threshold(seg_type)
        reread_fingerprint = state.get_uniform_tail_fingerprint(
            seg_type, reread_threshold
        )
        if not reread_fingerprint or state.is_same_as_last_action(reread_fingerprint):
            return None

        if not self.cfg.should_reread():
            return None

        if not self._actions:
            return None

        state.mark_handled(reread_fingerprint)
        action = random.choices(self._actions, self._weights, k=1)[0]
        if action == "ban":
            return ActionPlan(repeat_count=reread_threshold, action=action)

        output_segment = (
            Plain(self.cfg.interrupt.text) if action == "interrupt" else seg
        )
        return ActionPlan(
            repeat_count=reread_threshold,
            action=action,
            output_segment=output_segment,
        )
