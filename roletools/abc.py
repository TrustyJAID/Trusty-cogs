from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.commands import Context
from redbot.core.i18n import Translator

from .converter import (
    ButtonStyleConverter,
    RawUserIds,
    RoleEmojiConverter,
    RoleHierarchyConverter,
    SelfRoleConverter,
)

if TYPE_CHECKING:
    from discord import Interaction

    from .buttons import ButtonRoleConverter
    from .select import SelectOptionRoleConverter, SelectRoleConverter


log = logging.getLogger("red.trusty-cogs.ReTrigger")
_ = Translator("Roletools", __file__)


@commands.group()
@commands.guild_only()
async def roletools(self: commands.Cog, ctx: Context) -> None:
    """
    Commands for creating custom role settings
    """
    if isinstance(ctx, discord.Interaction):
        command_mapping = {
            "exclude": self.exclusive,
            "bulkreact": self.bulkreact,
            "sticky": self.sticky,
            "react": self.react,
            "selfrem": self.selfrem,
            "buttons": self.buttons,
            "giverole": self.giverole,
            "viewroles": self.viewroles,
            "select": self.select,
            "forcerole": self.forcerole,
            "globalatomic": self.globalatomic,
            "selfrole": self.selfrole,
            "include": self.inclusive,
            "cleanup": self.cleanup,
            "autorole": self.autorole,
            "selfadd": self.selfadd,
            "required": self.required_roles,
            "ownercleanup": self.ownercleanup,
            "forceroleremove": self.forceroleremove,
            "reactroles": self.reactroles,
            "cost": self.cost,
            "removerole": self.removerole,
            "remreact": self.remreact,
            "clearreact": self.clearreact,
            "atomic": self.atomic,
        }
        options = ctx.data["options"][0]
        option = options["name"]
        func = command_mapping[option]
        if getattr(func, "requires", None):
            if not await self.check_requires(func, ctx):
                return

        if getattr(func, "_prepare_cooldowns", None):
            if not await self.check_cooldowns(func, ctx):
                return

        try:
            kwargs = {}
            for option in options.get("options", []):
                name = option["name"]
                kwargs[name] = self.convert_slash_args(ctx, option)
        except KeyError:
            kwargs = {}
            pass
        except AttributeError:
            log.exception("Error getting past main parser")
            await ctx.response.send_message(
                _("One or more options you have provided are not available in DM's."),
                ephemeral=True,
            )
            return
        await func(ctx, **kwargs)


