import discord
import aiohttp
from datetime import datetime
from .constants import BASE_URL, TEAMS, HEADSHOT_URL
from redbot.core.i18n import Translator
import logging

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


async def make_rules_embed(guild, team, rules):
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
    em.set_thumbnail(url=guild.icon_url)
    em.set_author(name=guild.name, icon_url=guild.icon_url)
    return em


async def make_leaderboard_embed(guild, post_list, page=0):
    """
        Makes the leaderboard embed
    """
    leaderboard = post_list["lists"][page]
    style = post_list["type"]
    em = discord.Embed(timestamp=datetime.utcnow())
    description = ""
    for msg in leaderboard:
        description += msg
    em.description = description
    em.set_author(
        name=guild.name + _(" Pickems ") + style + _(" Leaderboard"), icon_url=guild.icon_url
    )
    em.set_thumbnail(url=guild.icon_url)
    em.set_footer(text=_("Page") + " {}/{}".format(page + 1, len(post_list["lists"])))
    return em


async def roster_embed(post_list, page):
    """
        Builds the embed for players by stats in the current season
    """
    player_list = post_list[page]
    url = BASE_URL + player_list["person"]["link"] + "?expand=person.stats&stats=yearByYear"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            player_data = await resp.json()
    player = player_data["people"][0]
    year_stats = [
        league
        for league in player["stats"][0]["splits"]
        if league["league"]["name"] == "National Hockey League"
    ][-1]
    name = player["fullName"]
    number = player["primaryNumber"]
    position = player["primaryPosition"]["name"]
    headshot = HEADSHOT_URL.format(player["id"])
    team = player["currentTeam"]["name"]
    em = discord.Embed(colour=int(TEAMS[team]["home"].replace("#", ""), 16))
    em.set_author(
        name="{} #{}".format(name, number),
        url=TEAMS[team]["team_url"],
        icon_url=TEAMS[team]["logo"],
    )
    em.add_field(name="Position", value=position)
    em.set_thumbnail(url=headshot)
    if position != "Goalie":
        post_data = {
            _("Shots"): year_stats["stat"]["shots"],
            _("Goals"): year_stats["stat"]["goals"],
            _("Assists"): year_stats["stat"]["assists"],
            _("Hits"): year_stats["stat"]["hits"],
            _("Face Off Percent"): year_stats["stat"]["faceOffPct"],
            "+/-": year_stats["stat"]["plusMinus"],
            _("Blocked Shots"): year_stats["stat"]["blocked"],
            _("PIM"): year_stats["stat"]["pim"],
        }
        for key, value in post_data.items():
            if value != 0.0:
                em.add_field(name=key, value=value)
    else:
        saves = year_stats["stat"]["saves"]
        save_percentage = year_stats["stat"]["savePercentage"]
        goals_against_average = year_stats["stat"]["goalAgainstAverage"]
        em.add_field(name=_("Saves"), value=saves)
        em.add_field(name=_("Save Percentage"), value=save_percentage)
        em.add_field(name=_("Goals Against Average"), value=goals_against_average)
    return em
