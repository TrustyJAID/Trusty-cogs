import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Literal, Optional, Union

import discord
from discord import app_commands
from discord.app_commands import Choice
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator

from .abc import MixinMeta
from .constants import TEAMS
from .helper import DATE_RE

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


class DateTransformer(app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> datetime:
        find = DATE_RE.search(value)
        date_str = f"{find.group(1)}-{find.group(3)}-{find.group(4)}"
        return datetime.strptime(date_str, "%Y-%m-%d")


def guild_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        allowed = interaction.guild is not None
        if not allowed:
            await interaction.response.send_message(
                _("This command is not available outside of a guild."), ephemeral=True
            )
        return allowed

    return app_commands.check(predicate)


class HockeySlash(MixinMeta):

    pickems_slash = app_commands.Group(
        name="pickems", description="Manage Hockey Pickems settings"
    )
    gdt_slash = app_commands.Group(name="gdt", description="Manage Hockey Game Day Threads")
    set_slash = app_commands.Group(name="set", description="Setup goal updates, standings, etc.")

    VALID_STANDINGS = Literal[
        "all",
        "conference",
        "western",
        "eastern",
        "division",
        "central",
        "metropolitan",
        "atlantic",
        "pacific",
    ]

    HOCKEY_STATES = Literal["Preview", "Live", "Final", "Goal", "Periodrecap"]

    #######################################################################
    # Where parsing of slash commands happens                             #
    #######################################################################

    @app_commands.command(name="standings")
    async def standings_slash(self, interaction: discord.Interaction, search: VALID_STANDINGS):
        """Display current standings"""

        await self.standings(interaction, search=search)

    @app_commands.command(name="games")
    @app_commands.describe(team="A valid NHL team", date="YYYY-MM-DD format")
    async def games_slash(
        self,
        interaction: discord.Interaction,
        team: Optional[str],
        date: Optional[app_commands.Transform[str, DateTransformer]],
    ):
        """Gets all NHL games"""

        teams_and_date = {}
        if team:
            teams_and_date["team"] = [team]
        if date:
            teams_and_date["date"] = date
        await self.games(interaction, teams_and_date=teams_and_date)

    @app_commands.command(name="heatmap")
    @app_commands.describe(team="A valid NHL team", date="YYYY-MM-DD format")
    async def heatmap_slash(
        self,
        interaction: discord.Interaction,
        style: Literal["all", "ev", "5v5", "sva", "home5v4", "away5v4"],
        team: Optional[str],
        date: Optional[app_commands.Transform[str, DateTransformer]],
    ):
        """Display game heatmaps."""

        teams_and_date = {}
        if team:
            teams_and_date["team"] = [team]
        if date:
            teams_and_date["date"] = date
        await self.heatmap(interaction, style, teams_and_date=teams_and_date)

    @app_commands.command(name="gameflow")
    @app_commands.describe(team="A valid NHL team", date="YYYY-MM-DD format")
    async def gameflow_slash(
        self,
        interaction: discord.Interaction,
        strength: Literal["all", "ev", "5v5", "sva"],
        team: Optional[str],
        date: Optional[app_commands.Transform[str, DateTransformer]],
        corsi: Optional[bool] = True,
    ):
        """Display games gameflow."""

        teams_and_date = {}
        if team:
            teams_and_date["team"] = [team]
        if date:
            teams_and_date["date"] = date
        await self.gameflow(interaction, strength, corsi, teams_and_date=teams_and_date)

    @app_commands.command(name="schedule")
    async def schedule_slash(
        self,
        interaction: discord.Interaction,
        team: Optional[str],
        date: Optional[app_commands.Transform[str, DateTransformer]],
    ):
        """Gets upcoming NHL games for the current season as a list"""

        teams_and_date = {}
        if team:
            teams_and_date["team"] = [team]
        if date:
            teams_and_date["date"] = date
        await self.schedule(interaction, teams_and_date=teams_and_date)

    @app_commands.command(name="player")
    @app_commands.describe(player="The name of the player", year="YYYY or YYYYYYYY formatted date")
    async def player_slash(
        self, interaction: discord.Interaction, player: str, year: Optional[int]
    ):
        """Lookup information about a specific player"""

        search = str(player)
        if year:
            search += f" {year}"
        await self.player(interaction, search=search)

    @app_commands.command(name="roster")
    async def roster_slash(
        self, interaction: discord.Interaction, team: str, season: Optional[int]
    ):
        """Get a team roster"""

        await self.roster(season, search=team)

    @app_commands.command(name="leaderboard")
    async def leaderboard_slash(
        self,
        interaction: discord.Interaction,
        leaderboard_type: Optional[
            Literal[
                "season",
                "weekly",
                "playoffs",
                "playoffs_weekly",
                "pre-season",
                "pre-season_weekly",
                "worst",
            ]
        ],
    ):
        """Shows the current server leaderboard"""

        await self.leaderboard(interaction, leaderboard_type)

    @app_commands.command(name="pickemsvotes")
    async def pickemsvotes_slash(self, interaction: discord.Interaction):
        """View your current pickems votes for the server"""

        await self.pickemsvotes(interaction)

    @app_commands.command(name="otherdiscords")
    async def otherdiscords_slash(self, interaction: discord.Interaction, team: str):
        """Get team specific discord links"""

        await self.otherdiscords(interaction, team)

    @pickems_slash.command(name="settings")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def pickems_settings_slash(self, interaction: discord.Interaction):
        """Show the servers current pickems settings"""
        func = self.pickems_settings
        await func(interaction)

    @pickems_slash.command(name="message")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def set_pickems_message_slash(
        self, interaction: discord.Interaction, message: Optional[str]
    ):
        """Customize the pickems message for this server"""
        func = self.set_pickems_message
        await func(interaction, message=message)

    @pickems_slash.command(name="setup")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def setup_auto_pickems_slash(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel]
    ):
        """Sets up pickems threads created every day"""
        func = self.setup_auto_pickems
        await func(interaction, channel)

    @pickems_slash.command(name="clear")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def delete_auto_pickems_slash(self, interaction: discord.Interaction):
        """Stop posting new pickems threads and clear existing list of pickems threads"""
        func = self.delete_auto_pickems
        await func(interaction)

    @pickems_slash.command(name="page")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def pickems_page_slash(
        self,
        interaction: discord.Interaction,
        date: Optional[app_commands.Transform[str, DateTransformer]],
    ):
        """Generates a pickems page for voting on"""
        func = self.pickems_page
        await func(interaction, date)

    @gdt_slash.command(name="settings")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def gdt_settings_slash(self, interaction: discord.Interaction):
        """Shows the current Game Day Thread settings"""
        func = self.gdt_settings
        await func(interaction)

    @gdt_slash.command(name="delete")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def gdt_delete_slash(self, interaction: discord.Interaction):
        """Delete all current game day threads for the server"""
        func = self.gdt_delete
        await func(interaction)

    @gdt_slash.command(name="stateupdates")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def gdt_default_game_state_slash(
        self,
        interaction: discord.Interaction,
        state: HOCKEY_STATES,
    ):
        """Set specific state updates to use for game day threads"""
        func = self.gdt_default_game_state
        await func(interaction, state)

    @gdt_slash.command(name="updates")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def gdt_update_start_slash(self, interaction: discord.Interaction, update_start: bool):
        """Set whether or not the starting thread message will update as the game progresses."""
        func = self.gdt_update_start
        await func(interaction, update_start)

    @gdt_slash.command(name="create")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def gdt_create_slash(self, interaction: discord.Interaction):
        """Creates the next gdt for the server"""
        func = self.gdt_create
        await func(interaction)

    @gdt_slash.command(name="toggle")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def gdt_toggle_slash(self, interaction: discord.Interaction):
        """Toggles the game day channel creation on this server"""
        func = self.gdt_toggle
        await func(interaction)

    @gdt_slash.command(name="channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def gdt_channel_slash(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Change the channel used for game day threads."""
        func = self.gdt_channel
        await func(interaction, channel)

    @gdt_slash.command(name="setup")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def gdt_setup_slash(
        self, interaction: discord.Interaction, team: str, channel: Optional[discord.TextChannel]
    ):
        """Setup game day threads for a single (or all) teams."""
        func = self.gdt_setup
        await func(interaction, team, channel)

    @set_slash.command(name="settings")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def hockey_settings_slash(self, interaction: discord.Interaction):
        """Show hockey settings for this server"""
        func = self.hockey_settings
        await func(interaction)

    @set_slash.command(name="poststandings")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def post_standings_slash(
        self,
        interaction: discord.Interaction,
        standings_type: VALID_STANDINGS,
        channel: Optional[discord.TextChannel],
    ):
        """Post automatic standings when all games for the day are done"""
        func = self.post_standings
        await func(interaction, standings_type, channel)

    @set_slash.command(name="stateupdates")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def set_game_state_updates(
        self, interaction: discord.Interaction, channel: discord.TextChannel, state: HOCKEY_STATES
    ):
        """Toggle specific updates in a designated channel"""
        func = self.set_game_state_updates
        await func(interaction, channel, state)

    @set_slash.command(name="add")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def add_goals_slash(
        self, interaction: discord.Interaction, team: str, channel: Optional[discord.TextChannel]
    ):
        """Add a teams goal updates to a channel"""
        func = self.add_goals
        await func(interaction, team, channel)

    @set_slash.command(name="remove")
    @app_commands.checks.has_permissions(manage_channels=True)
    @guild_only()
    async def remove_goals_slash(
        self,
        interaction: discord.Interaction,
        team: Optional[str],
        channel: Optional[discord.TextChannel],
    ):
        """Removes a teams goal updates from a channel"""
        func = self.remove_goals
        await func(interaction, team, channel)

    @games_slash.autocomplete("team")
    @heatmap_slash.autocomplete("team")
    @gameflow_slash.autocomplete("team")
    @roster_slash.autocomplete("team")
    @otherdiscords_slash.autocomplete("team")
    @gdt_setup_slash.autocomplete("team")
    @add_goals_slash.autocomplete("team")
    @remove_goals_slash.autocomplete("team")
    async def active_team_autocomplete(self, interaction: discord.Interaction, current: str):
        """Represents active team names for autocomplete purposes"""
        team_choices = []
        include_all = interaction.command.name in ["setup", "add"]
        include_inactive = interaction.command.name in ["roster"]
        ret = []
        for t, d in TEAMS.items():
            team_choices.append(app_commands.Choice(name=t, value=t))
        if include_all:
            team_choices.insert(0, app_commands.Choice(name="All", value="all"))
        for choice in team_choices:
            if not include_inactive and not TEAMS.get(choice.name, {"active": True})["active"]:
                continue
            if current.lower() in choice.name.lower():
                ret.append(choice)
        return ret[:25]

    @player_slash.autocomplete("player")
    async def player_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice]:
        now = datetime.utcnow()
        saved = datetime.fromtimestamp(await self.config.player_db())
        path = cog_data_path(self) / "players.json"
        ret = []
        if (now - saved) > timedelta(days=1) or not path.exists():
            async with self.session.get(
                "https://records.nhl.com/site/api/player?include=id&include=fullName&include=onRoster"
            ) as resp:
                with path.open(encoding="utf-8", mode="w") as f:
                    json.dump(await resp.json(), f)
            await self.config.player_db.set(int(now.timestamp()))
        with path.open(encoding="utf-8", mode="r") as f:
            data = json.loads(f.read())["data"]
            for player in data:
                if current.lower() in player["fullName"].lower():
                    ret.append(Choice(name=player["fullName"], value=player["fullName"]))
        return ret[:25]

    async def on_error(
        self, interaction: discord.Interaction, command: discord.app_commands.Command, error
    ):
        if isinstance(error, discord.app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message(error, ephemeral=True)
                return
        await interaction.client.tree.on_error(interaction, command, error)
        log.exception(error)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await self.bot.allowed_by_whitelist_blacklist(interaction.user):
            await interaction.response.send_message(
                _("You are not allowed to run this command here."), ephemeral=True
            )
            return False
        fake_ctx = discord.Object(id=interaction.id)
        fake_ctx.author = interaction.user
        fake_ctx.guild = interaction.guild
        if isinstance(interaction.channel, discord.channel.PartialMessageable):
            channel = interaction.user.dm_channel or await interaction.user.create_dm()
        else:
            channel = interaction.channel

        fake_ctx.channel = channel
        if not await self.bot.ignored_channel_or_guild(fake_ctx):
            await interaction.response.send_message(
                _("Commands are not allowed in this channel or guild."), ephemeral=True
            )
            return False
        return True
