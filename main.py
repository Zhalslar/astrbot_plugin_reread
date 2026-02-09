import random

from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import BaseMessageComponent, Face, Image, Plain
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType

from .core.state import  StateManager
from .core.config import PluginConfig


class RereadPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.state_mgr = StateManager(self.cfg)

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

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def reread_handle(self, event: AstrMessageEvent):
        if event.is_at_or_wake_command:
            return

        chain = event.get_messages()
        if len(chain) != 1:
            return

        seg = chain[0]
        seg_type = str(seg.type).split(".")[-1]
        group_id = event.get_group_id()
        send_id = event.get_sender_id()

        if not self.cfg.is_supported_type(seg_type):
            return

        if self.cfg.group_whitelist and not self.cfg.is_white_group(group_id):
            return

        state = self.state_mgr.get_state(group_id)

        # ========== 临界区 ==========
        async with state.lock:
            # 同人清窗
            state.clear_if_same_sender(
                seg_type,
                send_id,
                self.cfg.need_different,
            )

            # 推进窗口
            state.push_message(seg_type, send_id, seg)
            msg_list = state.get_messages(seg_type)

            # ───── 判定阶段 ─────

            threshold = self.cfg.get_threshold(seg_type)
            if len(msg_list) < threshold:
                return

            last_seg = msg_list[-1]["seg"]
            fp = self.make_fingerprint(last_seg)

            for msg in msg_list:
                if self.make_fingerprint(msg["seg"]) != fp:
                    return

            if state.is_same_as_last_repeat(fp):
                return

            if random.random() >= self.cfg.reread_prob:
                return

            # ───── commit 点（不可回滚） ─────
            state.mark_repeated(fp)

            # ───── 执行数据准备 ─────
            repeat_seg = last_seg
            out_seg = (
                Plain("打断！")
                if random.random() < self.cfg.interrupt_prob
                else repeat_seg
            )

        # ========== 出锁，执行 IO ==========
        await event.send(event.chain_result([out_seg]))
        event.stop_event()
