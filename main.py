from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType

from .core.ban import RereadBanHandler
from .core.config import PluginConfig
from .core.engine import RereadEngine
from .core.state import StateManager


class RereadPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config)
        self.state_mgr = StateManager(self.cfg.window_sizes)
        self.engine = RereadEngine(self.cfg)
        self.ban_handler = RereadBanHandler(self.cfg)

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def reread_handle(self, event: AstrMessageEvent):
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

        async with state.lock:
            plan = self.engine.evaluate(state, seg_type, send_id, seg)

        if not plan:
            return

        if plan.action == "ban":
            await self.ban_handler.handle(event, plan.repeat_count)
            return

        if not plan.output_segment:
            return

        yield event.chain_result([plan.output_segment])
