import re
from datetime import datetime
from typing import List, Optional, Pattern

import discord
from red_commons.logging import getLogger
from redbot.core.i18n import Translator

from .constants import TEAMS
from .errors import NoSchedule
from .helper import DATE_RE

_ = Translator("Hockey", __file__)
log = getLogger("red.trusty-cogs.hockey")

__all__ = (
    "StopButton",
    "ForwardButton",
    "BackButton",
    "LastItemButton",
    "FirstItemButton",
    "SkipForwardButton",
    "SkipBackButton",
    "FilterModal",
    "FilterButton",
    "HeatmapButton",
    "GameflowButton",
    "HockeySelectGame",
    "HockeySelectPlayer",
)


class StopButton(discord.ui.Button):
    def __init__(
        self,
        style: Optional[discord.ButtonStyle] = None,
        row: Optional[int] = None,
    ):
        if style is None:
            style = discord.ButtonStyle.red
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        if interaction.message.flags.ephemeral:
            await interaction.response.edit_message(view=None)
        else:
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


class SkipForwardButton(discord.ui.Button):
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
        await self.view.show_page(0, skip_next=True, interaction=interaction)


class SkipBackButton(discord.ui.Button):
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
        await self.view.show_page(0, skip_prev=True, interaction=interaction)


class FilterModal(discord.ui.Modal):
    def __init__(self, view: discord.ui.View):
        super().__init__(title=_("Filter games"))
        self.view = view
        cur_date = self.view.source.date
        self.teams = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            label="Teams to filter",
            placeholder="Edmonton Oilers\nCanucks\nHabs",
            default="\n".join(t for t in self.view.source.team),
            required=False,
        )
        self.date = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Dates to filter",
            placeholder="YYYY-MM-DD",
            default=f"{cur_date.year}-{cur_date.month}-{cur_date.day}",
            min_length=8,
            max_length=10,
            required=False,
        )
        self.add_item(self.date)
        self.add_item(self.teams)

    async def on_submit(self, interaction: discord.Interaction):
        if self.date.value:
            search = DATE_RE.search(self.date.value)
            if search:
                date_str = f"{search.group(1)}-{search.group(3)}-{search.group(4)}"
                date = datetime.strptime(date_str, "%Y-%m-%d")
                self.view.source.date = date
                try:
                    await self.view.source.prepare()
                except NoSchedule:
                    await interaction.response.send_message(self.view.format_error())
                    return
        if self.teams.value:
            potential_teams = self.teams.value.split()
            teams: List[str] = []
            for team, data in TEAMS.items():
                if "Team" in team:
                    continue
                nick = data["nickname"]
                short = data["tri_code"]
                pattern = rf"{short}\b|" + r"|".join(rf"\b{i}\b" for i in team.split())
                if nick:
                    pattern += r"|" + r"|".join(rf"\b{i}\b" for i in nick)
                log.trace("FilterModal pattern: %s", pattern)
                reg: Pattern = re.compile(rf"\b{pattern}", flags=re.I)
                for pot in potential_teams:
                    find = reg.findall(pot)
                    if find:
                        teams.append(team)
                self.view.source.team = teams
            try:
                await self.view.source.prepare()
            except NoSchedule:
                return await self.view.ctx.send(self.view.format_error())
        await self.view.show_page(0, interaction=interaction)


class FilterButton(discord.ui.Button):
    def __init__(self, style: discord.ButtonStyle, row: Optional[int]):
        super().__init__(style=style, row=row, label=_("Filter"))
        self.style = style

    async def callback(self, interaction: discord.Interaction):
        """stops the pagination session."""
        modal = FilterModal(self.view)
        await interaction.response.send_modal(modal)


class TeamModal(discord.ui.Modal):
    def __init__(self, view: discord.ui.View):
        super().__init__(title=_("Filter games"))
        self.view = view
        self.team = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Team to filter",
            placeholder="Edmonton Oilers",
            max_length=50,
        )
        self.add_item(self.team)

    async def on_submit(self, interaction: discord.Interaction):
        teams: List[str] = []
        for team, data in TEAMS.items():
            if "Team" in team:
                continue
            pattern = rf"{team}|{data['tri_code']}|{'|'.join(n for n in data['nickname'])}"
            log.trace("TeamModal pattern: %s", pattern)
            reg: Pattern = re.compile(pattern, flags=re.I)
            find = reg.search(self.team.value)
            if find:
                teams.append(team)
        log.trace("TeamModal teams: %s", teams)
        if not teams:
            await interaction.response.send_message(
                _("`{content}` is not a valid team.").format(content=self.view.value[:200]),
                ephemeral=True,
            )
            return
        self.view.search = teams[0]
        self.view.context = "team"
        await self.view.prepare()
        for page in self.view.pages:
            if teams[0].lower() in page.author.name.lower():
                page_num = self.view.pages.index(page)
        log.trace("Setting page number %s %s", page_num, teams[0])
        await self.view.show_page(page_num, interaction=interaction)


