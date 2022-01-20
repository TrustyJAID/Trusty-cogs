from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Pattern, Tuple, Union

import discord
import pytz
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from redbot.core.bot import Red
from redbot.core.commands import Context
from redbot.core.i18n import Translator

from .constants import TEAMS
from .teamentry import TeamEntry

if TYPE_CHECKING:
    from .game import Game


_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")

DATE_RE = re.compile(
    r"((19|20)\d\d)[- \/.](0[1-9]|1[012]|[1-9])[- \/.](0[1-9]|[12][0-9]|3[01]|[1-9])"
)
DAY_REF_RE = re.compile(r"(yesterday|tomorrow|today)", re.I)

YEAR_RE = re.compile(r"((19|20)\d\d)-?\/?((19|20)\d\d)?")
# https://www.regular-expressions.info/dates.html

TIMEZONE_RE = re.compile(r"|".join(re.escape(zone) for zone in pytz.common_timezones), flags=re.I)


def utc_to_local(utc_dt: datetime, new_timezone: str = "US/Pacific") -> datetime:
    eastern = pytz.timezone(new_timezone)
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=eastern)


def get_chn_name(game: Game) -> str:
    """
    Creates game day channel name
    """
    timestamp = utc_to_local(game.game_start)
    chn_name = "{}-vs-{}-{}-{}-{}".format(
        game.home_abr, game.away_abr, timestamp.year, timestamp.month, timestamp.day
    )
    return chn_name.lower()


class YearFinder(Converter):
    """
    Validates Year format

    for use in the `[p]nhl games` command to pull up specific dates
    """

    async def convert(self, ctx: Context, argument: str) -> re.Match:
        find = YEAR_RE.search(argument)
        if find:
            return find
        else:
            raise BadArgument(_("`{arg}` is not a valid year.").format(arg=argument))


class DateFinder(Converter):
    """
    Converter for `YYYY-MM-DD` date formats

    for use in the `[p]nhl games` command to pull up specific dates
    """

    async def convert(self, ctx: Context, argument: str) -> Optional[datetime]:
        find = DATE_RE.search(argument)
        if find:
            date_str = f"{find.group(1)}-{find.group(3)}-{find.group(4)}"
            return datetime.strptime(date_str, "%Y-%m-%d")
        else:
            return datetime.utcnow()


class TimezoneFinder(Converter):
    """
    Converts user input into valid timezones for pytz to use
    """

    async def convert(self, ctx: Context, argument: str) -> str:
        find = TIMEZONE_RE.search(argument)
        if find:
            return find.group(0)
        else:
            raise BadArgument(
                _(
                    "`{argument}` is not a valid timezone. Please see "
                    "`{prefix}hockeyset timezone list`."
                ).format(argument=argument, prefix=ctx.clean_prefix)
            )


class TeamDateFinder(Converter):
    """
    Converter to get both a team and a date from a string
    """

    async def convert(
        self, ctx: Context, argument: str
    ) -> Dict[str, Optional[Union[datetime, List[str], str]]]:
        result: Dict[str, Optional[Union[datetime, List[str], str]]] = {"team": []}
        find = DATE_RE.search(argument)
        day_ref = DAY_REF_RE.search(argument)
        if find:
            date_str = f"{find.group(1)}-{find.group(3)}-{find.group(4)}"
            result["date"] = datetime.strptime(date_str, "%Y-%m-%d")
            argument = DATE_RE.sub("", argument)
        if day_ref:
            today = utc_to_local(datetime.utcnow())
            if day_ref.group(1).lower() == "yesterday":
                result["date"] = today + timedelta(days=-1)
            elif day_ref.group(1).lower() == "tomorrow":
                result["date"] = today + timedelta(days=+1)
            else:
                result["date"] = today
            argument = DAY_REF_RE.sub("", argument)
        potential_teams = argument.split()
        for team, data in TEAMS.items():
            if "Team" in team:
                continue
            nick = data["nickname"]
            short = data["tri_code"]
            pattern = fr"{short}\b|" + r"|".join(fr"\b{i}\b" for i in team.split())
            if nick:
                pattern += r"|" + r"|".join(fr"\b{i}\b" for i in nick)
            # log.debug(pattern)
            reg: Pattern = re.compile(fr"\b{pattern}", flags=re.I)
            for pot in potential_teams:
                find = reg.findall(pot)
                if find:
                    log.debug(reg)
                    log.debug(find)
                    result["team"].append(team)

        return result


