import asyncio
import random
from collections import deque
from collections.abc import Sequence
from typing import TypedDict

from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import BaseMessageComponent, Face, Image, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType

# ============================================================
# 类型定义
# ============================================================


class MsgRecord(TypedDict):
    """
    单条复读窗口记录（仅单段消息）
    """

    send_id: str
    seg: BaseMessageComponent


# ============================================================
# GroupState —— 单群状态（单段消息 + 幂等保护）
# ============================================================


class GroupState:
    """
    单群状态容器

    仅负责「状态」本身，不包含任何业务规则：
    - 按消息类型分组的消息窗口（deque + maxlen）
    - 最近一次成功复读的消息指纹（用于幂等保护）
    """

    def __init__(self, thresholds: dict[str, int]):
        # 群级并发保护
        self.lock = asyncio.Lock()

        # {seg_type: deque[MsgRecord]}
        # deque 的 maxlen 由 thresholds 决定
        self.messages: dict[str, deque[MsgRecord]] = {
            seg_type: deque(maxlen=limit) for seg_type, limit in thresholds.items()
        }

        # 最近一次成功复读的内容指纹
        self.last_repeated_fingerprint: str | None = None

    # ───────── 消息窗口操作 ─────────

    def clear_if_same_sender(
        self,
        seg_type: str,
        send_id: str,
        require_different_people: bool,
    ) -> None:
        """
        若要求必须不同人复读：
        - 当前消息发送者与窗口中最后一条相同 → 清空窗口
        """
        if not require_different_people:
            return

        lst = self.messages[seg_type]
        if lst and lst[-1]["send_id"] == send_id:
            lst.clear()

    def push_message(
        self,
        seg_type: str,
        send_id: str,
        seg: BaseMessageComponent,
    ) -> None:
        """
        将单段消息压入对应类型的窗口
        """
        self.messages[seg_type].append(
            {
                "send_id": send_id,
                "seg": seg,
            }
        )

    def get_messages(self, seg_type: str) -> deque[MsgRecord]:
        """
        获取指定消息类型的窗口
        """
        return self.messages[seg_type]

    def clear_all(self) -> None:
        """
        清空当前群内所有消息窗口
        （通常在一次成功复读后调用）
        """
        for lst in self.messages.values():
            lst.clear()

    # ───────── 幂等保护 ─────────

    def is_same_as_last_repeat(self, fingerprint: str) -> bool:
        """
        判断当前候选复读内容
        是否与上一次成功复读的内容完全一致
        """
        return self.last_repeated_fingerprint == fingerprint

    def mark_repeated(self, fingerprint: str) -> None:
        """
        标记一次成功复读：
        - 记录指纹
        - 清空所有窗口，避免立刻二次触发
        """
        self.last_repeated_fingerprint = fingerprint
        self.clear_all()


# ============================================================
# RereadPlugin —— 规则 + 副作用
# ============================================================


class RereadPlugin(Star):
    """
    复读插件主体

    职责：
    - 消息过滤
    - 复读判定
    - 副作用（发送消息、打断、stop_event）
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        self.thresholds: dict[str, int] = config["thresholds"]
        self.supported_type = list(self.thresholds.keys())

        # {group_id: GroupState}
        self.group_states: dict[str, GroupState] = {}

    # ───────── State 管理 ─────────

    def get_group_state(self, group_id: str) -> GroupState:
        """
        获取或初始化指定群的状态对象
        """
        if group_id not in self.group_states:
            self.group_states[group_id] = GroupState(self.thresholds)
        return self.group_states[group_id]

    # ───────── 主处理逻辑 ─────────

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def reread_handle(self, event: AstrMessageEvent):
        """
        群消息复读处理入口
        """
        # 忽略唤醒 / at bot 的消息
        if event.is_at_or_wake_command:
            return

        chain = event.get_messages()

        # 仅处理单段消息
        if len(chain) != 1:
            return

        seg = chain[0]
        seg_type = str(seg.type).split(".")[-1]

        # 仅处理配置中声明支持的消息类型
        if seg_type not in self.supported_type:
            return

        group_id = event.get_group_id()

        # 群白名单过滤
        whitelist = self.conf["reread_group_whitelist"]
        if whitelist and group_id not in whitelist:
            return

        state = self.get_group_state(group_id)
        send_id = event.get_sender_id()

        async with state.lock:
            # 同一用户连续发言 → 清空窗口
            state.clear_if_same_sender(
                seg_type,
                send_id,
                self.conf["require_different_people"],
            )

            # 记录当前消息
            state.push_message(seg_type, send_id, seg)
            msg_list = state.get_messages(seg_type)

            # 是否满足复读阈值与一致性条件
            if not self._can_repeat(seg_type, msg_list):
                return

            # 计算当前复读候选内容的指纹
            fingerprint = self._make_fingerprint(seg_type, msg_list[0]["seg"])

            # 与上一次成功复读内容相同 → 跳过（幂等保护）
            if state.is_same_as_last_repeat(fingerprint):
                return

            # 概率判定
            if random.random() >= self.conf["repeat_probability"]:
                return

            # 打断机制
            out_seg = seg
            if random.random() < self.conf["interrupt_probability"]:
                out_seg = Plain("打断！")

            # 执行复读
            await event.send(MessageChain(chain=[out_seg]))  # type: ignore
            yield event.chain_result([out_seg])

            # 标记复读成功
            state.mark_repeated(fingerprint)
            event.stop_event()

    # ───────── 判定逻辑 ─────────

    def _can_repeat(
        self,
        seg_type: str,
        msg_list: Sequence[MsgRecord],
    ) -> bool:
        """
        判断当前窗口是否满足复读条件：
        - 数量达到阈值
        - 所有消息的指纹完全一致
        """
        threshold = self.thresholds.get(seg_type, 3)
        if len(msg_list) < threshold:
            return False

        base_fp = self._make_fingerprint(seg_type, msg_list[0]["seg"])

        for msg in msg_list:
            if self._make_fingerprint(seg_type, msg["seg"]) != base_fp:
                return False

        return True

    def _make_fingerprint(
        self,
        seg_type: str,
        seg: BaseMessageComponent,
    ) -> str:
        """
        单段消息的唯一判等 / 幂等指纹

        该指纹：
        - 决定是否可以复读
        - 决定是否与上一次复读内容相同
        """
        if isinstance(seg, Plain):
            return f"text:{seg.text}"

        if isinstance(seg, Image):
            key = seg.file or seg.url or seg.path
            return f"image:{key}"

        if isinstance(seg, Face):
            return f"face:{seg.id}"

        return f"unknown:{seg_type}"
