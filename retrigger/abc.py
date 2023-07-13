from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Literal, Optional, Tuple, Union

import discord

if TYPE_CHECKING:
    from redbot.core import Config, commands
    from redbot.core.bot import Red
    from redbot.core.commands import TimedeltaConverter

    from .converters import (
        ChannelUserRole,
        MultiFlags,
        Trigger,
        TriggerExists,
        ValidEmoji,
        ValidRegex,
    )


class ReTriggerMixin(ABC):
    def __init__(self, *_args):
        super().__init__()
        self.config: Config
        self.bot: Red
        self.triggers: Dict[int, Dict[str, Trigger]]

    #############################################################################
    # triggerhandler.py                                                         #
    #############################################################################

    @abstractmethod
    async def remove_trigger_from_cache(self, guild_id: int, trigger: Trigger) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def can_edit(self, author: discord.Member, trigger: Trigger) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def can_enable_or_disable(self, author: discord.Member, trigger: Trigger) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def is_mod_or_admin(self, member: discord.Member) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def make_guild_folder(self, directory) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def save_image_location(self, image_url: str, guild: discord.Guild) -> Optional[str]:
        raise NotImplementedError()

    @abstractmethod
    async def wait_for_image(self, ctx: commands.Context) -> Optional[discord.Message]:
        raise NotImplementedError()

    @abstractmethod
    async def wait_for_multiple_images(self, ctx: commands.Context) -> List[str]:
        raise NotImplementedError()

    @abstractmethod
    async def wait_for_multiple_responses(self, ctx: commands.Context) -> List[discord.Message]:
        raise NotImplementedError()

    @abstractmethod
    def resize_image(self, size: int, image: str) -> discord.File:
        raise NotImplementedError()

    @abstractmethod
    def resize_gif(self, size: int, image: str) -> discord.File:
        raise NotImplementedError()

    @abstractmethod
    async def check_is_command(self, message: discord.Message) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def on_message(self, message: discord.Message) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def check_triggers(self, message: discord.Message, edit: bool) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def get_image_text(self, message: discord.Message) -> str:
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def convert_embed_to_string(embed: discord.Embed, embed_index: int = 0) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def safe_regex_search(
        self, guild: discord.Guild, trigger: Trigger, content: str
    ) -> Tuple[bool, list]:
        raise NotImplementedError()

    @abstractmethod
    async def perform_trigger(
        self, message: discord.Message, trigger: Trigger, find: List[str]
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def convert_parms(
        self, message: discord.Message, raw_response: str, trigger: Trigger, find: List[str]
    ) -> str:
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    async def transform_parameter(result: str, message: discord.Message) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def modlog_action(
        self, message: discord.Message, trigger: Trigger, find: List[str], action: str
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def remove_trigger(self, guild_id: int, trigger_name: str) -> bool:
        raise NotImplementedError()

    #############################################################################
    # retrigger.py                                                              #
    #############################################################################

    @abstractmethod
    async def _not_authorized(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def _no_multi(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def _no_edit(self, ctx: Union[commands.Context, discord.Interaction]):
        raise NotImplementedError()

    @abstractmethod
    async def _no_trigger(self, ctx: Union[commands.Context, discord.Interaction], trigger: str):
        raise NotImplementedError()

    @abstractmethod
    async def _already_exists(self, ctx: Union[commands.Context, discord.Interaction], name: str):
        raise NotImplementedError()

    @abstractmethod
    async def _trigger_set(self, ctx: Union[commands.Context, discord.Interaction], name: str):
        raise NotImplementedError()

    @abstractmethod
    async def modlog_settings(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def modlog_bans(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def modlog_kicks(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def modlog_filter(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def modlog_addroles(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def modlog_removeroles(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def modlog_channel(
        self, ctx: commands.Context, channel: Union[discord.TextChannel, str, None]
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def cooldown(
        self, ctx: commands.Context, trigger: TriggerExists, time: int, style="guild"
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def whitelist_add(
        self,
        ctx: commands.Context,
        trigger: TriggerExists,
        channel_user_role: commands.Greedy[ChannelUserRole],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def whitelist_remove(
        self,
        ctx: commands.Context,
        trigger: TriggerExists,
        channel_user_role: commands.Greedy[ChannelUserRole],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def blacklist_add(
        self,
        ctx: commands.Context,
        trigger: TriggerExists,
        channel_user_role: commands.Greedy[ChannelUserRole],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def blacklist_remove(
        self,
        ctx: commands.Context,
        trigger: TriggerExists,
        channel_user_role: commands.Greedy[ChannelUserRole],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_regex(
        self, ctx: commands.Context, trigger: TriggerExists, *, regex: ValidRegex
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def toggle_ocr_search(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def toggle_nsfw(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def toggle_read_embeds(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def toggle_filename_search(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_reply(
        self, ctx: commands.Context, trigger: TriggerExists, set_to: Optional[bool] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_tts(self, ctx: commands.Context, trigger: TriggerExists, set_to: bool) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_user_mention(
        self, ctx: commands.Context, trigger: TriggerExists, set_to: bool
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_everyone_mention(
        self, ctx: commands.Context, trigger: TriggerExists, set_to: bool
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_role_mention(
        self, ctx: commands.Context, trigger: TriggerExists, set_to: bool
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def toggle_check_edits(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_text(self, ctx: commands.Context, trigger: TriggerExists, *, text: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_chance(
        self, ctx: commands.Context, trigger: TriggerExists, chance: int
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_delete_after(
        self,
        ctx: commands.Context,
        trigger: TriggerExists,
        *,
        delete_after: TimedeltaConverter = None,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_ignore_commands(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_command(
        self, ctx: commands.Context, trigger: TriggerExists, *, command: str
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_roles(
        self, ctx: commands.Context, trigger: TriggerExists, roles: commands.Greedy[discord.Role]
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_reactions(
        self, ctx: commands.Context, trigger: TriggerExists, emojis: commands.Greedy[ValidEmoji]
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def enable_trigger(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def disable_trigger(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def list(
        self, ctx: commands.Context, guild_id: Optional[int] = None, trigger: TriggerExists = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def remove(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def explain(self, ctx: commands.Context, page_num: Optional[int] = 1) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def text(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        delete_after: Optional[TimedeltaConverter] = None,
        *,
        text: str,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def random(self, ctx: commands.Context, name: str, regex: ValidRegex) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def dm(self, ctx: commands.Context, name: str, regex: ValidRegex, *, text: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def dmme(
        self, ctx: commands.Context, name: str, regex: ValidRegex, *, text: str
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def rename(
        self, ctx: commands.Context, name: str, regex: ValidRegex, *, text: str
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def image(
        self, ctx: commands.Context, name: str, regex: ValidRegex, image_url: str = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def randomimage(self, ctx: commands.Context, name: str, regex: ValidRegex) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def imagetext(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        text: str,
        image_url: str = None,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def resize(
        self, ctx: commands.Context, name: str, regex: ValidRegex, image_url: str = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def ban(self, ctx: commands.Context, name: str, regex: ValidRegex) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def kick(self, ctx: commands.Context, name: str, regex: ValidRegex) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def react(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        emojis: commands.Greedy[ValidEmoji],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def publish(self, ctx: commands.Context, name: str, regex: ValidRegex) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def command(
        self, ctx: commands.Context, name: str, regex: ValidRegex, *, command: str
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def mock(
        self, ctx: commands.Context, name: str, regex: ValidRegex, *, command: str
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def filter(
        self,
        ctx: commands.Context,
        name: str,
        check_filenames: Optional[bool] = False,
        *,
        regex: str,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def addrole(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        roles: commands.Greedy[discord.Role],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def removerole(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        roles: commands.Greedy[discord.Role],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def multi(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        *,
        multi: MultiFlags,
    ) -> None:
        raise NotImplementedError()
