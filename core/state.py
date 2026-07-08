import asyncio
from collections import deque
from typing import TypedDict


class MsgRecord(TypedDict):
    """
    单条复读窗口记录（仅用于判定）
    """

    send_id: str
    fp: str


class GroupState:
    """
    单群状态容器
    - 按消息类型分组的消息窗口（deque + maxlen）
    - 最近一次成功复读的消息指纹（用于幂等保护）
    """

    def __init__(self, window_sizes: dict[str, int]):
        # 群级并发保护
        self.lock = asyncio.Lock()

        # {seg_type: deque[MsgRecord]}
        self.messages: dict[str, deque[MsgRecord]] = {
            seg_type: deque(maxlen=limit) for seg_type, limit in window_sizes.items()
        }

        # Fingerprint handled by the latest successful action.
        self.last_handled_fingerprint: str | None = None

    # ───────── 窗口维护 ─────────

    def clear_if_same_sender(
        self,
        seg_type: str,
        send_id: str,
        need_different: bool,
    ) -> None:
        """
        若要求必须不同人复读：
        - 当前消息发送者与窗口中最后一条相同 → 清空窗口
        """
        if not need_different:
            return

        lst = self.messages[seg_type]
        if lst and lst[-1]["send_id"] == send_id:
            lst.clear()

    def push_message(
        self,
        seg_type: str,
        send_id: str,
        fp: str,
    ) -> None:
        """
        将单段消息指纹压入对应类型的窗口
        """
        self.messages[seg_type].append(
            {
                "send_id": send_id,
                "fp": fp,
            }
        )

    def get_messages(self, seg_type: str) -> deque[MsgRecord]:
        """
        获取指定消息类型的窗口
        """
        return self.messages[seg_type]

    def get_uniform_tail_fingerprint(self, seg_type: str, count: int) -> str | None:
        if count <= 0:
            return None

        messages = self.messages[seg_type]
        if len(messages) < count:
            return None

        tail = list(messages)[-count:]
        first_fp = tail[0]["fp"]
        if any(msg["fp"] != first_fp for msg in tail):
            return None
        return first_fp

    def clear_all(self) -> None:
        """
        清空当前群内所有消息窗口
        （通常在一次成功复读后调用）
        """
        for lst in self.messages.values():
            lst.clear()

    # ───────── 幂等保护 ─────────

    def is_same_as_last_action(self, fingerprint: str) -> bool:
        """Check whether the candidate fingerprint matches the last handled one."""
        return self.last_handled_fingerprint == fingerprint

    def mark_handled(self, fingerprint: str) -> None:
        """Record a successful action and clear windows to avoid immediate retrigger."""
        self.last_handled_fingerprint = fingerprint
        self.clear_all()


class StateManager:
    """
    全局状态管理器（按群）
    """

    _group_states: dict[str, GroupState] = {}

    def __init__(self, window_sizes: dict[str, int]):
        self.window_sizes = window_sizes

    def get_state(self, gid: str) -> GroupState:
        """
        获取或初始化指定群的状态对象
        """
        if gid not in self._group_states:
            self._group_states[gid] = GroupState(self.window_sizes)
        return self._group_states[gid]
