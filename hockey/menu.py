from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional, Union

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list
from redbot.vendored.discord.ext import menus

from .components import (
    BackButton,
    BroadcastsButton,
    FilterButton,
    FirstItemButton,
    ForwardButton,
    GameflowButton,
    HeatmapButton,
    HockeySelectGame,
    HockeySelectPlayer,
    LastItemButton,
    SkipBackButton,
    SkipForwardButton,
    StopButton,
)
from .errors import NoSchedule
from .helper import LeaderboardType
from .player import SearchPlayer
from .schedule import PlayByPlay, PlayByPlayFilter, Schedule, ScheduleList

if TYPE_CHECKING:
    from .abc import HockeyMixin

_ = Translator("Hockey", __file__)
log = getLogger("red.trusty-cogs.hockey")


class GamesMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self.cog = cog
        self.source = source
        self.message = message
        self.current_page = 0
        self.ctx: commands.Context = None
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = SkipBackButton(discord.ButtonStyle.grey, 0)
        self.last_item = SkipForwardButton(discord.ButtonStyle.grey, 0)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.filter_button = FilterButton(discord.ButtonStyle.primary, 1)
        self.heatmap_button = HeatmapButton(discord.ButtonStyle.primary, 1)
        self.gameflow_button = GameflowButton(discord.ButtonStyle.primary, 1)
        self.broadcast_button = BroadcastsButton(1)

        self.add_item(self.stop_button)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.add_item(self.filter_button)
        if isinstance(self.source, Schedule):
            self.heatmap_button.label = _("Heatmap {style}").format(style=self.source.style)
            corsi = "Corsi" if self.source.corsi else "Expected Goals"
            self.gameflow_button.label = _("Gameflow {corsi} {strength}").format(
                corsi=corsi, strength=self.source.strength
            )
            self.add_item(self.heatmap_button)
            self.add_item(self.gameflow_button)
            self.add_item(self.broadcast_button)
        if isinstance(self.source, ScheduleList):
            self.add_item(self.broadcast_button)
        if isinstance(self.source, PlayByPlay):
            self.pbp_filter = PlayByPlayFilter(self.source.select_options)
            self.add_item(self.pbp_filter)
            self.heatmap_button.disabled = True
            self.gameflow_button.disabled = True
            self.broadcast_button.disabled = True
        self.select_view: Optional[HockeySelectGame] = None
        self.author = None

    async def on_timeout(self):
        try:
            await self.message.edit(view=None)
        except Exception:
            pass

    async def start(self, ctx: commands.Context):
        await self.source._prepare_once()
        if hasattr(self.source, "select_options") and len(self.source.select_options) > 1:
            self.select_view = HockeySelectGame(self.source.select_options[:25])
            self.add_item(self.select_view)
        self.ctx = ctx
        if isinstance(ctx, discord.Interaction):
            self.author = ctx.user
        else:
            self.author = ctx.author
        self.message = await self.send_initial_message(ctx)

    async def show_page(
        self,
        page_number: int,
        *,
        interaction: discord.Interaction,
        skip_next: bool = False,
        skip_prev: bool = False,
        game_id: Optional[int] = None,
    ) -> None:
        try:
            page = await self.source.get_page(
                page_number, skip_next=skip_next, skip_prev=skip_prev, game_id=game_id
            )
        except NoSchedule:
            if interaction.response.is_done():
                await interaction.followup.edit(content=self.format_error(), embed=None, view=self)
            else:
                await interaction.response.edit_message(
                    content=self.format_error(), embed=None, view=self
                )
            return
        if hasattr(self.source, "select_options") and len(self.source.select_options) > 1:
            self.remove_item(self.select_view)
            if page_number >= 12:
                self.select_view = HockeySelectGame(
                    self.source.select_options[page_number - 12 : page_number + 13]
                )
            else:
                self.select_view = HockeySelectGame(self.source.select_options[:25])
            self.add_item(self.select_view)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        if interaction.response.is_done():
            await interaction.followup.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def send_initial_message(self, ctx: commands.Context) -> discord.Message:
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.author = ctx.author

        try:
            page = await self.source.get_page(0)
        except (IndexError, NoSchedule):
            return await ctx.send(self.format_error(), view=self)
        kwargs = await self._get_kwargs_from_page(page)
        self.message = await ctx.send(**kwargs, view=self)
        return self.message

    def format_error(self):
        team = ""
        if self.source.team:
            team = _("for {teams} ").format(teams=humanize_list(self.source.team))
        msg = _("No schedule could be found {team}in dates between {last_searched}").format(
            team=team, last_searched=self.source._last_searched
        )
        return msg

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        try:
            await self.show_page(page_number, interaction=interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if self.author and interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class LeaderboardPages(menus.ListPageSource):
    def __init__(self, pages: list, style: LeaderboardType):
        super().__init__(pages, per_page=1)
        self.style = style

    def is_paginating(self) -> bool:
        return True

    async def format_page(self, view: BaseMenu, page: List[str]) -> discord.Embed:
        em = discord.Embed(timestamp=datetime.now())
        description = ""
        for msg in page:
            description += msg
        em.description = description
        em.set_author(
            name=view.ctx.guild.name
            + _(" Pickems {style} Leaderboard").format(style=self.style.as_str().title()),
            icon_url=view.ctx.guild.icon,
        )
        em.set_thumbnail(url=view.ctx.guild.icon)
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class PlayerPages(menus.ListPageSource):
    def __init__(
        self, pages: list, season: Optional[str] = None, include_headshot: Optional[bool] = True
    ):
        super().__init__(pages, per_page=1)
        self.pages: List[int] = pages
        self.season = season
        self.players = {p.id: p for p in pages}
        self.select_options = []
        self.include_headshot = include_headshot
        for count, player in enumerate(pages):
            player_name = player.name
            self.select_options.append(
                discord.SelectOption(
                    label=player_name[:50],
                    description=f"Page {count + 1}",
                    value=player.id,
                )
            )

    def is_paginating(self) -> bool:
        return len(self.pages) > 1

    async def format_page(self, view: BaseMenu, player: SearchPlayer) -> discord.Embed:
        # player = await Player.from_id(page, session=view.cog.session)
        log.trace("PlayerPages player: %s", player)
        player_stats = await view.cog.api.get_player(player.id)
        em = player_stats.get_embed(self.season, self.include_headshot)
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class SimplePages(menus.ListPageSource):
    def __init__(self, pages: List[Union[discord.Embed, str]]):
        super().__init__(pages, per_page=1)

    def is_paginating(self) -> bool:
        return True

    async def format_page(self, view: BaseMenu, page: Any) -> Union[discord.Embed, str]:
        if isinstance(page, discord.Embed):
            page.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return page


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        page_start: int = 0,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self.cog: HockeyMixin = cog
        self._source = source
        self.ctx: commands.Context = None
        self.message: discord.Message = None
        self.page_start = page_start
        self.current_page = page_start
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
        self.select_view = None
        if hasattr(self.source, "select_options"):
            self.select_view = HockeySelectPlayer(self.source.select_options[:25])
            self.add_item(self.select_view)
        self.author = None

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        try:
            await self.message.edit(view=None)
        except Exception:
            pass

    async def start(
        self, ctx: commands.Context, content: Optional[str] = None, ephemeral: bool = False
    ):
        await self.source._prepare_once()
        self.ctx = ctx
        self.message = await self.send_initial_message(ctx, content, ephemeral)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def update_select_view(self, page_number: int):
        if self.select_view is not None:
            self.remove_item(self.select_view)
        if not hasattr(self.source, "select_options"):
            return
        options = self.source.select_options[:25]
        if page_number >= 12:
            options = self.source.select_options[page_number - 12 : page_number + 13]
        self.select_view = HockeySelectPlayer(options)
        self.add_item(self.select_view)

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await self.update_select_view(page_number)
        if interaction.response.is_done():
            await interaction.followup.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)

    async def send_initial_message(
        self, ctx: commands.Context, content: Optional[str], ephemeral: bool
    ) -> discord.Message:
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        if content and not kwargs.get("content", None):
            kwargs["content"] = content
        self.author = ctx.author
        return await ctx.send(**kwargs, view=self, ephemeral=ephemeral)

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
        if self.author and interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True