class TeamButton(discord.ui.Button):
    def __init__(self, style: discord.ButtonStyle, row: Optional[int]):
        super().__init__(style=style, row=row, label=_("Team"))
        self.style = style

    async def callback(self, interaction: discord.Interaction):
        """stops the pagination session."""
        modal = TeamModal(self.view)
        await interaction.response.send_modal(modal)


class HeatmapButton(discord.ui.Button):
    def __init__(self, style: discord.ButtonStyle, row: Optional[int]):
        super().__init__(style=style, row=row, label=_("Heatmap"))
        self.style = style

    async def callback(self, interaction: discord.Interaction):
        """stops the pagination session."""
        mapping = {
            "all": "ev",
            "ev": "5v5",
            "5v5": "sva",
            "sva": "home5v4",
            "home5v4": "away5v4",
            "away5v4": "all",
        }
        if self.view.source.include_gameflow:
            self.view.source.include_gameflow = False
        if not self.view.source.include_heatmap:
            self.view.source.include_heatmap = True
            self.label = _("Heatmap {style}").format(style=self.view.source.style)
            await self.view.show_page(self.view.current_page, interaction=interaction)
            return
        else:
            self.view.source.style = mapping[self.view.source.style]
            self.label = _("Heatmap {style}").format(style=self.view.source.style)
            await self.view.show_page(self.view.current_page, interaction=interaction)
            return


class BroadcastsButton(discord.ui.Button):
    def __init__(self, row: Optional[int]):
        super().__init__(style=discord.ButtonStyle.primary, row=row, label=_("Broadcasts"))
        self.style = discord.ButtonStyle.primary

    async def callback(self, interaction: discord.Interaction):
        self.view.source.show_broadcasts = not self.view.source.show_broadcasts
        self.style = (
            discord.ButtonStyle.primary
            if not self.view.source.show_broadcasts
            else discord.ButtonStyle.green
        )
        await self.view.show_page(self.view.current_page, interaction=interaction)


class GameflowButton(discord.ui.Button):
    def __init__(self, style: discord.ButtonStyle, row: Optional[int]):
        super().__init__(style=style, row=row, label=_("Gameflow"))
        self.style = style

    async def callback(self, interaction: discord.Interaction):
        """stops the pagination session."""
        mapping = {
            (True, "all"): (True, "ev"),
            (True, "ev"): (True, "5v5"),
            (True, "5v5"): (True, "sva"),
            (True, "sva"): (False, "all"),
            (False, "all"): (False, "ev"),
            (False, "ev"): (False, "5v5"),
            (False, "5v5"): (False, "sva"),
            (False, "sva"): (True, "all"),
        }
        if self.view.source.include_heatmap:
            self.view.source.include_heatmap = False
        if not self.view.source.include_gameflow:
            self.view.source.include_gameflow = True
            corsi = "Corsi" if self.view.source.corsi else "Expected Goals"
            strength = self.view.source.strength
            self.label = _("Gameflow {corsi} {strength}").format(corsi=corsi, strength=strength)
            await self.view.show_page(self.view.current_page, interaction=interaction)
            return
        else:
            lookup = (self.view.source.corsi, self.view.source.strength)
            corsi_bool, strength = mapping[lookup]
            self.view.source.corsi = corsi_bool
            self.view.source.strength = strength
            corsi = "Corsi" if corsi_bool else "Expected Goals"
            self.label = _("Gameflow {corsi} {strength}").format(corsi=corsi, strength=strength)
            await self.view.show_page(self.view.current_page, interaction=interaction)
            return


class HockeySelectGame(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(min_values=1, max_values=1, options=options, placeholder=_("Pick a game"))

    async def callback(self, interaction: discord.Interaction):
        game_id = int(self.values[0])
        await self.view.show_page(0, game_id=game_id, interaction=interaction)


class HockeySelectPlayer(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(
            min_values=1, max_values=1, options=options, placeholder=_("Pick a Player")
        )

    async def callback(self, interaction: discord.Interaction):
        player_id = int(self.values[0])
        player = self.view.source.players.get(player_id)
        index = self.view.source.pages.index(player)
        await self.view.show_page(index, interaction)
