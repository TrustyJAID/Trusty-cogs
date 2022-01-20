import json
import logging
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, List, Literal, Optional, Tuple, Union
from urllib.parse import quote

import discord
from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import humanize_list, pagify

from .abc import MixinMeta
from .constants import BASE_URL, TEAMS
from .helper import YEAR_RE, HockeyStandings, HockeyTeams, TeamDateFinder, YearFinder
from .menu import (
    BaseMenu,
    ConferenceStandingsPages,
    DivisionStandingsPages,
    GamesMenu,
    LeaderboardPages,
    PlayerPages,
    SimplePages,
    StandingsPages,
    TeamStandingsPages,
)
from .schedule import Schedule, ScheduleList
from .standings import Standings

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


class HockeyCommands(MixinMeta):
    """
    All the commands grouped under `[p]hockey`
    """

    #######################################################################
    # All the basic commands                                              #
    #######################################################################

    @commands.group(name="hockey", aliases=["nhl"])
    async def hockey_commands(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Get information from NHL.com
        """
        pass

    @hockey_commands.command()
    async def version(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Display the current version
        """
        await ctx.send(_("Hockey version ") + self.__version__)

    @commands.command()
    async def hockeyhub(
        self, ctx: Union[commands.Context, discord.Interaction], *, search: str
    ) -> None:
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

    @hockey_commands.command(name="role")
    @commands.bot_has_permissions(manage_roles=True)
    async def team_role(
        self, ctx: Union[commands.Context, discord.Interaction], *, team: HockeyTeams
    ) -> None:
        """Set your role to a team role"""
        guild = ctx.message.guild
        if team is None:
            await ctx.send(_("You must provide a valid current team."))
            return
        try:
            role = [
                role
                for role in guild.roles
                if (team.lower() in role.name.lower() and "GOAL" not in role.name)
            ]
            if role[0] >= guild.me.top_role:
                return
            await ctx.author.add_roles(role[0])
            await ctx.send(role[0].name + _(" role applied."))
        except Exception:
            log.error("error adding team role", exc_info=True)
            await ctx.send(team + _(" is not an available role!"))

    @hockey_commands.command(name="goalsrole")
    async def team_goals(
        self, ctx: Union[commands.Context, discord.Interaction], *, team: HockeyTeams = None
    ) -> None:
        """Subscribe to goal notifications"""
        guild = ctx.message.guild
        member = ctx.message.author
        if not guild.me.guild_permissions.manage_roles:
            return
        if team is None:
            team_roles = []
            for role in guild.roles:
                if role.name in [r.name + " GOAL" for r in member.roles]:
                    team_roles.append(role)
            if team_roles != []:
                for role in team_roles:
                    if role[0] >= guild.me.top_role:
                        continue
                    await ctx.message.author.add_roles(role)
                role_list = ", ".join(r.name for r in team_roles)
                await ctx.message.channel.send(f"{role_list} role applied.")
                return
            else:
                await ctx.send(
                    _("Please provide the team you want the goal notification role for.")
                )
                return
        else:
            try:
                role = [
                    role
                    for role in guild.roles
                    if (team.lower() in role.name.lower() and role.name.endswith("GOAL"))
                ]
                await ctx.message.author.add_roles(role[0])
                await ctx.message.channel.send(role[0].name + _(" role applied."))
            except Exception:
                await ctx.message.channel.send(team + _(" is not an available role!"))

    @hockey_commands.command()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def standings(
        self, ctx: Union[commands.Context, discord.Interaction], *, search: HockeyStandings = None
    ) -> None:
        """
        Displays current standings

        `[search]` If provided you can see a teams complete stats
        by searching for team or get all standings at once
        separated by division
        """
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
        source = {
            "all": StandingsPages,
            "conference": ConferenceStandingsPages,
            "western": ConferenceStandingsPages,
            "eastern": ConferenceStandingsPages,
            "division": DivisionStandingsPages,
            "central": DivisionStandingsPages,
            "metropolitan": DivisionStandingsPages,
            "atlantic": DivisionStandingsPages,
            "pacific": DivisionStandingsPages,
        }
        if search is None:
            search = "all"
        standings, page = await Standings.get_team_standings(search.lower(), session=self.session)
        for team in TEAMS:
            if "Team" in team:
                source[team.replace("Team ", "").lower()] = DivisionStandingsPages
            else:
                source[team] = TeamStandingsPages
        await BaseMenu(
            source=source[search](pages=standings),
            page_start=page,
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=180,
        ).start(ctx=ctx)

    @hockey_commands.command(aliases=["score"])
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def games(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        teams_and_date: Optional[TeamDateFinder] = {},
    ) -> None:
        """
        Gets all NHL games for the current season

        If team is provided it will grab that teams schedule.
        A date may also be provided and the bot will search for games within
        that date range.
        Dates must be in the format of `YYYY-MM-DD` if provided.
        Team and Date can be provided at the same time and then
        only that teams games may appear in that date range if they exist.
        """
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
            # if teams_and_date:
            # teams_and_date = await TeamDateFinder().convert(ctx, teams_and_date)
        log.debug(teams_and_date)
        await GamesMenu(
            source=Schedule(**teams_and_date, session=self.session),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=180,
        ).start(ctx=ctx)

    @hockey_commands.command()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def heatmap(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        style: str = "all",
        *,
        teams_and_date: Optional[TeamDateFinder] = {},
    ) -> None:
        """
        Display game heatmaps.

        `[style]` must be one of "all", "ev", "5v5", "sva", "home5v4", or "away5v4"

        If team is provided it will grab that teams schedule.
        A date may also be provided and the bot will search for games within
        that date range.
        Dates must be in the format of `YYYY-MM-DD` if provided.
        Team and Date can be provided at the same time and then
        only that teams games may appear in that date range if they exist.
        """
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
        styles = ["all", "ev", "5v5", "sva", "home5v4", "away5v4"]
        if style not in styles:
            await ctx.send(
                _("Style must be one of {styles}.").format(styles=humanize_list(styles))
            )
            return
        if "style" in teams_and_date:
            teams_and_date.pop("style")
        log.debug(teams_and_date)
        await GamesMenu(
            source=Schedule(
                **teams_and_date,
                session=self.session,
                include_goals=False,
                include_heatmap=True,
                style=style,
            ),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=180,
        ).start(ctx=ctx)

    @hockey_commands.command()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def gameflow(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        strength: str = "all",
        corsi: bool = True,
        *,
        teams_and_date: Optional[TeamDateFinder] = {},
    ) -> None:
        """
        Display games gameflow.

        `[strength]` must be one of "all", "ev", "5v5", or "sva".
        `[corsi]` either true or false.

        If team is provided it will grab that teams schedule.
        A date may also be provided and the bot will search for games within
        that date range.
        Dates must be in the format of `YYYY-MM-DD` if provided.
        Team and Date can be provided at the same time and then
        only that teams games may appear in that date range if they exist.
        """
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
        styles = ["all", "ev", "5v5", "sva"]
        if strength not in styles:
            await ctx.send(
                _("Style must be one of {styles}.").format(styles=humanize_list(styles))
            )
            return
        if "strength" in teams_and_date:
            teams_and_date.pop("strength")
        if "corsi" in teams_and_date:
            teams_and_date.pop("corsi")
        log.debug(teams_and_date)
        await GamesMenu(
            source=Schedule(
                **teams_and_date,
                session=self.session,
                include_goals=False,
                include_gameflow=True,
                corsi=corsi,
                strength=strength,
            ),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=180,
        ).start(ctx=ctx)

    @hockey_commands.command()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def schedule(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        teams_and_date: Optional[TeamDateFinder] = {},
    ) -> None:
        """
        Gets all upcoming NHL games for the current season as a list

        If team is provided it will grab that teams schedule
        A date may also be provided and the bot will search for games within
        that date range.
        Dates must be in the format of `YYYY-MM-DD` if provided.
        Team and Date can be provided at the same time and then
        only that teams games may appear in that date range if they exist.
        """
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
            if teams_and_date:
                teams_and_date = await TeamDateFinder().convert(ctx, teams_and_date)
        await GamesMenu(
            source=ScheduleList(**teams_and_date, session=self.session),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=180,
        ).start(ctx=ctx)

    async def player_id_lookup(self, name: str) -> Tuple[List[int], Dict[int, dict]]:
        now = datetime.utcnow()
        saved = datetime.fromtimestamp(await self.config.player_db())
        path = cog_data_path(self) / "players.json"
        if (now - saved) > timedelta(days=1) or not path.exists():
            async with self.session.get(
                "https://records.nhl.com/site/api/player?include=id&include=fullName&include=onRoster"
            ) as resp:
                with path.open(encoding="utf-8", mode="w") as f:
                    json.dump(await resp.json(), f)
            await self.config.player_db.set(int(now.timestamp()))
        with path.open(encoding="utf-8", mode="r") as f:

            players = {}
            player_ids = []
            async for player in AsyncIter(json.loads(f.read())["data"], steps=100):
                if name.lower() in player["fullName"].lower():
                    if player["onRoster"] == "N":
                        players[player["id"]] = player
                        player_ids.append(player["id"])
                    else:
                        players[player["id"]] = player
                        player_ids.insert(0, player["id"])
        log.debug(players)
        return player_ids, players

    async def player_choices(self, name: str) -> List[dict]:
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
            async for player in AsyncIter(json.loads(f.read())["data"], steps=100):
                if name.lower() in player["fullName"].lower():
                    ret.append({"name": player["fullName"], "value": player["fullName"]})
        return ret

    @hockey_commands.command(aliases=["players"])
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def player(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        search: str,
    ) -> None:
        """
        Lookup information about a specific player

        `<search>` The name of the player to search for
        you can include the season to get stats data on format can be `YYYY` or `YYYYYYYY`
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
            is_slash = True
        else:
            await ctx.trigger_typing()

        season = YEAR_RE.search(search)
        season_str = None
        if season:
            search = YEAR_RE.sub("", search)
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
        log.debug(season)
        log.debug(search)
        player_ids, players = await self.player_id_lookup(search.strip())
        if players != {}:
            await BaseMenu(
                source=PlayerPages(pages=player_ids, season=season_str, players=players),
                cog=self,
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=180,
            ).start(ctx=ctx)
        else:
            msg = _('I could not find any player data for "{player}".').format(player=search)
            if not is_slash:
                await ctx.send(msg)
            else:
                await ctx.followup.send(msg, ephemeral=True)

    @hockey_commands.command()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def roster(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        season: Optional[YearFinder] = None,
        *,
        search: HockeyTeams,
    ) -> None:
        """
        Search for a player or get a team roster

        `[season]` The season to get stats data on format can be `YYYY` or `YYYYYYYY`
        `<search>` The name of the team to search for
        """
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
            if season:
                try:
                    season = await YearFinder().convert(ctx, season)
                except commands.BadArgument as e:
                    await ctx.followup.send(e, ephemeral=True)
            if search:
                try:
                    search = await HockeyTeams().convert(ctx, search)
                except commands.BadArgument as e:
                    await ctx.followup.send(e, ephemeral=True)

        season_str = None
        season_url = ""
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
        if season:
            season_url = f"?season={season_str}"
        if search is None:
            await ctx.send(_("You must provide a valid current team."))
            return
        players = {}
        player_ids = []
        teams = [team for team in TEAMS if search.lower() in team.lower()]
        if teams != []:
            for team in teams:
                url = f"{BASE_URL}/api/v1/teams/{TEAMS[team]['id']}/roster{season_url}"
                async with self.session.get(url) as resp:
                    data = await resp.json()
                if "roster" in data:
                    for player in data["roster"]:
                        player_ids.append(player["person"]["id"])
                        players[player["person"]["id"]] = player["person"]
        else:
            await ctx.send(_("No team name was provided."))
            return

        if players:
            await BaseMenu(
                source=PlayerPages(pages=player_ids, season=season_str, players=players),
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

    @hockey_commands.command(hidden=True)
    @commands.mod_or_permissions(manage_messages=True)
    async def rules(self, ctx: Union[commands.Context, discord.Interaction]) -> None:
        """
        Display a nice embed of server specific rules
        """
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
        em.set_thumbnail(url=str(guild.icon_url))
        em.set_author(name=guild.name, icon_url=str(guild.icon_url))
        return em

    async def post_leaderboard(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        leaderboard_type: Literal[
            "season",
            "weekly",
            "worst",
            "playoffs",
            "playoffs_weekly",
            "pre-season",
            "pre-season_weekly",
        ],
    ) -> None:
        """
        Posts the leaderboard based on specific style
        """
        leaderboard_type_str = leaderboard_type.replace("_", " ").title()
        leaderboard = await self.pickems_config.guild(ctx.guild).leaderboard()
        if leaderboard == {} or leaderboard is None:
            await ctx.send(_("There is no current leaderboard for this server!"))
            return
        if leaderboard_type != "worst":
            leaderboard = sorted(
                leaderboard.items(), key=lambda i: i[1][leaderboard_type], reverse=True
            )
        else:
            leaderboard = sorted(
                leaderboard.items(), key=lambda i: i[1]["total"] - i[1]["season"], reverse=True
            )
        msg_list = []
        count = 1
        user_position = None
        total_str = {
            "season": "total",
            "playoffs": "playoffs_total",
            "pre-season": "pre-season_total",
        }.get(leaderboard_type, "total")
        position = None

        for member_id in leaderboard:
            if str(member_id[0]) == str(ctx.author.id):
                user_position = leaderboard.index(member_id)
            member = ctx.guild.get_member(int(member_id[0]))
            if member is None:
                member_mention = _("User has left the server ") + member_id[0]
            else:
                member_mention = member.mention
            if leaderboard_type in ["weekly", "playoffs_weekly", "pre-season_weekly"]:
                points = member_id[1].get(leaderboard_type, 0)
                msg_list.append("#{}. {}: {}\n".format(count, member_mention, points))
            elif leaderboard_type in ["season", "playoffs", "pre-season"]:
                total = member_id[1].get(total_str, 0)
                wins = member_id[1].get(leaderboard_type, 0)
                try:
                    percent = (wins / total) * 100
                except ZeroDivisionError:
                    percent = 0.0
                msg_list.append(
                    f"#{count}. {member_mention}: {wins}/{total} correct ({percent:.4}%)\n"
                )
            else:
                total = member_id[1].get(total_str, 0)
                losses = member_id[1].get(total_str, 0) - member_id[1].get(leaderboard_type)
                try:
                    percent = (losses / total) * 100
                except ZeroDivisionError:
                    percent = 0.0
                msg_list.append(
                    f"#{count}. {member_mention}: {losses}/{total} incorrect ({percent:.4}%)\n"
                )
            count += 1
        leaderboard_list = [msg_list[i : i + 10] for i in range(0, len(msg_list), 10)]
        if user_position is not None:
            user = leaderboard[user_position][1]
            wins = user["season"]
            total = user[total_str] or 1
            losses = user[total_str] - user["season"]
            position = _(
                "{member}, you're #{number} on the {leaderboard_type} leaderboard!\n"
            ).format(
                member=ctx.author.display_name,
                number=user_position + 1,
                leaderboard_type=leaderboard_type_str,
            )
            if leaderboard_type == "season":
                percent = (wins / total) * 100
                position += _("You have {wins}/{total} correct ({percent:.4}%).").format(
                    wins=wins, total=total, percent=percent
                )
            elif leaderboard_type == "worst":
                percent = (losses / total) * 100
                position += _("You have {wins}/{total} incorrect ({percent:.4}%).").format(
                    wins=wins, total=total, percent=percent
                )

        if ctx.assume_yes:
            em = discord.Embed(timestamp=datetime.now())
            description = ""
            for msg in leaderboard_list[0]:
                description += msg
            em.description = description
            em.set_author(
                name=ctx.guild.name
                + _(" Pickems {style} Leaderboard").format(style=leaderboard_type_str),
                icon_url=ctx.guild.icon_url,
            )
            em.set_thumbnail(url=ctx.guild.icon_url)
            await ctx.send(embed=em)
            return
        if position:
            await ctx.send(position)
        await BaseMenu(
            source=LeaderboardPages(pages=leaderboard_list, style=leaderboard_type_str),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=180,
        ).start(ctx=ctx)

    @hockey_commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def leaderboard(
        self,
        ctx: Union[commands.Context, discord.Interaction],
        *,
        leaderboard_type: str = "seasonal",
    ) -> None:
        """
        Shows the current server leaderboard

        `[leaderboard_type]` can be either `seasonal` the default, `weekly`, or `worst`

        Leaderboards % is calculated based on cumulative votes compared to number of votes.
        This is so that one lucky user who only votes once isn't considered *better*
        than people who consistently vote. The only way to win is to keep playing
        and picking correctly.
        """
        leaderboard_type = leaderboard_type.replace(" ", "_").lower()
        if leaderboard_type in ["seasonal", "season"]:
            await self.post_leaderboard(ctx, "season")
        if leaderboard_type in ["weekly", "week"]:
            await self.post_leaderboard(ctx, "weekly")
        if leaderboard_type in ["playoffs", "playoff"]:
            await self.post_leaderboard(ctx, "playoffs")
        if leaderboard_type in ["playoffs_weekly", "playoff_weekly"]:
            await self.post_leaderboard(ctx, "playoffs_weekly")
        if leaderboard_type in ["pre-season", "preseason"]:
            await self.post_leaderboard(ctx, "pre-season")
        if leaderboard_type in ["pre-season_weekly", "preseason_weekly"]:
            await self.post_leaderboard(ctx, "pre-season_weekly")
        if leaderboard_type in ["worst"]:
            await self.post_leaderboard(ctx, "worst")

    @hockey_commands.command(aliases=["pickemvotes", "pickemvote"])
    @commands.guild_only()
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def pickemsvotes(self, ctx: Union[commands.Context, discord.Interaction]):
        """
        View your current pickems votes for the server.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
        if str(ctx.guild.id) not in self.all_pickems:
            _("This server does not have any pickems setup.")
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
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
        await BaseMenu(source=SimplePages(msgs)).start(ctx=ctx)

    @hockey_commands.command(hidden=True)
    @commands.mod_or_permissions(manage_messages=True)
    async def setrules(
        self, ctx: Union[commands.Context, discord.Interaction], team: HockeyTeams, *, rules
    ) -> None:
        """Set the main rules page for the nhl rules command"""
        if team is None:
            return await ctx.send(_("You must provide a valid current team."))
        if not ctx.channel.permissions_for(ctx.guild.me).embed_links:
            await ctx.send(_("I don't have embed links permission!"))
            return
        await self.config.guild(ctx.guild).rules.set(rules)
        await self.config.guild(ctx.guild).team_rules.set(team)
        em = await self.make_rules_embed(ctx.guild, team, rules)
        await ctx.send(_("Done, here's how it will look."), embed=em)

    @hockey_commands.command(aliases=["link", "invite"])
    async def otherdiscords(
        self, ctx: Union[commands.Context, discord.Interaction], team: HockeyTeams
    ) -> None:
        """
        Get team specific discord links

        choosing all will create a nicely formatted list of
        all current NHL team discord server links
        """
        is_slash = False

        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
            member = ctx.user
            team = await HockeyTeams().convert(ctx, team)
        else:
            member = ctx.author

        if team is None:
            msg = _("You must provide a valid current team.")
            if is_slash:
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
        if team not in ["all"]:
            invite = TEAMS[team]["invite"]
            await ctx.followup.send(_("Here is the {team} server invite link:").format(team=team))
            await ctx.channel.send(invite)
        else:
            if not await self.slash_check_permissions(ctx, member):
                # Don't need everyone spamming this command
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
                "__**Hockey Discord Master List**__\n```fix\n"
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
                "to a ban. ```\n\nhttps://discord.gg/reddithockey\n"
                "https://discord.gg/sdpn\nhttps://discord.gg/thehockeyguy"
            )
            eastern_conference = "https://i.imgur.com/CtXvcCs.png"
            western_conference = "https://i.imgur.com/UFYJTDF.png"
            async with self.session.get(eastern_conference) as resp:
                data = await resp.read()
            logo = BytesIO()
            logo.write(data)
            logo.seek(0)
            image = discord.File(logo, filename="eastern_logo.png")
            await ctx.send(msg1, file=image)
            for division in team_list:
                if division == "Central":
                    async with self.session.get(western_conference) as resp:
                        data = await resp.read()
                    logo = BytesIO()
                    logo.write(data)
                    logo.seek(0)
                    image = discord.File(logo, filename="western_logo.png")
                    await ctx.send(file=image)
                div_emoji = "<:" + TEAMS["Team {}".format(division)]["emoji"] + ">"
                msg = "{0} __**{1} DIVISION**__ {0}".format(div_emoji, division.upper())
                await ctx.send(msg)
                for team in team_list[division]:
                    team_emoji = "<:" + TEAMS[team]["emoji"] + ">"
                    team_link = TEAMS[team]["invite"]
                    msg = "{0} {1} {0}".format(team_emoji, team_link)
                    await ctx.channel.send(msg)