class RoleToolsMixin(ABC):
    """
    Base class for well behaved type hint detection with composite class.

    Basically, to keep developers sane when not all attributes are defined in each mixin.
    """

    c = roletools

    def __init__(self, *_args):
        self.config: Config
        self.bot: Red
        self.settings: Dict[Any, Any]
        self._ready: asyncio.Event

    #######################################################################
    # roletools.py                                                        #
    #######################################################################

    @abstractmethod
    def update_cooldown(
        self, ctx: Context, rate: int, per: float, _type: commands.BucketType
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def initalize(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def selfrole(self, ctx: Union[Context, Interaction], *, role: SelfRoleConverter) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def selfrole_remove(
        self, ctx: Union[Context, Interaction], *, role: SelfRoleConverter
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def giverole(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *who: Union[discord.Role, discord.TextChannel, discord.Member, str],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def removerole(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *who: Union[discord.Role, discord.TextChannel, discord.Member, str],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def forcerole(
        self,
        ctx: Union[Context, Interaction],
        users: commands.Greedy[Union[discord.Member, RawUserIds]],
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def forceroleremove(
        self,
        ctx: Union[Context, Interaction],
        users: commands.Greedy[Union[discord.Member, RawUserIds]],
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def viewroles(
        self, ctx: Union[Context, Interaction], *, role: Optional[discord.Role]
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def roletools_slash(self, ctx: Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def roletools_global_slash(self, ctx: Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def roletools_global_slash_disable(self, ctx: Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def roletools_guild_slash(self, ctx: Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def roletools_delete_slash(self, ctx: Context) -> None:
        raise NotImplementedError()

    #######################################################################
    # inclusive.py                                                        #
    #######################################################################

    @abstractmethod
    async def inclusive(self, ctx: Union[Context, Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def inclusive_add(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *,
        include: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def mutual_inclusive_add(self, ctx: Context, *roles: RoleHierarchyConverter) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def inclusive_remove(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *,
        include: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        raise NotImplementedError()

    #######################################################################
    # exclusive.py                                                        #
    #######################################################################

    @abstractmethod
    async def exclusive(self, ctx: Union[Context, Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def exclusive_add(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *,
        exclude: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def mutual_exclusive_add(self, ctx: Context, *roles: RoleHierarchyConverter) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def exclusive_remove(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *,
        exclude: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        raise NotImplementedError()

    #######################################################################
    # requires.py                                                         #
    #######################################################################

    @abstractmethod
    async def required_roles(self, ctx: Union[Context, Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def required_add(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *,
        required: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def required_remove(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *,
        required: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        raise NotImplementedError()

    #######################################################################
    # settings.py                                                         #
    #######################################################################

    @abstractmethod
    async def selfadd(
        self,
        ctx: Union[Context, Interaction],
        true_or_false: Optional[bool] = None,
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def selfrem(
        self,
        ctx: Union[Context, Interaction],
        true_or_false: Optional[bool] = None,
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def atomic(
        self, ctx: Union[Context, Interaction], true_or_false: Optional[Union[bool, str]] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def globalatomic(self, ctx: Context, true_or_false: Optional[bool] = None) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def cost(
        self,
        ctx: Union[Context, Interaction],
        cost: Optional[int] = None,
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def sticky(
        self,
        ctx: Union[Context, Interaction],
        true_or_false: Optional[bool] = None,
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def autorole(
        self,
        ctx: Union[Context, Interaction],
        true_or_false: Optional[bool] = None,
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        raise NotImplementedError()

    #######################################################################
    # reactions.py                                                        #
    #######################################################################

    @abstractmethod
    async def cleanup(self, ctx: Union[Context, Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def ownercleanup(self, ctx: Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def reactroles(self, ctx: Union[Context, Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clearreact(
        self,
        ctx: Union[Context, Interaction],
        message: discord.Message,
        *emojis: Optional[Union[discord.Emoji, str]],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def react(
        self,
        ctx: Union[Context, Interaction],
        message: discord.Message,
        emoji: Union[discord.Emoji, str],
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def remreact(
        self,
        ctx: Union[Context, Interaction],
        message: discord.Message,
        *,
        role_or_emoji: Union[RoleHierarchyConverter, discord.Emoji, str],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def bulkreact(
        self,
        ctx: Context,
        message: discord.Message,
        *role_emoji: RoleEmojiConverter,
    ) -> None:
        raise NotImplementedError()

    #######################################################################
    # events.py                                                           #
    #######################################################################

    @abstractmethod
    async def check_guild_verification(
        self, member: discord.Member, guild: discord.Guild
    ) -> Union[bool, int]:
        raise NotImplementedError()

    @abstractmethod
    async def wait_for_verification(self, member: discord.Member, guild: discord.Guild) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def check_atomicity(self, guild: discord.Guild) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def give_roles(
        self,
        member: discord.Member,
        roles: List[discord.Role],
        reason: Optional[str] = None,
        *,
        check_required: bool = True,
        check_exclusive: bool = True,
        check_inclusive: bool = True,
        check_cost: bool = True,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def remove_roles(
        self,
        member: discord.Member,
        roles: List[discord.Role],
        reason: Optional[str] = None,
        *,
        check_inclusive: bool = True,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def _auto_give(self, member: discord.Member) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def _sticky_leave(self, member: discord.Member) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def _sticky_join(self, member: discord.Member) -> None:
        raise NotImplementedError()

    #######################################################################
    # buttons.py                                                          #
    #######################################################################

    @abstractmethod
    async def initialize_buttons(self):
        raise NotImplementedError()

    @abstractmethod
    async def button_autocomplete(self, interaction: discord.Interaction) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def buttons(self, ctx: Union[Context, Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def send_buttons(
        self,
        ctx: Union[Context, Interaction],
        channel: discord.TextChannel,
        buttons: commands.Greedy[ButtonRoleConverter],
        *,
        message: str,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_with_buttons(
        self,
        ctx: Union[Context, Interaction],
        message: discord.Message,
        buttons: commands.Greedy[ButtonRoleConverter],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def create_button(
        self,
        ctx: Union[Context, Interaction],
        name: str,
        role: RoleHierarchyConverter,
        label: Optional[str] = None,
        emoji: Optional[Union[discord.PartialEmoji, str]] = None,
        style: Optional[ButtonStyleConverter] = discord.ButtonStyle.primary,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_button(self, ctx: Union[Context, Interaction], *, name: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def button_roles_view(self, ctx: Union[Context, Interaction]) -> None:
        raise NotImplementedError()

    #######################################################################
    # select.py                                                           #
    #######################################################################

    @abstractmethod
    async def initialize_select(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def select_option_autocomplete(self, interaction: discord.Interaction) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def select_menu_autocomplete(self, interaction: discord.Interaction) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def select(self, ctx: Union[Context, Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def create_select_menu(
        self,
        ctx: Union[Context, Interaction],
        name: str,
        options: commands.Greedy[SelectOptionRoleConverter],
        min_values: Optional[int] = None,
        max_values: Optional[int] = None,
        *,
        placeholder: Optional[str] = None,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_select_menu(self, ctx: Union[Context, Interaction], *, name: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def create_select_option(
        self,
        ctx: Union[Context, Interaction],
        name: str,
        role: RoleHierarchyConverter,
        label: Optional[str] = None,
        description: Optional[str] = None,
        emoji: Optional[Union[discord.PartialEmoji, str]] = None,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_select_option(self, ctx: Union[Context, Interaction], *, name: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def send_select(
        self,
        ctx: Union[Context, Interaction],
        channel: discord.TextChannel,
        menus: commands.Greedy[SelectRoleConverter],
        *,
        message: str,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_with_select(
        self,
        ctx: Union[Context, Interaction],
        message: discord.Message,
        menus: commands.Greedy[SelectRoleConverter],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def select_menus_view(self, ctx: Union[Context, Interaction]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def select_options_view(self, ctx: Union[Context, Interaction]) -> None:
        raise NotImplementedError()

    #######################################################################
    # slash.py                                                            #
    #######################################################################

    @abstractmethod
    async def load_slash(self):
        raise NotImplementedError()

    @abstractmethod
    async def role_hierarchy_options(self, interaction: discord.Interaction):
        raise NotImplementedError()

    @abstractmethod
    async def check_requires(self, func, interaction: discord.Interaction):
        raise NotImplementedError()

    @abstractmethod
    async def check_cooldowns(self, func, interaction: discord.Interaction):
        raise NotImplementedError()

    @abstractmethod
    async def pre_check_slash(self, interaction):
        raise NotImplementedError()

    @abstractmethod
    async def on_interaction(self, interaction: discord.Interaction):
        raise NotImplementedError()
