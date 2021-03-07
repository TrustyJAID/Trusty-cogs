import logging
import re

from typing import Optional

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
            "trialsofthenine": {"code": 39, "alt": ["9"]},
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
            "gambirprime": {"code": 75, "alt": []},
            "reckoning": {"code": 76, "alt": []},
            "menagerie": {"code": 77, "alt": []},
            "vexoffensive": {"code": 78, "alt": []},
            "nightmarehunt": {"code": 79, "alt": []},
            "elimination": {"code": 80, "alt": ["elim"]},
            "momentum": {"code": 81, "alt": []},
            "dungeon": {"code": 82, "alt": []},
            "sundial": {"code": 83, "alt": []},
            "trialsofosiris": {"code": 84, "alt": ["trials"]},
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


@cog_i18n(_)
class SearchInfo(Converter):
    """Returns specific type of information to display with search
    By default we want to list the available perks on the weapon
    Sometimes a user may want to view an items lore card

    returns True to show lore pages instead
    returns False to show detailed info instead

    """

    async def convert(self, ctx: commands.Context, argument: str) -> Optional[bool]:

        possible_results = {
            "lore": {"code": False, "alt": ["lore"]},
            "details": {
                "code": True,
                "alt": ["stats", "yes", "y", "true", "t", "1", "enable", "on"],
            },
        }
        result = None
        argument = argument.lower()
        if argument in possible_results:
            result = possible_results[argument]["code"]
        else:
            for k, v in possible_results.items():
                if argument in v["alt"]:
                    result = v["code"]
        if result is None:
            raise BadArgument()
        return result


@cog_i18n(_)
class DestinyItemType(Converter):
    """Returns the correct item type code if provided a named one
    This is essentially the enum for item type as a converter
    None: 0
    Currency: 1
    Armor: 2
    Weapon: 3
    Message: 7
    Engram: 8
    Consumable: 9
    ExchangeMaterial: 10
    MissionReward: 11
    QuestStep: 12
    QuestStepComplete: 13
    Emblem: 14
    Quest: 15
    Subclass: 16
    ClanBanner: 17
    Aura: 18
    Mod: 19
    Dummy: 20
    Ship: 21
    Vehicle: 22
    Emote: 23
    Ghost: 24
    Package: 25
    Bounty: 26
    Wrapper: 27
    SeasonalArtifact: 28
    Finisher: 29
    """

    async def convert(self, ctx: commands.Context, argument: str) -> int:
        possible_results: dict = {
            "none": {"code": 0, "alt": []},
            "currency": {"code": 1, "alt": []},
            "armor": {"code": 2, "alt": ["armour"]},
            "weapon": {"code": 3, "alt": ["weapons"]},
            "message": {"code": 7, "alt": []},
            "engram": {"code": 8, "alt": []},
            "consumable": {"code": 9, "alt": []},
            "exchangematerial": {"code": 10, "alt": []},
            "missionreward": {"code": 11, "alt": []},
            "queststep": {"code": 12, "alt": []},
            "questStepcomplete": {"code": 13, "alt": []},
            "emblem": {"code": 14, "alt": []},
            "quest": {"code": 15, "alt": []},
            "subclass": {"code": 16, "alt": []},
            "clanbanner": {"code": 17, "alt": []},
            "aura": {"code": 18, "alt": []},
            "mod": {"code": 19, "alt": []},
            "dummy": {"code": 20, "alt": []},
            "ship": {"code": 21, "alt": []},
            "vehicle": {"code": 22, "alt": ["sparrow"]},
            "emote": {"code": 23, "alt": ["emotes"]},
            "ghost": {"code": 24, "alt": ["ghosts"]},
            "package": {"code": 25, "alt": []},
            "bounty": {"code": 26, "alt": []},
            "wrapper": {"code": 27, "alt": []},
            "seasonalartifact": {"code": 28, "alt": []},
            "finisher": {"code": 29, "alt": ["finishers"]},
        }
        result = None
        argument = argument.lower()
        if argument.isdigit() and int(argument) in [
            v["code"] for k, v in possible_results.items()
        ]:
            result = int(argument)
        elif argument.lower() in possible_results:
            result = possible_results[argument]["code"]
        else:
            for k, v in possible_results.items():
                if argument in v["alt"]:
                    result = v["code"]
        if not result:
            raise BadArgument(
                _("That is not an available item type, pick from these: {activity_list}").format(
                    activity_list=humanize_list(list(possible_results.keys()))
                )
            )
        return result


@cog_i18n(_)
class DestinyEververseItemType(Converter):
    """Returns the correct item type code if provided a named one
    """

    ITEM_TYPE_RE = re.compile(
        r"(ghosts?|ships?|vehicles?|sparrows?|finishers?|packages?|consumables?)", flags=re.I
    )
    ITEM_SUB_TYPE_RE = re.compile(r"(shaders?|ornaments?)", flags=re.I)

    async def convert(self, ctx: commands.Context, argument: str) -> dict:
        ret = {"item_types": [], "item_sub_types": []}
        item_types: dict = {
            "consumable": 9,
            "ship":  21,
            "vehicle": 22,
            "ghost": 24,
            "finisher": 29,
        }
        item_sub_types: dict = {
            "shaders": 20,
            "ornaments": 21
        }
        for i in self.ITEM_TYPE_RE.findall(argument):
            if i in item_types:
                ret["item_types"].append(item_types[i])
            if i[:-1] in item_types:
                ret["item_types"].append(item_types[i[:-1]])

        for i in self.ITEM_SUB_TYPE_RE.findall(argument):
            if i in item_sub_types:
                ret["item_sub_types"].append(item_sub_types[i])
            if i[:-1] in item_sub_types:
                ret["item_sub_types"].append(item_sub_types[i[:-1]])

        return ret
