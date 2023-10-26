from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, EnumMeta
from typing import List, Optional, Union

import discord
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

_ = Translator("Destiny", __file__)

log = getLogger("red.trusty-cogs.Destiny")

STRING_VAR_RE = re.compile(r"{var:(?P<hash>\d+)}")


@dataclass
class NewsArticle:
    Title: str
    Link: str
    PubDate: str
    UniqueIdentifier: str
    Description: str
    ImagePath: str
    OptionalMobileImagePath: Optional[str] = None

    def pubdate(self) -> datetime:
        return datetime.strptime(self.PubDate, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    def save_id(self) -> str:
        return f"{self.UniqueIdentifier}:{int(self.pubdate().timestamp())}"


@dataclass
class NewsArticles:
    CurrentPaginationToken: int
    NextPaginationToken: int
    ResultCountThisPage: int
    NewsArticles: List[NewsArticle]
    PagerAction: str
    CategoryFilter: Optional[str] = None

    @classmethod
    def from_json(cls, data: dict) -> NewsArticles:
        articles = [NewsArticle(**i) for i in data.pop("NewsArticles", [])]
        return cls(NewsArticles=articles, **data)


class DestinyComponentType(Enum):
    none = 0
    profiles = 100
    vendor_receipts = 101
    profile_inventories = 102
    profile_currencies = 103
    profile_progression = 104
    platform_silver = 105
    characters = 200
    character_inventories = 201
    character_progression = 202
    character_renderdata = 203
    character_activities = 204
    character_equipment = 205
    character_loadouts = 206
    item_instances = 300
    item_objectives = 301
    item_perks = 302
    item_renderdata = 303
    item_stats = 304
    item_sockets = 305
    item_talentgrids = 306
    item_common_data = 307
    item_plug_states = 308
    item_plug_objectives = 309
    item_reusable_plugs = 310
    vendors = 400
    vendor_categories = 401
    vendor_sales = 402
    kiosks = 500
    currency_lookups = 600
    presentation_nodes = 700
    collectibles = 800
    records = 900
    transitory = 1000
    metrics = 1100
    string_variables = 1200
    craftables = 1300
    social_commendations = 1400


class DestinyActivityModeType(Enum):
    none = 0
    story = 2
    strike = 3
    raid = 4
    allpvp = 5
    patrol = 6
    allpve = 7
    reserved9 = 9
    control = 10
    reserved11 = 11
    clash = 12
    reserved13 = 13
    crimsondoubles = 15
    nightfall = 16
    heroicnightfall = 17
    allstrikes = 18
    ironbanner = 10
    reserved20 = 20
    reserved21 = 21
    reserved22 = 22
    reserved24 = 24
    allmayhem = 25
    reserved26 = 26
    reserved27 = 27
    reserved28 = 28
    reserved29 = 29
    reserved30 = 30
    supremacy = 31
    privatematchesall = 32
    survival = 37
    countdown = 38
    trialsofthenine = 39
    social = 40
    trialscountdown = 31
    trialssurvival = 42
    ironbannercontrol = 43
    ironbannerclash = 44
    ironbannersupremacy = 45
    scorednightfall = 46
    scoredheroicnightfall = 47
    rumble = 48
    alldoubles = 49
    doubles = 50
    privatematchesclash = 51
    privatematchescontrol = 52
    privatematchessupremacy = 53
    privatematchescountdown = 54
    privatematchesruvival = 55
    privatematchesmayhem = 56
    privatematchesrumble = 57
    heroicadventure = 58
    showdown = 59
    lockdown = 60
    scorched = 61
    scorchedteam = 62
    gambit = 63
    allpvecompetitive = 64
    breakthrough = 65
    blackarmoryrun = 66
    salvage = 67
    ironbannersalvage = 68
    pvpcompetitive = 69
    pvpquickplay = 70
    clashquickplay = 71
    clashcompetitive = 72
    controlquickplay = 73
    controlcompetitive = 74
    gambitprime = 75
    reckoning = 76
    menagerie = 77
    vexoffensive = 78
    nightmarehunt = 79
    elimination = 80
    momentum = 81
    dungeon = 82
    sundial = 83
    trialsofosiris = 84
    dares = 85
    offensive = 86
    lostsector = 87
    rift = 88
    zonecontrol = 89
    ironbannerrift = 90
    ironbannerzonecontrol = 91


class DestinyEnumGroup:
    def __init__(self, enum: EnumMeta, name: str, *args: Union[Enum, int]):
        self._list: List[Enum] = []
        self._enum: EnumMeta = enum
        self._name: str = name
        for arg in args:
            if isinstance(arg, int):
                self._list.append(self._enum(arg))
            elif isinstance(arg, Enum):
                self._list.append(arg)
            else:
                continue

    def __iter__(self):
        return self._list

    def add(self, item: Union[Enum, int]):
        if isinstance(item, int):
            if self._enum(item) not in self._list:
                self._list.append(self._enum(item))
        elif isinstance(item, Enum):
            if item not in self._list:
                self._list.append(item)

    def to_str(self):
        return ",".join(str(i.value) for i in self._list)

    def to_dict(self):
        return {self._name: self.to_str()}


class DestinyComponents(DestinyEnumGroup):
    # "100,102,103,104,200,201,202,204,205,300,302,304,305,307,308,309,310,600,800,900,1000,1100,1200,1300"
    def __init__(self, *args: Union[DestinyComponentType, int]):
        super().__init__(DestinyComponentType, "components", *args)

    @classmethod
    def all(cls):
        return cls(*DestinyComponentType)


class DestinyActivityModeGroup(DestinyEnumGroup):
    def __init__(self, *args: Union[DestinyActivityModeType, int]):
        super().__init__(DestinyActivityModeType, "modes", *args)


class DestinyStatsGroupType(Enum):
    # If the enum value is > 100, it is a "special" group that cannot be
    # queried for directly (special cases apply to when they are returned,
    # and are not relevant in general cases)
    none = 0
    general = 1
    weapons = 2
    medals = 3
    reservedgroups = 100
    # This is purely to serve as the dividing line between
    # filterable and un-filterable groups. Below this
    # number is a group you can pass as a filter.
    # Above it are groups used in very specific circumstances and not relevant for filtering.
    leaderboard = 101
    # Only applicable while generating leaderboards.
    activity = 102
    # These will *only* be consumed by GetAggregateStatsByActivity
    unique_weapon = 103
    # These are only consumed and returned by GetUniqueWeaponHistory
    internal = 104


class DestinyStatsGroup(DestinyEnumGroup):
    def __init__(self, *args: Union[DestinyStatsGroupType, int]):
        super().__init__(DestinyStatsGroupType, "groups", *args)

    @classmethod
    def all(cls):
        return cls(*DestinyStatsGroupType)


class PeriodType(Enum):
    none = 0
    daily = 1
    alltime = 2
    activity = 3


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

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str):
        if argument.lower() == "titan":
            return cls(0)
        if argument.lower() == "hunter":
            return cls(1)
        if argument.lower() == "warlock":
            return cls(2)
        return cls(0)


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


