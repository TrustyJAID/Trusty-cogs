import logging

from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

_ = Translator("Destiny", __file__)

log = logging.getLogger("red.trusty-cogs.Destiny")


@cog_i18n(_)
class DestinyActivity(Converter):
    """Returns the correct history code if provided a named one"""

    async def convert(self, ctx: commands.Context, argument: str) -> int:
        possible_results: dict = {
            "all": {"code": 0, "alt": ["none"]},
            "story": {"code": 2, "alt": []},
            "strike": {"code": 3, "alt": []},
            "raid": {"code": 4, "alt": []},
            "allpvp": {"code": 5, "alt": ["pvp"]},
            "patrol": {"code": 6, "alt": []},
            "allpve": {"code": 7, "alt": ["pve"]},
            "control": {"code": 10, "alt": []},
            "clash": {"code": 12, "alt": []},
            "crimsondoubles": {"code": 15, "alt": []},
            "nightfall": {"code": 16, "alt": []},
            "heroicnightfall": {"code": 17, "alt": []},
            "allstrikes": {"code": 18, "alt": []},
            "ironbanner": {"code": 19, "alt": []},
            "allmayhem": {"code": 25, "alt": []},
            "supremacy": {"code": 31, "alt": []},
            "privatematchesall": {"code": 32, "alt": ["private"]},
            "survival": {"code": 37, "alt": []},
            "countdown": {"code": 38, "alt": []},
            "trialsofthenine": {"code": 39, "alt": ["9", "trials"]},
            "social": {"code": 40, "alt": []},
            "trialscountdown": {"code": 41, "alt": []},
            "trialssurvival": {"code": 42, "alt": []},
            "ironbannercontrol": {"code": 43, "alt": []},
            "ironbannerclash": {"code": 44, "alt": []},
            "ironbannersupremacy": {"code": 45, "alt": []},
            "scorednightfall": {"code": 46, "alt": []},
            "scoredheroicnightfall": {"code": 47, "alt": []},
            "rumble": {"code": 48, "alt": []},
            "alldoubles": {"code": 49, "alt": []},
            "doubles": {"code": 50, "alt": []},
            "privatematchesclash": {"code": 51, "alt": ["privateclash"]},
            "privatematchescontrol": {"code": 52, "alt": ["privatecontrol"]},
            "privatematchessupremacy": {"code": 53, "alt": ["privatesupremacy"]},
            "privatematchescountdown": {"code": 54, "alt": ["privatecountdown"]},
            "privatematchessurvival": {"code": 55, "alt": ["privatesurvival"]},
            "privatematchesmayhem": {"code": 56, "alt": ["privatemayhem"]},
            "privatematchesrumble": {"code": 57, "alt": ["privaterumble"]},
            "heroicadventure": {"code": 58, "alt": []},
            "showdown": {"code": 59, "alt": []},
            "lockdown": {"code": 60, "alt": []},
            "scorched": {"code": 61, "alt": []},
            "scorchedteam": {"code": 62, "alt": []},
            "gambit": {"code": 63, "alt": []},
            "allpvecompetitive": {"code": 64, "alt": ["pvecomp"]},
            "breakthrough": {"code": 65, "alt": []},
            "blackarmoryrun": {"code": 66, "alt": ["blackarmory", "armory"]},
            "salvage": {"code": 67, "alt": []},
            "ironbannersalvage": {"code": 68, "alt": []},
            "pvpcompetitive": {"code": 69, "alt": ["pvpcomp", "comp"]},
            "pvpquickplay": {"code": 70, "alt": ["pvpqp", "qp"]},
            "clashquickplay": {"code": 71, "alt": ["clashqp"]},
            "clashcompetitive": {"code": 72, "alt": ["clashcomp"]},
            "controlquickplay": {"code": 73, "alt": ["controlqp"]},
            "controlcompetitive": {"code": 74, "alt": ["controlcomp"]},
        }
        result = None
        argument = argument.lower()
        if argument.isdigit() and int(argument) in [
            v["code"] for k, v in possible_results.items()
        ]:
            result = int(argument)
        elif argument in possible_results:
            result = possible_results[argument]["code"]
        else:
            for k, v in possible_results.items():
                if argument in v["alt"]:
                    result = v["code"]
        if not result:
            raise BadArgument(
                _("That is not an available activity, pick from these: {activity_list}").format(
                    activity_list=humanize_list(list(possible_results.keys()))
                )
            )
        return result


@cog_i18n(_)
class StatsPage(Converter):
    """Returns a tuple of strings of the correct stats page type to use"""

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        possible_results = {
            "allpvp": {"code": "allPvP", "alt": ["pvp"]},
            "patrol": {"code": "patrol", "alt": []},
            "raid": {"code": "raid", "alt": ["all"]},
            "story": {"code": "story", "alt": []},
            "allstrikes": {"code": "allStrikes", "alt": ["strikes", "strike"]},
            "allpve": {"code": "allPvE", "alt": ["pve"]},
            "allpvecompetitive": {"code": "allPvECompetitive", "alt": ["gambit"]},
        }
        result = None
        argument = argument.lower()
        if argument in possible_results:
            result = possible_results[argument]["code"]
        else:
            for k, v in possible_results.items():
                if argument in v["alt"]:
                    result = v["code"]
        if not result:
            raise BadArgument(
                _("That is not an available stats page, pick from these: {activity_list}").format(
                    activity_list=humanize_list(list(possible_results.keys()))
                )
            )
        return result
