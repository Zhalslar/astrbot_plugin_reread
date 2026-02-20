import random

from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import (
    BaseMessageComponent,
    Face,
    Image,
    Plain,
)
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType

from .core.config import PluginConfig
from .core.state import StateManager


class RereadPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.state_mgr = StateManager(self.cfg.thresholds)

    # ───────── 指纹生成 ─────────

    @staticmethod
    def make_fingerprint(seg: BaseMessageComponent) -> str:
        """
        为单段消息生成稳定的逻辑指纹
        """
        if isinstance(seg, Plain):
            return f"text:{seg.text}"

        if isinstance(seg, Image):
            key = seg.file or seg.url or seg.path
            return f"image:{key}"

        if isinstance(seg, Face):
            return f"face:{seg.id}"

        return f"unknown:{seg.type}"

    # ───────── 主处理逻辑 ─────────

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def reread_handle(self, event: AstrMessageEvent):
        # at / 唤醒指令不处理
        if event.is_at_or_wake_command:
            return

        chain = event.get_messages()
        if len(chain) != 1:
            return

        seg = chain[0]
        seg_type = str(seg.type).split(".")[-1]

        if not self.cfg.is_supported_type(seg_type):
            return

        group_id = event.get_group_id()
        send_id = event.get_sender_id()

        if self.cfg.group_whitelist and not self.cfg.is_white_group(group_id):
            return

        state = self.state_mgr.get_state(group_id)

        # ========== 进入临界区 ==========
        async with state.lock:
            # 同人清窗
            state.clear_if_same_sender(
                seg_type,
                send_id,
                self.cfg.need_different,
            )

            # 生成指纹（只算一次）
            fp = self.make_fingerprint(seg)

            # 推进窗口（只存判定信息）
            state.push_message(seg_type, send_id, fp)
            msg_list = state.get_messages(seg_type)

            threshold = self.cfg.get_threshold(seg_type)
            if len(msg_list) < threshold:
                return

            # ───── 复读一致性判定 ─────
            first_fp = msg_list[0]["fp"]
            if any(m["fp"] != first_fp for m in msg_list):
                return

            # 幂等保护
            if state.is_same_as_last_repeat(first_fp):
                return

            # 概率判定
            if random.random() >= self.cfg.reread_prob:
                return

            # ───── commit 点（不可回滚） ─────
            state.mark_repeated(first_fp)

            # ───── 输出准备（直接使用当下 seg） ─────
            out_seg = (
                Plain("打断！") if random.random() < self.cfg.interrupt_prob else seg
            )

        # ========== 出锁，执行 IO ==========
        await event.send(event.chain_result([out_seg]))
        event.stop_event()
