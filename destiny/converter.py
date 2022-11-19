from __future__ import annotations

import logging
import re
from enum import Enum
from typing import List, Optional

from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

_ = Translator("Destiny", __file__)

log = logging.getLogger("red.trusty-cogs.Destiny")


class DestinyManifestCacheStyle(Enum):
    disable = 0
    lazy = 1
    enable = 2

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> DestinyManifestCacheStyle:
        if argument.lower() == "lazy":
            return cls(1)
        elif argument.lower() == "enable":
            return cls(2)
        return cls(0)


class DestinyClassType(Enum):
    titan = 0
    hunter = 1
    warlock = 2
    unknown = 3


class DestinyRandomConverter(Enum):
    titan = 0
    hunter = 1
    warlock = 2
    weapon = 3

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str):
        if argument.lower() == "titan":
            return cls(0)
        if argument.lower() == "hunter":
            return cls(1)
        if argument.lower() == "warlock":
            return cls(2)
        if argument.lower() == "weapon":
            return cls(3)
        return cls(0)


class DestinyItemType(Enum):
    none = 0
    currency = 1
    armor = 2
    weapon = 3
    message = 7
    engram = 8
    consumable = 9
    exchangeMaterial = 10
    missionReward = 11
    questStep = 12
    questStepComplete = 13
    emblem = 14
    quest = 15
    subclass = 16
    clanBanner = 17
    aura = 18
    mod = 19
    dummy = 20
    ship = 21
    vehicle = 22
    emote = 23
    ghost = 24
    package = 25
    bounty = 26
    wrapper = 27
    seasonalArtifact = 28
    finisher = 29


class DestinyActivity(Converter):
    """Returns the correct history code if provided a named one"""

    CHOICES: List[dict] = [
        {"name": "all", "value": "0"},
        {"name": "story", "value": "2"},
        {"name": "strike", "value": "3"},
        {"name": "raid", "value": "4"},
        {"name": "allpvp", "value": "5"},
        {"name": "patrol", "value": "6"},
        {"name": "allpve", "value": "7"},
        {"name": "control", "value": "10"},
        {"name": "clash", "value": "12"},
        {"name": "crimsondoubles", "value": "15"},
        {"name": "nightfall", "value": "16"},
        {"name": "heroicnightfall", "value": "17"},
        {"name": "allstrikes", "value": "18"},
        {"name": "ironbanner", "value": "19"},
        {"name": "allmayhem", "value": "25"},
        {"name": "supremacy", "value": "31"},
        {"name": "privatematchesall", "value": "32"},
        {"name": "survival", "value": "37"},
        {"name": "countdown", "value": "38"},
        {"name": "trialsofthenine", "value": "39"},
        {"name": "social", "value": "40"},
        {"name": "trialscountdown", "value": "41"},
        {"name": "trialssurvival", "value": "42"},
        {"name": "ironbannercontrol", "value": "43"},
        {"name": "ironbannerclash", "value": "44"},
        {"name": "ironbannersupremacy", "value": "45"},
        {"name": "scorednightfall", "value": "46"},
        {"name": "scoredheroicnightfall", "value": "47"},
        {"name": "rumble", "value": "48"},
        {"name": "alldoubles", "value": "49"},
        {"name": "doubles", "value": "50"},
        {"name": "privatematchesclash", "value": "51"},
        {"name": "privatematchescontrol", "value": "52"},
        {"name": "privatematchessupremacy", "value": "53"},
        {"name": "privatematchescountdown", "value": "54"},
        {"name": "privatematchessurvival", "value": "55"},
        {"name": "privatematchesmayhem", "value": "56"},
        {"name": "privatematchesrumble", "value": "57"},
        {"name": "heroicadventure", "value": "58"},
        {"name": "showdown", "value": "59"},
        {"name": "lockdown", "value": "60"},
        {"name": "scorched", "value": "61"},
        {"name": "scorchedteam", "value": "62"},
        {"name": "gambit", "value": "63"},
        {"name": "allpvecompetitive", "value": "64"},
        {"name": "breakthrough", "value": "65"},
        {"name": "blackarmoryrun", "value": "66"},
        {"name": "salvage", "value": "67"},
        {"name": "ironbannersalvage", "value": "68"},
        {"name": "pvpcompetitive", "value": "69"},
        {"name": "pvpquickplay", "value": "70"},
        {"name": "clashquickplay", "value": "71"},
        {"name": "clashcompetitive", "value": "72"},
        {"name": "controlquickplay", "value": "73"},
        {"name": "controlcompetitive", "value": "74"},
        {"name": "gambirprime", "value": "75"},
        {"name": "reckoning", "value": "76"},
        {"name": "menagerie", "value": "77"},
        {"name": "vexoffensive", "value": "78"},
        {"name": "nightmarehunt", "value": "79"},
        {"name": "elimination", "value": "80"},
        {"name": "momentum", "value": "81"},
        {"name": "dungeon", "value": "82"},
        {"name": "sundial", "value": "83"},
        {"name": "trialsofosiris", "value": "84"},
    ]

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


class DestinyEververseItemType(Converter):
    """Returns the correct item type code if provided a named one"""

    ITEM_TYPE_RE = re.compile(
        r"(ghosts?|ships?|vehicles?|sparrows?|finishers?|packages?|consumables?)", flags=re.I
    )
    ITEM_SUB_TYPE_RE = re.compile(r"(shaders?|ornaments?)", flags=re.I)

    async def convert(self, ctx: commands.Context, argument: str) -> dict:
        ret = {"item_types": [], "item_sub_types": []}
        item_types: dict = {
            "consumable": 9,
            "ship": 21,
            "vehicle": 22,
            "ghost": 24,
            "finisher": 29,
        }
        item_sub_types: dict = {"shaders": 20, "ornaments": 21}
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
