from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional, Tuple, Union

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.vendored.discord.ext import menus

log = getLogger("red.Trusty-cogs.serverstats")

_ = Translator("serverstats", __file__)


class AvatarDisplay(Enum):
    default = 0
    _global = 1
    guild = 2

    def get_name(self):
        return {
            AvatarDisplay.default: _("Default Avatar"),
            AvatarDisplay._global: _("Global Avatar"),
            AvatarDisplay.guild: _("Server Avatar"),
        }.get(self, _("Global Avatar"))

    def get_asset(self, member: Union[discord.Member, discord.User]) -> Optional[discord.Asset]:
        if self is AvatarDisplay.default:
            return member.default_avatar
        elif self is AvatarDisplay.guild:
            return getattr(member, "guild_avatar", None)
        return member.avatar


class AvatarPages(menus.ListPageSource):
    def __init__(self, members: List[discord.abc.User]):
        super().__init__(members, per_page=1)
        self.use_display_avatar: bool = True
        self.avatar_display: AvatarDisplay = None

    def adjust_buttons(self, menu: BaseView, member: Union[discord.Member, discord.User]):
        for style in AvatarDisplay:
            if style is self.avatar_display or style.get_asset(member) is None:
                menu.avatar_swap[style.value].disabled = True
            else:
                menu.avatar_swap[style.value].disabled = False

    async def format_page(
        self, menu: BaseView, member: Union[discord.Member, discord.User]
    ) -> discord.Embed:
        if self.avatar_display is None:
            for style in AvatarDisplay:
                if style.get_asset(member):
                    self.avatar_display = style
                    # iterate upwards and replace until we find the
                    # highest level which is the guild specific avatar
        em = discord.Embed(title=self.avatar_display.get_name(), colour=member.colour)
        url = self.avatar_display.get_asset(member)
        assert isinstance(url, discord.Asset)
        self.adjust_buttons(menu, member)
        formats = ["jpg", "png", "webp"]
        if url.is_animated():
            formats.append("gif")
        if url != member.default_avatar:
            description = (
                " | ".join(f"[{a.upper()}]({url.replace(size=4096, format=a)})" for a in formats)
                + "\n"
            )
            description += " | ".join(
                f"[{a}]({url.replace(size=a)})" for a in [32, 64, 128, 256, 512, 1024, 2048, 4096]
            )
            em.description = description
        if isinstance(member, discord.Member):
            name = f"{member} {f'~ {member.nick}' if member.nick else ''}"
        else:
            name = str(member)
        em.set_image(url=url.replace(size=4096))
        em.set_author(name=name, icon_url=url, url=url)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class SwapAvatarButton(discord.ui.Button):
    def __init__(self, avatar_display: AvatarDisplay):
        super().__init__(style=discord.ButtonStyle.grey, label=avatar_display.get_name())
        self.view: BaseView
        self.avatar_display = avatar_display

    async def callback(self, interaction: discord.Interaction):
        source: AvatarPages = self.view.source
        source.use_display_avatar = not source.use_display_avatar
        source.avatar_display = self.avatar_display
        await self.view.show_checked_page(self.view.current_page, interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()


class GuildPages(menus.ListPageSource):
    def __init__(self, guilds: List[discord.Guild]):
        super().__init__(guilds, per_page=1)
        self.guild: Optional[discord.Guild] = None

    async def format_page(self, menu: menus.MenuPages, guild: discord.Guild):
        self.guild = guild
        em = await menu.cog.guild_embed(guild)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class TopMemberPages(menus.ListPageSource):
    def __init__(self, pages: List[discord.Member], include_bots: Optional[bool]):
        super().__init__(pages, per_page=10)
        self.members = pages
        self.include_bots = include_bots

    async def format_page(self, menu: BaseView, page: discord.Member):
        msg = ""
        guild = page[0].guild
        for member in page:
            joined_dt = getattr(member, "joined_at", None) or datetime.now(timezone.utc)
            joined_at = discord.utils.format_dt(joined_dt)
            msg += f"{self.members.index(member) + 1}. {member.mention} - {joined_at}\n"
        if menu.ctx and await menu.ctx.embed_requested():
            em = discord.Embed(description=msg)
            title = _("{guild} top members").format(guild=guild.name)
            if self.include_bots is False:
                title += _(" not including bots")
            if self.include_bots is True:
                title = _("{guild} top bots").format(guild=guild.name)
            em.set_author(name=title, icon_url=guild.icon)
            em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            return em
        return msg


class ListPages(menus.ListPageSource):
    def __init__(self, pages: List[Union[discord.Embed, str]]):
        super().__init__(pages, per_page=1)

    async def format_page(self, menu: menus.MenuPages, page: Union[discord.Embed, str]):
        return page


class StopButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        if interaction.message.flags.ephemeral:
            await interaction.response.edit_message(view=None)
            return
        await interaction.message.delete()


class ForwardButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page + 1, interaction)


class BackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page - 1, interaction)


class LastItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(self.view._source.get_max_pages() - 1, interaction)


class FirstItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, interaction)


class LeaveGuildButton(discord.ui.Button):
    def __init__(self, style: discord.ButtonStyle, row: Optional[int]):
        super().__init__(style=style, row=row, label=_("Leave Guild"))

    async def callback(self, interaction: discord.Interaction):
        await self.view.cog.confirm_leave_guild(self.view.ctx, self.view.source.guild)
        if not interaction.response.is_done():
            await interaction.response.defer()


class JoinGuildButton(discord.ui.Button):
    def __init__(self, style: discord.ButtonStyle, row: Optional[int]):
        super().__init__(style=style, row=row, label=_("Join Guild"))

    async def callback(self, interaction: discord.Interaction):
        invite = await self.view.cog.get_guild_invite(self.view.source.guild)
        if invite:
            await interaction.response.send_message(str(invite))
        else:
            await interaction.response.send_message(
                _("I cannot find or create an invite for `{guild}`").format(
                    guild=self.view.source.guild.name
                )
            )
        if not interaction.response.is_done():
            await interaction.response.defer()


class BaseView(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        page_start: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self._source = source
        self.cog = cog
        self.page_start = page_start
        self.current_page = page_start
        self.message = message
        self.ctx = kwargs.get("ctx", None)
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = FirstItemButton(discord.ButtonStyle.grey, 0)
        self.last_item = LastItemButton(discord.ButtonStyle.grey, 0)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.add_item(self.stop_button)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        if (
            isinstance(source, GuildPages)
            and self.ctx
            and self.ctx.author.id in self.ctx.bot.owner_ids
        ):
            self.leave_guild_button = LeaveGuildButton(discord.ButtonStyle.red, 1)
            self.join_guild_button = JoinGuildButton(discord.ButtonStyle.green, 1)
            self.add_item(self.leave_guild_button)
            self.add_item(self.join_guild_button)
        if isinstance(source, AvatarPages):
            self.avatar_swap = {}
            for style in AvatarDisplay:
                button = SwapAvatarButton(style)
                self.avatar_swap[style.value] = button
                self.add_item(button)

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def start(self, ctx: commands.Context):
        await self.send_initial_message(ctx)

    def disable_navigation(self):
        self.first_item.disabled = True
        self.back_button.disabled = True
        self.forward_button.disabled = True
        self.last_item.disabled = True

    def enable_navigation(self):
        self.first_item.disabled = False
        self.back_button.disabled = False
        self.forward_button.disabled = False
        self.last_item.disabled = False

    async def send_initial_message(self, ctx: commands.Context):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.ctx = ctx
        if not self.source.is_paginating():
            self.disable_navigation()
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        self.message = await ctx.send(**kwargs, view=self)
        return self.message

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        if not self.source.is_paginating():
            self.disable_navigation()
        else:
            self.enable_navigation()
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await interaction.response.edit_message(**kwargs, view=self)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.user.id not in (*self.ctx.bot.owner_ids, self.ctx.author.id):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class ConfirmView(discord.ui.View):
    """
    This is just a copy of my version from Red to be removed later possibly
    https://github.com/Cog-Creators/Red-DiscordBot/pull/6176
    """

    def __init__(
        self,
        author: Optional[discord.abc.User] = None,
        *,
        timeout: float = 180.0,
        disable_buttons: bool = False,
    ):
        if timeout is None:
            raise TypeError("This view should not be used as a persistent view.")
        super().__init__(timeout=timeout)
        self.result: Optional[bool] = None
        self.author: Optional[discord.abc.User] = author
        self.message: Optional[discord.Message] = None
        self.disable_buttons = disable_buttons

    async def on_timeout(self):
        if self.message is None:
            # we can't do anything here if message is none
            return

        if self.disable_buttons:
            self.confirm_button.disabled = True
            self.dismiss_button.disabled = True
            await self.message.edit(view=self)
        else:
            await self.message.edit(view=None)

    @discord.ui.button(label=_("Yes"), style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        self.stop()
        # respond to the interaction so the user does not see "interaction failed".
        await interaction.response.defer()
        # call `on_timeout` explicitly here since it's not called when `stop()` is called.
        await self.on_timeout()

    @discord.ui.button(label=_("No"), style=discord.ButtonStyle.secondary)
    async def dismiss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        self.stop()
        # respond to the interaction so the user does not see "interaction failed".
        await interaction.response.defer()
        # call `on_timeout` explicitly here since it's not called when `stop()` is called.
        await self.on_timeout()

    async def interaction_check(self, interaction: discord.Interaction):
        if self.message is None:
            self.message = interaction.message
        if self.author and interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True