class StatsPage(discord.app_commands.Transformer):
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

    async def transform(self, interaction: discord.Interaction, argument: str) -> str:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)


class DestinyCharacter(discord.app_commands.Transformer):
    """Returns the selected Character ID for a user"""

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        cog = ctx.bot.get_cog("Destiny")
        chars = await cog.config.user(ctx.author).characters()
        if argument.isdigit():
            return argument
        if not chars:
            try:
                characters = await cog.get_characters(
                    ctx.author, components=DestinyComponents(DestinyComponentType.characters)
                )
                chars = characters["characters"]["data"]
                await cog.config.user(ctx.author).characters.set(chars)
            except Exception as e:
                await cog.send_error_msg(ctx, e)
                return
        for char_id, data in chars.items():
            if argument.lower() == "titan" and data["classType"] == 0:
                return char_id
            if argument.lower() == "hunter" and data["classType"] == 1:
                return char_id
            if argument.lower() == "warlock" and data["classType"] == 2:
                return char_id

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        cog = interaction.client.get_cog("Destiny")
        chars = await cog.config.user(interaction.user).characters()
        class_info = await cog.get_entities("DestinyClassDefinition")
        if not chars:
            try:
                characters = await cog.get_characters(
                    interaction.user, components=DestinyComponents(DestinyComponentType.characters)
                )
                chars = characters["characters"]["data"]
                await cog.config.user(interaction.user).characters.set(chars)
            except Exception:
                return [
                    discord.app_commands.Choice(
                        name=_("No characters could be found at this time."), value=""
                    )
                ]
        ret = []
        for char_id, data in sorted(
            chars.items(),
            key=lambda x: datetime.strptime(x[1]["dateLastPlayed"], "%Y-%m-%dT%H:%M:%SZ"),
            reverse=True,
        ):
            name = (
                class_info.get(str(data["classHash"])).get("displayProperties", {}).get("name", "")
            )
            if current.lower() in name.lower():
                ret.append(discord.app_commands.Choice(name=name, value=char_id))
        return ret

    async def transform(self, interaction: discord.Interaction, current: str) -> str:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, current)


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
