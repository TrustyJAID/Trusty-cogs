import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Pattern, Tuple, Union

import discord
import pytz
from discord.ext.commands.converter import Converter, EmojiConverter
from discord.ext.commands.errors import BadArgument
from redbot.core.bot import Red
from redbot.core.commands import Context
from redbot.core.i18n import Translator
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate, MessagePredicate

from .constants import TEAMS
from .teamentry import TeamEntry

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


class HockeyTeams(Converter):
    """
    Converter for valid Hockey Teams to choose from

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    async def convert(
        self, ctx: Context, argument: str
    ) -> Optional[Union[List[Dict[str, dict]], str]]:
        result: Optional[Union[List[Dict[str, dict]], str]] = []
        team_list = await check_valid_team(argument)
        my_perms = ctx.channel.permissions_for(ctx.guild.me)
        if team_list == []:
            raise BadArgument('Team "{}" not found'.format(argument))
        if len(team_list) == 1:
            result = team_list[0]
        else:
            # This is just some extra stuff to correct the team picker
            msg = _("There's multiple teams with that name, pick one of these:\n")
            if my_perms.add_reactions and my_perms.use_external_emojis:
                new_msg = await ctx.send(msg)
                team_emojis = [
                    await EmojiConverter().convert(ctx, "<:" + TEAMS[team]["emoji"] + ">")
                    for team in team_list
                ]
                log.debug(team_emojis)
                log.debug(team_list)
                pred = ReactionPredicate.with_emojis(team_emojis, message=new_msg)
                start_adding_reactions(new_msg, team_emojis)
                try:
                    reaction, user = await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                except asyncio.TimeoutError:
                    await new_msg.edit(content=_("I guess not."))
                    return None
                else:
                    result = team_list[pred.result]
                    log.debug(result)
            else:
                for i, team_name in enumerate(team_list):
                    msg += "{}: {}\n".format(i + 1, team_name)

                def msg_check(m):
                    return m.author == ctx.message.author

                try:
                    msg = await ctx.bot.wait_for("message", check=msg_check, timeout=60)
                except asyncio.TimeoutError:
                    await new_msg.edit(content=_("I guess not."))
                    return None

                if msg.content.isdigit():
                    msg = int(msg.content) - 1
                    try:
                        result = team_list[msg]
                    except (IndexError, ValueError, AttributeError):
                        pass
                else:
                    return_team = None
                    for team in team_list:
                        if msg.content.lower() in team.lower():
                            return_team = team
                    result = return_team
            if new_msg:
                await new_msg.delete()
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
            raise BadArgument('Standing or Team "{}" not found'.format(argument))
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
    """
    is_team = []
    conference: List[str] = []  # ["eastern", "western", "conference"]
    division = [
        "central",
        "discover",
        "division",
        "scotia",
        "north",
        "massmutual",
        "east",
        "honda",
        "west",
    ]
    if team_name.lower() == "all":
        return ["all"]
    if team_name in conference and standings:
        return [team_name]
    if team_name.lower() in division and standings:
        return [team_name]
    for team in TEAMS:
        if team_name.lower() in team.lower():
            is_team.append(team)
    if is_team == []:
        if team_name.lower() in ["montreal canadiens", "habs", "montreal"]:
            is_team.append("Montréal Canadiens")
        if team_name.lower() == "avs":
            is_team.append("Colorado Avalanche")
        if team_name.lower() == "preds":
            is_team.append("Nashville Predators")
        if team_name.lower() == "bolts":
            is_team.append("Tampa Bay Lightning")
        if team_name.lower() in ["jackets", "bjs"]:
            is_team.append("Columbus Blue Jackets")
        if team_name.lower() == "isles":
            is_team.append("New York Islanders")
        if team_name.lower() == "sens":
            is_team.append("Ottawa Senators")
        if team_name.lower() == "pens":
            is_team.append("Pittsburgh Penguins")
        if team_name.lower() == "caps":
            is_team.append("Washington Capitals")
    return is_team


async def get_channel_obj(bot: Red, channel_id: int, data: dict) -> Optional[discord.TextChannel]:
    """
    Requires a bot object to access config, channel_id, and channel config data
    Returns the channel object and sets the guild ID if it's missing from config

    This is used in Game objects and Goal objects so it's here to be shared
    between the two rather than duplicating the code
    """
    if not data["guild_id"]:
        channel = bot.get_channel(id=channel_id)
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
    if channel is None:
        await bot.get_cog("Hockey").config.channel_from_id(channel_id).clear()
        log.info(f"{channel_id} channel was removed because it no longer exists")
        return None
    return channel