class SelectTeamMenu(discord.ui.Select):
    def __init__(self, max_values=1, min_values=1, placeholder=_("Pick a team")):
        super().__init__(max_values=max_values, min_values=min_values, placeholder=placeholder)

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        pass


class SelectTeamView(discord.ui.View):
    def __init__(self, ctx: Context, author: discord.Member):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class HockeyTeams(Converter):
    """
    Converter for valid Hockey Teams to choose from
    """

    async def convert(
        self, ctx: Context, argument: str
    ) -> Optional[Union[List[Dict[str, dict]], str]]:
        result: Optional[Union[List[Dict[str, dict]], str]] = []
        team_list = await check_valid_team(argument)
        if team_list == []:
            raise BadArgument(_('Team "{team}" not found').format(team=argument))
        if len(team_list) == 1:
            result = team_list[0]
        else:
            # This is just some extra stuff to correct the team picker
            msg = _("There's multiple teams with that name, pick one of these:\n")
            is_slash = False
            if isinstance(ctx, discord.Interaction):
                is_slash = True
                author = ctx.user
            else:
                author = ctx.author
            view = SelectTeamView(ctx, author)
            menu = SelectTeamMenu(max_values=1, min_values=1, placeholder=_("Pick a team"))
            for team in team_list[:25]:
                emoji_str = TEAMS[team]["emoji"]
                if emoji_str:
                    emoji = discord.PartialEmoji.from_str(emoji_str)

                else:
                    emoji = None
                menu.add_option(emoji=emoji, label=team)
            view.add_item(menu)
            if is_slash:
                await ctx.followup.send(msg, view=view)
            else:
                await ctx.send(msg, view=view)
            await view.wait()
            if len(menu.values) == 0:
                return None
            return menu.values[0]
        return result


