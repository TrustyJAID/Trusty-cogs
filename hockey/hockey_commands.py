import os
from datetime import datetime, timezone
from typing import List, Literal, Optional
from urllib.parse import quote

import aiohttp
import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify

from .abc import HockeyMixin
from .api import GameEventTypeCode
from .constants import BASE_URL, TEAMS
from .helper import (
    DateFinder,
    LeaderboardFinder,
    LeaderboardType,
    PlayerFinder,
    StandingsFinder,
    TeamFinder,
    YearFinder,
)
from .menu import BaseMenu, GamesMenu, LeaderboardPages, PlayerPages, SimplePages
from .player import SearchPlayer
from .schedule import PlayByPlay, Schedule, ScheduleList
from .standings import PlayoffsView, StandingsMenu
from .stats import LeaderCategories, LeaderView

_ = Translator("Hockey", __file__)

log = getLogger("red.trusty-cogs.Hockey")


hockey_commands = HockeyMixin.hockey_commands


class HockeyCommands(HockeyMixin):
    """
    All the commands grouped under `[p]hockey`
    """

    #######################################################################
    # All the basic commands                                              #
    #######################################################################

    @hockey_commands.command()
    async def version(self, ctx: commands.Context) -> None:
        """
        Display the current version
        """
        ret = _("Hockey version ") + self.__version__
        if self._commit:
            ret += f"\n- Commit: [{self._commit[:9]}]({self._repo}/tree/{self._commit})"
        await ctx.send(ret)

    @commands.command()
    async def hockeyhub(self, ctx: commands.Context, *, search: str) -> None:
        """
        Search for hockey related items on https://hockeyhub.github.io/

        lines   team    Team lines on Daily Faceoff
        stats   [year] team Team stats on nhl.com, year optional
        schedule    team    Team schedule on nhl.com
        draft   team oryear Draft history for team or year on Elite Prospects
        cap team orplayer   Cap information for team or player on CapFriendly
        player  player  Search for player on Elite Prospects
        depth   team    Team depth chart on Elite Prospects
        prospects   team    Team prospects on Elite Prospects
        trades  team    Team trade history on NHL Trade Tracker
        jersey  [team] number orname    Find a player by jersey number
        highlights  [team]  Game Highlights, team optional
        reddit  team    Team subreddit on Reddit
        """
        search = quote(search)
        await ctx.send("https://hh.sbstp.ca/?search=" + search)

    @hockey_commands.command(name="role", hidden=True, with_app_command=False)
    @commands.bot_has_permissions(manage_roles=True)
    async def team_role(
        self, ctx: commands.Context, *, team: discord.app_commands.Transform[str, TeamFinder]
    ) -> None:
        """Set your role to a team role"""
        guild = ctx.message.guild
        if not team:
            await ctx.send(_("You must provide a valid current team."))
            return
        msg = ""
        role_name = f"{team}"
        try:
            role = discord.utils.find(lambda r: r.name == role_name, guild.roles)
            if not role or role >= guild.me.top_role:
                msg += _("{role_name} is not an available role!").format(role_name=role_name)
            await ctx.author.add_roles(role[0])
            msg += role[0].name + _(" role applied.")
        except Exception:
            log.error("error adding team role", exc_info=True)
            msg += _("{role_name} is not an available role!").format(role_name=role_name)
        await ctx.send(msg)

    @hockey_commands.command(name="goalsrole", hidden=True, with_app_command=False)
    @commands.bot_has_permissions(manage_roles=True)
    async def team_goals(
        self, ctx: commands.Context, *, team: discord.app_commands.Transform[str, TeamFinder]
    ) -> None:
        """Subscribe to goal notifications"""
        guild = ctx.message.guild
        msg = ""
        role_name = f"{team} GOAL"
        try:
            role = discord.utils.find(lambda r: r.name == role_name, guild.roles)
            if not role or role >= guild.me.top_role:
                msg += _("{role_name} is not an available role!").format(role_name=role_name)
            await ctx.author.add_roles(role[0])
            msg += role[0].name + _(" role applied.")
        except Exception:
            log.error("error adding team role", exc_info=True)
            msg += _("{role_name} is not an available role!").format(role_name=role_name)
        await ctx.send(msg)

    @hockey_commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def standings(self, ctx: commands.Context, *, search: StandingsFinder = None) -> None:
        """
        Displays current standings

        `[search]` If provided you can see a teams complete stats
        by searching for team or get all standings at once
        separated by division
        """
        await ctx.typing()
        try:
            standings = await self.api.get_standings()
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return
        await StandingsMenu(standings=standings, start=search).start(ctx=ctx)

    @hockey_commands.command(aliases=["score"])
    @commands.bot_has_permissions(embed_links=True)
    @discord.app_commands.describe(date="YYYY-MM-DD")
    async def games(
        self,
        ctx: commands.Context,
        date: Optional[discord.app_commands.Transform[datetime, DateFinder]] = None,
        *,
        team: Optional[discord.app_commands.Transform[str, TeamFinder]],
    ) -> None:
        """
        Display information about games.

        `[date]` The date in the form of `YYYY-MM-DD` you want to get.
            - Defaults to the current date.
        `[team]` The team name you want to filter games for.
            - Defaults to all teams.
        """
        await ctx.typing()
        teams = []
        if team is not None:
            teams = [team]
        try:
            await GamesMenu(
                source=Schedule(team=teams, date=date, api=self.api),
                cog=self,
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=180,
            ).start(ctx=ctx)
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return

    @hockey_commands.command(aliases=["pbp"])
    @commands.bot_has_permissions(embed_links=True)
    @discord.app_commands.describe(date="YYYY-MM-DD")
    async def playbyplay(
        self,
        ctx: commands.Context,
        date: Optional[discord.app_commands.Transform[datetime, DateFinder]] = None,
        type_code: Optional[GameEventTypeCode] = None,
        *,
        team: Optional[discord.app_commands.Transform[str, TeamFinder]],
    ) -> None:
        """
        Gets all play-by-play information for any game.

        `[date]` The date in the form of `YYYY-MM-DD` you want to get.
            - Defaults to the current date.
        `[type_code]` The event type you want to filter down.
            - Defaults to all events.
            - Displays only the last events of that type from the game.
        `[team]` The team name you want to filter games for.
            - Defaults to all teams.
        """
        log.debug(type_code)
        await ctx.typing()
        teams = []
        if team is not None:
            teams = [team]
        try:
            await GamesMenu(
                source=PlayByPlay(type_code=type_code, team=teams, date=date, api=self.api),
                cog=self,
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=180,
            ).start(ctx=ctx)
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return

    @hockey_commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def playoffs(
        self,
        ctx: commands.Context,
        season: Optional[YearFinder] = None,
    ) -> None:
        """
        Gets Playoff brackets for a givent season.

        `[season]` Is the year the playoffs happened in.
        Example: `2024` or `2023-2024` for the 2024 Stanley Cup Playoffs.
        """
        await ctx.typing()
        season_str = None
        if season:
            if season.group(3):
                if (int(season.group(3)) - int(season.group(1))) > 1:
                    await ctx.send(_("Dates must be only 1 year apart."))
                    return
                if (int(season.group(3)) - int(season.group(1))) <= 0:
                    await ctx.send(_("Dates must be only 1 year apart."))
                    return
                if int(season.group(1)) > datetime.now().year:
                    await ctx.send(_("Please select a year prior to now."))
                    return
                season_str = int(season.group(3))
            else:
                if int(season.group(1)) > datetime.now().year:
                    await ctx.send(_("Please select a year prior to now."))
                    return
                season_str = int(season.group(1))
        try:
            await PlayoffsView(start_date=season_str, api=self.api).start(ctx=ctx)
        except Exception:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return

    @hockey_commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def heatmap(
        self,
        ctx: commands.Context,
        style: Literal["all", "ev", "5v5", "sva", "home5v4", "away5v4"] = "all",
        date: Optional[discord.app_commands.Transform[datetime, DateFinder]] = None,
        *,
        team: Optional[discord.app_commands.Transform[str, TeamFinder]],
    ) -> None:
        """
        Display game heatmaps.

        `[style]` must be one of `all`, `ev`, `5v5`, `sva`, `home5v4`, or `away5v4`
            - Defaults to all.
        `[date]` The date in the form of `YYYY-MM-DD` you want to get.
            - Defaults to the current date.
        `[team]` The team name you want to filter games for.
            - Defaults to all teams.
        """
        await ctx.typing()
        styles = ["all", "ev", "5v5", "sva", "home5v4", "away5v4"]
        if style not in styles:
            await ctx.send(
                _("Style must be one of {styles}.").format(styles=humanize_list(styles))
            )
            return
        teams = []
        if team is not None:
            teams = [team]
        try:
            await GamesMenu(
                source=Schedule(
                    team=teams,
                    date=date,
                    include_goals=False,
                    include_heatmap=True,
                    style=style,
                    api=self.api,
                ),
                cog=self,
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=180,
            ).start(ctx=ctx)
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return

    @hockey_commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def gameflow(
        self,
        ctx: commands.Context,
        strength: Literal["all", "ev", "5v5", "sva"] = "all",
        corsi: bool = True,
        date: Optional[discord.app_commands.Transform[datetime, DateFinder]] = None,
        *,
        team: Optional[discord.app_commands.Transform[str, TeamFinder]],
    ) -> None:
        """
        Display games gameflow.

        `[strength]` must be one of "all", "ev", "5v5", or "sva".
            - Defaults to `all`.
        `[corsi]` either true or false.
            - Defaults to `true`.
        `[date]` The date in the form of `YYYY-MM-DD` you want to get.
            - Defaults to the current date.
        `[team]` The team name you want to filter games for.
            - Defaults to all teams.
        """
        await ctx.typing()
        styles = ["all", "ev", "5v5", "sva"]
        if strength not in styles:
            await ctx.send(
                _("Style must be one of {styles}.").format(styles=humanize_list(styles))
            )
            return
        teams = []
        if team is not None:
            teams = [team]
        try:
            await GamesMenu(
                source=Schedule(
                    team=teams,
                    date=date,
                    include_goals=False,
                    include_gameflow=True,
                    corsi=corsi,
                    strength=strength,
                    api=self.api,
                ),
                cog=self,
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=180,
            ).start(ctx=ctx)
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return

    @hockey_commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def schedule(
        self,
        ctx: commands.Context,
        date: Optional[discord.app_commands.Transform[datetime, DateFinder]],
        *,
        team: Optional[discord.app_commands.Transform[str, TeamFinder]],
    ) -> None:
        """
        Gets upcoming NHL games for the current season as a list.

        `[date]` The date in the form of `YYYY-MM-DD` you want to get.
            - Defaults to the current date.
        `[team]` The team name you want to filter games for.
            - Defaults to all teams.
        """
        await ctx.typing()
        teams = []
        if team is not None:
            teams = [team]
        try:
            await GamesMenu(
                source=ScheduleList(team=teams, date=date, api=self.api),
                cog=self,
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=180,
            ).start(ctx=ctx)
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return

    @hockey_commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def recap(
        self,
        ctx: commands.Context,
        date: Optional[discord.app_commands.Transform[datetime, DateFinder]],
        *,
        team: Optional[discord.app_commands.Transform[str, TeamFinder]],
    ) -> None:
        """
        Gets NHL games and their game recap links

        `[date]` The date in the form of `YYYY-MM-DD` you want to get.
            - Defaults to the current date.
        `[team]` The team name you want to filter games for.
            - Defaults to all teams.
        """
        await ctx.typing()
        teams = []
        if team is not None:
            teams = [team]
        try:
            await GamesMenu(
                source=ScheduleList(team=teams, date=date, get_recap=True, api=self.api),
                cog=self,
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=180,
            ).start(ctx=ctx)
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return

    @hockey_commands.command(hidden=True, with_app_command=False)
    @commands.bot_has_permissions(embed_links=True)
    async def season(
        self,
        ctx: commands.Context,
        team: discord.app_commands.Transform[str, TeamFinder],
        season: str = None,
    ) -> None:
        """
        Gets all upcoming NHL games for the current season for one team.

        `<team>` The name of the teams season schedule you want to post.
        `[season]` must be YYYYYYYY format. e.g. 20212022.
        """
        await ctx.typing()
        if season is None:
            season = f"{datetime.now().year}{datetime.now().year+1}"
        if "-" in season:
            start, end = season.split("-")
            season = f"{start}{end}"
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(
                _("Posting {team}'s season schedule for {season}.").format(
                    team=team, season=season
                ),
                ephemeral=True,
            )
        url = f"{BASE_URL}/api/v1/schedule?season={season}"
        url += "&teamId=" + ",".join([str(TEAMS[team]["id"])])
        log.verbose("season team: %s", team)
        log.verbose("season team id: %s", TEAMS[team]["id"])
        log.verbose("season team url: %s", url)
        try:
            async with self.session.get(url) as resp:
                data = await resp.json()
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return
        games = [game for date in data["dates"] for game in date["games"]]
        msg = ""
        for game in games:
            game_start = datetime.strptime(game["gameDate"], "%Y-%m-%dT%H:%M:%SZ")
            game_start = game_start.replace(tzinfo=timezone.utc)
            home_team = game["teams"]["home"]["team"]["name"]
            away_team = game["teams"]["away"]["team"]["name"]
            home_emoji = "<:" + TEAMS[home_team]["emoji"] + ">"
            away_emoji = "<:" + TEAMS[away_team]["emoji"] + ">"
            date_str = f"<t:{int(game_start.timestamp())}:d>"
            time_str = f"<t:{int(game_start.timestamp())}:t>"
            msg += f"{date_str} - {away_emoji} @ " f"{home_emoji} - {time_str}\n"
        for page in pagify(msg):
            await ctx.channel.send(page)
            break
        # x = list(pagify(msg))
        # await ctx.send(str(len(x)))
        # await ctx.send(x[0])

    @hockey_commands.command(aliases=["players"])
    @commands.bot_has_permissions(embed_links=True)
    async def player(
        self,
        ctx: commands.Context,
        season: Optional[YearFinder],
        include_headshot: Optional[bool],
        *,
        player: discord.app_commands.Transform[List[SearchPlayer], PlayerFinder],
    ) -> None:
        """
        Lookup information about a specific player

        `[season]` The season to get stats data on format can be `YYYY` or `YYYYYYYY`
        `<player>` The name of the player to search for
        """
        await ctx.typing()
        season_str = None
        if season:
            if season.group(3):
                if (int(season.group(3)) - int(season.group(1))) > 1:
                    await ctx.send(_("Dates must be only 1 year apart."))
                    return
                if (int(season.group(3)) - int(season.group(1))) <= 0:
                    await ctx.send(_("Dates must be only 1 year apart."))
                    return
                if int(season.group(1)) > datetime.now().year:
                    await ctx.send(_("Please select a year prior to now."))
                    return
                season_str = f"{season.group(1)}{season.group(3)}"
            else:
                if int(season.group(1)) > datetime.now().year:
                    await ctx.send(_("Please select a year prior to now."))
                    return
                year = int(season.group(1)) + 1
                season_str = f"{season.group(1)}{year}"

        if not player:
            await ctx.send(_("No player could be found by that name."))
            return
        if include_headshot is None and isinstance(ctx.author, discord.Member):
            include_headshot = not ctx.author.is_on_mobile()
        try:
            await BaseMenu(
                source=PlayerPages(
                    pages=player,
                    season=season_str,
                    include_headshot=include_headshot,
                ),
                cog=self,
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=180,
            ).start(ctx=ctx)
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return

    @hockey_commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def roster(
        self,
        ctx: commands.Context,
        season: Optional[YearFinder],
        *,
        team: discord.app_commands.Transform[str, TeamFinder],
    ) -> None:
        """
        Get a teams roster

        `[season]` The season to get stats data on format can be `YYYY` or `YYYYYYYY`
        `<team>` The name of the team to search for
        """
        await ctx.typing()
        season_str = None
        if season:
            if season.group(3):
                if (int(season.group(3)) - int(season.group(1))) > 1:
                    await ctx.send(_("Dates must be only 1 year apart."))
                    return
                if (int(season.group(3)) - int(season.group(1))) <= 0:
                    await ctx.send(_("Dates must be only 1 year apart."))
                    return
                if int(season.group(1)) > datetime.now().year:
                    await ctx.send(_("Please select a year prior to now."))
                    return
                season_str = f"{season.group(1)}{season.group(3)}"
            else:
                if int(season.group(1)) > datetime.now().year:
                    await ctx.send(_("Please select a year prior to now."))
                    return
                year = int(season.group(1)) + 1
                season_str = f"{season.group(1)}{year}"
        if team is None:
            await ctx.send(_("You must provide a valid current team."))
            return
        roster = await self.api.get_roster(team=team, season=season_str)
        if roster.players:
            await BaseMenu(
                source=PlayerPages(pages=roster.players, season=season_str),
                cog=self,
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=180,
            ).start(ctx=ctx)
        else:
            if season:
                year = _(" in the {season} season").format(
                    season=f"{season.group(1)}-{season.group(3)}"
                )
            else:
                year = ""
            await ctx.send(
                _("I could not find a roster for the {team}{year}.").format(team=team, year=year)
            )

    @hockey_commands.command(name="stats")
    async def hockey_stats(
        self,
        ctx: commands.Context,
        category: Optional[LeaderCategories],
        season: Optional[str],
        limit: Optional[int] = 10,
    ):
        """
        Display Leader categories

        `[season]` must be `YYYY-YYYY` formatted.
        `[limit=10]` is the limit of the number of players to show.
        `[category]` Must be one of the following (default is goals):
            goals
            assists
            savePct
            shutouts
            wins
            gaa
            plusMinus
            points
            powerPlayGoals
            shortHandedGoals
            timeOnIcePerGame
            faceOffPct
            otLosses
            losses
            shortHandedAssists
            pointsPerGame
            powerPlayPoints
            shootingPctg
            hits
            shortHandedPoints
            penaltyMinutes
            shots
            powerPlayAssists
            gameWinningGoals
        """
        await ctx.typing()
        if category is None:
            category = LeaderCategories("goals")
        if season is not None:
            new_season = season.replace("-", "")
            if not new_season.isdigit() and len(new_season) != 8:
                await ctx.send(f"`{season}` is not a valid season.", ephemeral=True)
                return
        try:
            view = LeaderView(category, season, limit, self.session)
            await view.start(ctx)
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return

    @hockey_commands.command(hidden=True, with_app_command=False)
    @commands.mod_or_permissions(manage_messages=True)
    async def rules(self, ctx: commands.Context) -> None:
        """
        Display a nice embed of server specific rules
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        if not ctx.channel.permissions_for(ctx.guild.me).embed_links:
            return
        rules = await self.config.guild(ctx.guild).rules()
        team = await self.config.guild(ctx.guild).team_rules()
        if rules == "":
            return
        em = await self.make_rules_embed(ctx.guild, team, rules)
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await ctx.message.delete()
        await ctx.send(embed=em)

    @staticmethod
    async def make_rules_embed(guild: discord.Guild, team: str, rules: str) -> discord.Embed:
        """
        Builds the rule embed for the server
        """
        warning = _(
            "***Violating [Discord Terms of Service](https://discordapp.com/terms) "
            "or [Community Guidelines](https://discordapp.com/guidelines) will "
            "result in an immediate ban. You may also be reported to Discord.***"
        )
        em = discord.Embed(colour=int(TEAMS[team]["home"].replace("#", ""), 16))
        em.description = rules
        em.title = _("__RULES__")
        em.add_field(name=_("__**WARNING**__"), value=warning)
        em.set_thumbnail(url=str(guild.icon))
        em.set_author(name=guild.name, icon_url=str(guild.icon))
        return em

    async def post_leaderboard(
        self,
        ctx: commands.Context,
        leaderboard_type: LeaderboardType,
        ephemeral: bool = False,
    ) -> None:
        """
        Posts the leaderboard based on specific style
        """
        guild = ctx.guild
        if guild is None:
            return

        if leaderboard_type.is_last_week():
            leaderboard = await self.pickems_config.guild(guild).last_week_leaderboard()
        else:
            leaderboard = await self.pickems_config.guild(guild).leaderboard()
        if not leaderboard:
            await ctx.send(_("There is no current leaderboard for this server!"))
            return

        if not leaderboard_type.is_worst():
            leaderboard = sorted(
                leaderboard.items(), key=lambda i: i[1][leaderboard_type.key()], reverse=True
            )
        else:
            leaderboard = sorted(
                leaderboard.items(),
                key=lambda i: i[1][leaderboard_type.total_key()] - i[1][leaderboard_type.key()],
                reverse=True,
            )
        msg_list = []
        count = 1
        user_position = None
        position = ""

        for member_id, data in leaderboard:
            if str(member_id) == str(ctx.author.id):
                user_position = leaderboard.index((member_id, data))
            member = guild.get_member(int(member_id))
            if member is None:
                member_mention = _("User has left the server {member_id}").format(
                    member_id=member_id
                )
            else:
                member_mention = member.mention
            if leaderboard_type.is_weekly():  # in [2, 4, 6, 7, 8, 9]:
                points = data.get(leaderboard_type.key(), 0)
                if not points:
                    continue
                msg_list.append(f"{count}. {member_mention}: {points}\n")
            elif leaderboard_type.is_standard():  # .value in [1, 3, 5]:
                total = data.get(leaderboard_type.total_key(), 0)
                wins = data.get(leaderboard_type.key(), 0)
                if not total:
                    continue
                try:
                    percent = (wins / total) * 100
                except ZeroDivisionError:
                    percent = 0.0
                verb = _("correct")
                msg_list.append(
                    f"{count}. {member_mention}: {wins}/{total} {verb} ({percent:.4}%)\n"
                )
            elif leaderboard_type.is_worst():
                wins = data.get(leaderboard_type.key(), 0)
                total = data.get(leaderboard_type.total_key(), 0)
                losses = total - wins
                if not losses:
                    continue
                try:
                    percent = (losses / total) * 100
                except ZeroDivisionError:
                    percent = 0.0
                verb = _("incorrect")
                msg_list.append(
                    f"{count}. {member_mention}: {losses}/{total} {verb} ({percent:.4}%)\n"
                )
            count += 1
        leaderboard_list = [msg_list[i : i + 10] for i in range(0, len(msg_list), 10)]
        if user_position is not None:
            user = leaderboard[user_position][1]
            wins = user.get(leaderboard_type.key(), 0)
            total = user.get(leaderboard_type.total_key(), 0)
            losses = total - wins
            if (not leaderboard_type.is_weekly() and total) or (
                leaderboard_type.is_weekly() and wins
            ):
                position = _(
                    "{member}, you're #{number} on the {leaderboard_type} leaderboard!\n"
                ).format(
                    member=ctx.author.display_name,
                    number=user_position + 1,
                    leaderboard_type=leaderboard_type.as_str(),
                )
            if leaderboard_type.is_standard():
                try:
                    percent = (wins / total) * 100
                except ZeroDivisionError:
                    percent = 0.0
                position += _("You have {wins}/{total} correct ({percent:.4}%).").format(
                    wins=wins, total=total, percent=percent
                )
            elif leaderboard_type is LeaderboardType.worst:
                try:
                    percent = (losses / total) * 100
                except ZeroDivisionError:
                    percent = 0.0
                position += _("You have {wins}/{total} incorrect ({percent:.4}%).").format(
                    wins=wins, total=total, percent=percent
                )
        if not leaderboard_list:
            await ctx.send(
                _("No data could be found in the {style} leaderboard.").format(
                    style=leaderboard_type.as_str()
                )
            )
            return
        if ctx.assume_yes:
            em = discord.Embed(timestamp=datetime.now())
            description = ""
            for msg in leaderboard_list[0]:
                description += msg
            em.description = description
            em.set_author(
                name=_("{guild} Pickems {style} Leaderboard").format(
                    guild=guild.name, style=leaderboard_type.as_str()
                ),
                icon_url=guild.icon,
            )
            em.set_thumbnail(url=guild.icon)
            await ctx.send(embed=em)
            return

        await BaseMenu(
            source=LeaderboardPages(pages=leaderboard_list, style=leaderboard_type),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=180,
        ).start(ctx=ctx, content=position, ephemeral=ephemeral)

    @hockey_commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(add_reactions=True)
    async def leaderboard(
        self,
        ctx: commands.Context,
        public: Optional[bool] = True,
        *,
        leaderboard_type: Optional[
            discord.app_commands.Transform[LeaderboardType, LeaderboardFinder]
        ],
    ) -> None:
        """
        Shows the current server leaderboard

        `[leaderboard_type]` can be any of the following:
        `season` (the default)
        `weekly`
        `playoffs`
        `playoffs weekly`
        `pre-season`
        `pre-season weekly`
        `worst`

        Leaderboards % is calculated based on cumulative votes compared to number of votes.
        This is so that one lucky user who only votes once isn't considered *better*
        than people who consistently vote. The only way to win is to keep playing
        and picking correctly.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing(ephemeral=not public)
        if leaderboard_type is None:
            leaderboard_type = LeaderboardType(3)
        await self.post_leaderboard(ctx, leaderboard_type, not public)

    @hockey_commands.command(aliases=["pickemvotes", "pickemvote"])
    @commands.guild_only()
    @commands.bot_has_permissions(add_reactions=True)
    async def pickemsvotes(self, ctx: commands.Context, public: Optional[bool] = False):
        """
        View your current pickems votes for the server.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing(ephemeral=not public)
        if str(ctx.guild.id) not in self.all_pickems:
            msg = _("This server does not have any pickems setup.")
            await ctx.send(msg)
            return
        msg = _("You have voted on the following games:\n")
        for game_id, pickem in self.all_pickems[str(ctx.guild.id)].items():
            if str(ctx.author.id) in pickem.votes:
                vote = pickem.votes[str(ctx.author.id)]
                timestamp = int(pickem.game_start.timestamp())
                time_str = f"<t:{timestamp}:F>"
                msg += f"{pickem.away_team} @ {pickem.home_team} {time_str} - {vote}\n"
        msgs = []
        for page in pagify(msg):
            if ctx.channel.permissions_for(ctx.me).embed_links:
                em = discord.Embed(
                    title=_("Pickems votes in {guild}").format(guild=ctx.guild.name),
                    description=page,
                )
                msgs.append(em)
            else:
                msgs.append(page)
        await BaseMenu(source=SimplePages(msgs)).start(ctx=ctx, ephemeral=not public)

    @hockey_commands.command(hidden=True, with_app_command=False)
    @commands.mod_or_permissions(manage_messages=True)
    async def setrules(
        self,
        ctx: commands.Context,
        team: discord.app_commands.Transform[str, TeamFinder],
        *,
        rules,
    ) -> None:
        """Set the main rules page for the nhl rules command"""
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if not team:
            await ctx.send(_("You must provide a valid current team."))
            return
        team = team[0]
        if not ctx.channel.permissions_for(ctx.guild.me).embed_links:
            await ctx.send(_("I don't have embed links permission!"))
            return
        await self.config.guild(ctx.guild).rules.set(rules)
        await self.config.guild(ctx.guild).team_rules.set(team)
        em = await self.make_rules_embed(ctx.guild, team, rules)
        await ctx.send(_("Done, here's how it will look."), embed=em)

    @hockey_commands.command(aliases=["link", "invite"])
    async def otherdiscords(
        self, ctx: commands.Context, team: discord.app_commands.Transform[str, TeamFinder]
    ) -> None:
        """
        Get team specific discord links

        choosing all will create a nicely formatted list of
        all current NHL team discord server links
        """
        await ctx.typing(ephemeral=True)
        if team is None:
            msg = _("You must provide a valid current team.")
            await ctx.send(msg)
        if "all" not in team.lower():
            invites = ""
            if team in TEAMS:
                invites += TEAMS[team]["invite"] + "\n"
            else:
                await ctx.send(_("You must provide a valid current team."))
                return
            await ctx.send(
                _("Here is the {team} server invite link:\n{link}").format(team=team, link=invites)
            )
            # await ctx.channel.send(invites)
        else:
            if not ctx.channel.permissions_for(ctx.author).manage_messages:
                # Don't need everyone spamming this command
                await ctx.send(_("You are not authorized to use this command."), ephemeral=True)
                return
            atlantic = [
                team
                for team in TEAMS
                if TEAMS[team]["division"] == "Atlantic" and TEAMS[team]["active"]
            ]
            metropolitan = [
                team
                for team in TEAMS
                if TEAMS[team]["division"] == "Metropolitan" and TEAMS[team]["active"]
            ]
            central = [
                team
                for team in TEAMS
                if TEAMS[team]["division"] == "Central" and TEAMS[team]["active"]
            ]
            pacific = [
                team
                for team in TEAMS
                if TEAMS[team]["division"] == "Pacific" and TEAMS[team]["active"]
            ]
            team_list = {
                "Atlantic": atlantic,
                "Metropolitan": metropolitan,
                "Central": central,
                "Pacific": pacific,
            }
            msg1 = _(
                "# Hockey Discord Master List\n"
                "- Do not join other discords to troll.\n- "
                "Respect their rules & their members "
                "(Yes even the leafs & habs unfortunately).\n- "
                "We don't control the servers below. "
                "If you get banned we can not get you unbanned.\n- "
                "Don't be an asshole because then we all look like assholes. "
                "They won't see it as one asshole "
                "fan they will see it as a toxic fanbase.\n- "
                "Salt levels may vary. Your team is the best "
                "here but don't go on another discord and preach "
                "it to an angry mob after we just won.\n- "
                "Not following the above rules will result in "
                "appropriate punishments ranging from a warning "
                "to a ban. \n\nhttps://discord.gg/reddithockey\n"  # r/hockey
                "https://discord.gg/rishockey\n"  # r/ishockey
                # "https://discord.gg/c3Q7Fq4T\n" # SDPN
                "https://discord.gg/thehockeyguy\n"  # THG
                "https://discord.gg/P3aFDDXqym\n"  # PWHL
            )
            await ctx.channel.send(msg1)
            for division in team_list:
                msg = "# {div} DIVISION".format(div=division.upper())
                await ctx.channel.send(msg)
                for team in team_list[division]:
                    team_emoji = discord.PartialEmoji.from_str(TEAMS[team]["emoji"])
                    team_link = TEAMS[team]["invite"]
                    msg = "## {emoji} {link} {emoji}".format(emoji=team_emoji, link=team_link)
                    await ctx.channel.send(msg)
            if ctx.interaction:
                await ctx.send(_("Done."))

    async def get_image(self, file_name: str, url: str) -> discord.File:
        path = cog_data_path(self) / file_name
        if not os.path.exists(path):
            async with self.session.get(url) as resp:
                data = await resp.read()
            with path.open("wb") as outfile:
                outfile.write(data)
        return discord.File(path, filename=file_name)
