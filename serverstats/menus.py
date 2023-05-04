from __future__ import annotations

import logging
from typing import Any, List, Optional, Union

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.vendored.discord.ext import menus

log = logging.getLogger("red.Trusty-cogs.serverstats")

_ = Translator("serverstats", __file__)


class AvatarPages(menus.ListPageSource):
    def __init__(self, members: List[discord.abc.User]):
        super().__init__(members, per_page=1)
        self.use_display_avatar: bool = True

    def is_paginating(self):
        return True

    async def format_page(
        self, menu: BaseView, member: Union[discord.Member, discord.User]
    ) -> discord.Embed:
        em = discord.Embed(title=_("**Avatar**"), colour=member.colour)
        if self.use_display_avatar:
            url = str(member.display_avatar)
            menu.avatar_swap.label = _("Show global avatar")
        else:
            url = str(member.avatar)
            menu.avatar_swap.label = _("Show server avatar")
        if not getattr(member, "guild_avatar", None):
            menu.avatar_swap.disabled = True
        else:
            menu.avatar_swap.disabled = False
        if isinstance(member, discord.Member):
            name = f"{member} {f'~ {member.nick}' if member.nick else ''}"
        else:
            name = str(member)
        em.set_image(url=url)
        em.set_author(name=name, icon_url=url, url=url)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class SwapAvatarButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.grey, label=_("Show global avatar"))
        self.view: BaseView

    async def callback(self, interaction: discord.Interaction):
        source: AvatarPages = self.view.source
        source.use_display_avatar = not source.use_display_avatar
        await self.view.show_checked_page(self.view.current_page, interaction)
        if not interaction.response.is_done():
            await interaction.response.defer()


class GuildPages(menus.ListPageSource):
    def __init__(self, guilds: List[discord.Guild]):
        super().__init__(guilds, per_page=1)
        self.guild: Optional[discord.Guild] = None

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, guild: discord.Guild):
        self.guild = guild
        em = await menu.cog.guild_embed(guild)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class ListPages(menus.ListPageSource):
    def __init__(self, pages: List[Union[discord.Embed, str]]):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

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
                    guild=self.source.guild.name
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
            self.avatar_swap = SwapAvatarButton()
            self.add_item(self.avatar_swap)

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def start(self, ctx: commands.Context):
        await self.send_initial_message(ctx)

    async def send_initial_message(self, ctx: commands.Context):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.ctx = ctx
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