class HockeyStandings(Converter):
    """
    Converter for valid Hockey Standings to choose from

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    async def convert(self, ctx: Context, argument: str) -> Optional[str]:
        result = None
        team_list = await check_valid_team(argument, True)
        if team_list == []:
            raise BadArgument(_('Standing or Team "{team}" not found').format(team=argument))
        if len(team_list) >= 1:
            result = team_list[0]
        return result


class HockeyStates(Converter):
    """
    Converter for valid Hockey states to pick from

        This is used to determine what game states the bot should post.
    """

    async def convert(self, ctx: Context, argument: str) -> str:
        state_list = ["preview", "live", "final", "goal", "periodrecap"]
        if argument.lower() not in state_list:
            raise BadArgument('"{}" is not a valid game state.'.format(argument))
        return argument.title()


async def check_to_post(
    bot: Red, channel: discord.TextChannel, channel_data: dict, post_state: str, game_state: str
) -> bool:
    if channel is None:
        return False
    channel_teams = channel_data.get("team", [])
    if channel_teams is None:
        await bot.get_cog("Hockey").config.channel(channel).team.clear()
        return False
    should_post = False
    if game_state in channel_data["game_states"]:
        for team in channel_teams:
            if team in post_state:
                should_post = True
    return should_post


async def get_team_role(guild: discord.Guild, home_team: str, away_team: str) -> Tuple[str, str]:
    """
    This returns the role mentions if they exist
    Otherwise it returns the name of the team as a str
    """
    home_role = None
    away_role = None

    for role in guild.roles:
        if "Montréal Canadiens" in home_team and "Montreal Canadiens" in role.name:
            home_role = role.mention
        elif role.name == home_team:
            home_role = role.mention
        if "Montréal Canadiens" in away_team and "Montreal Canadiens" in role.name:
            away_role = role.mention
        elif role.name == away_team:
            away_role = role.mention
    if home_role is None:
        home_role = home_team
    if away_role is None:
        away_role = away_team
    return home_role, away_role


async def get_team(bot: Red, team: str) -> TeamEntry:
    config = bot.get_cog("Hockey").config
    team_list = await config.teams()
    if team_list is None:
        team_list = []
        team_entry = TeamEntry("Null", team, 0, [], {}, [], "")
        team_list.append(team_entry.to_json())
        await config.teams.set(team_list)
    for teams in team_list:
        if team == teams["team_name"]:
            return teams
    # Add unknown teams to the config to track stats
    return_team = TeamEntry("Null", team, 0, [], {}, [], "")
    team_list.append(return_team.to_json())
    await config.teams.set(team_list)
    return return_team


async def check_valid_team(team_name: str, standings: bool = False) -> List[str]:
    """
    Checks if this is a valid team name or all teams
    useful for game day channel creation should impliment elsewhere

    Parameters
    ----------
        team_name: str
            The team name you're searching for
        standings: bool
            Whether or not to include standings types

    Returns
    -------
        List[str]
            A list of the teams that resemble the search. Teams
            will be returned sorted alphabetically and in preference of
            active teams first.
    """
    is_team = []
    active_team = set()
    inactive_team = set()
    conference: List[str] = ["eastern", "western", "conference"]
    division = [
        "central",
        "metropolitan",
        "division",
        "pacific",
        "atlantic",
    ]
    if team_name.lower() == "all":
        return ["all"]
    if standings:
        if team_name in conference:
            return [team_name]
        if team_name.lower() in division:
            return [team_name]
        for div in division:
            if team_name.lower() in div:
                return [div]
    for team, data in TEAMS.items():
        if team_name.lower() in team.lower():
            if data["active"]:
                active_team.add(team)
            else:
                inactive_team.add(team)
    if team_name.lower() in {"montreal canadiens", "habs", "montreal"}:
        active_team.add("Montréal Canadiens")
    if team_name.lower() in {"avs"}:
        active_team.add("Colorado Avalanche")
    if team_name.lower() in {"preds"}:
        active_team.add("Nashville Predators")
    if team_name.lower() in {"bolts"}:
        active_team.add("Tampa Bay Lightning")
    if team_name.lower() in {"jackets", "bjs"}:
        active_team.add("Columbus Blue Jackets")
    if team_name.lower() in {"isles"}:
        active_team.add("New York Islanders")
    if team_name.lower() in {"sens"}:
        active_team.add("Ottawa Senators")
    if team_name.lower() in {"pens"}:
        active_team.add("Pittsburgh Penguins")
    if team_name.lower() in {"caps"}:
        active_team.add("Washington Capitals")
    is_team = sorted(active_team) + sorted(inactive_team)
    return is_team


async def get_channel_obj(
    bot: Red, channel_id: int, data: dict
) -> Optional[Union[discord.TextChannel, discord.Thread]]:
    """
    Requires a bot object to access config, channel_id, and channel config data
    Returns the channel object and sets the guild ID if it's missing from config

    This is used in Game objects and Goal objects so it's here to be shared
    between the two rather than duplicating the code
    """
    if not data["guild_id"]:
        channel = bot.get_channel(channel_id)
        if not channel:
            await bot.get_cog("Hockey").config.channel_from_id(channel_id).clear()
            log.info(f"{channel_id} channel was removed because it no longer exists")
            return None
        guild = channel.guild
        await bot.get_cog("Hockey").config.channel(channel).guild_id.set(guild.id)
        return channel
    guild = bot.get_guild(data["guild_id"])
    if not guild:
        await bot.get_cog("Hockey").config.channel_from_id(channel_id).clear()
        log.info(f"{channel_id} channel was removed because it no longer exists")
        return None
    channel = guild.get_channel(channel_id)
    thread = guild.get_thread(channel_id)
    if channel is None and thread is None:
        await bot.get_cog("Hockey").config.channel_from_id(channel_id).clear()
        log.info(f"{channel_id} channel was removed because it no longer exists")
        return None
    return channel or thread
