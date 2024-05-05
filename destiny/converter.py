from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, EnumMeta
from typing import List, NamedTuple, Optional, Union

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

LOADOUT_COLOURS = {
    "3871954967": discord.Colour(2171690),
    "3871954966": discord.Colour(9867402),
    "3871954965": discord.Colour(3947839),
    "3871954964": discord.Colour(506554),
    "3871954963": discord.Colour(4285049),
    "3871954962": discord.Colour(6723509),
    "3871954961": discord.Colour(3893443),
    "3871954960": discord.Colour(1978973),
    "3871954975": discord.Colour(10388775),
    "3871954974": discord.Colour(4074770),
    "1693821586": discord.Colour(2445870),
    "1693821587": discord.Colour(3241571),
    "1693821584": discord.Colour(7317564),
    "1693821585": discord.Colour(12277017),
    "1693821590": discord.Colour(11813737),
    "1693821591": discord.Colour(3942220),
    "1693821588": discord.Colour(9004445),
    "1693821589": discord.Colour(3483255),
    "1693821594": discord.Colour(8333347),
    "1693821595": discord.Colour(5248791),
}
# Generated from the dominant colour of each image using
# this algorithm https://stackoverflow.com/a/61730849


class BungieTweet:
    def __init__(self, **kwargs):
        self.id: str = kwargs.pop("id", "")
        self.created_at: str = kwargs.pop("created_at", datetime.now(timezone.utc).isoformat())
        self.user: str = kwargs.pop("user", "")
        self.user_id: str = kwargs.pop("user_id", "")
        self.text: str = kwargs.pop("text", "")
        self.raw_text: str = kwargs.pop("raw_text", "")
        self.thread_text: str = kwargs.pop("thread_text", "")
        self.thread_raw_text: str = kwargs.pop("thread_raw_text", "")
        self.lang: str = kwargs.pop("lang", "en")
        self.in_reply_to: Optional[str] = kwargs.pop("in_reply_to", "")
        self.is_quote_status: bool = kwargs.pop("is_quote_status", "")
        self.quote: str = kwargs.pop("quote", "")
        self.possibly_sensitive: Optional[bool] = kwargs.pop("possibly_sensitive", False)
        self.possibly_sensitive_editable: Optional[bool] = kwargs.pop(
            "possibly_sensitive_editable", True
        )
        self.quote_count: int = kwargs.pop("quote_count", 0)
        self.reply_count: int = kwargs.pop("reply_count", 0)
        self.favorite_count: int = kwargs.pop("favorite_count", 0)
        self.favorited: bool = kwargs.pop("favorited", False)
        self.view_count: str = kwargs.pop("view_count", "")
        self.retweet_count: int = kwargs.pop("retweet_count", 0)
        self.editable_until_msecs: Optional[str] = kwargs.pop("editable_until_msecs", "")
        self.is_translatable: bool = kwargs.pop("is_translatable", False)
        self.is_edit_eligible: bool = kwargs.pop("is_edit_eligible", True)
        self.edits_remaining: Optional[str] = kwargs.pop("edits_remaining", "")
        self.unix: float = kwargs.pop("unix", 0.0)
        self.url: str = kwargs.pop("url", "")
        self.media: List[dict] = kwargs.pop("media", [])
        self._kwargs = kwargs
        # For everything else that may be added in the future

    @property
    def time(self) -> datetime:
        return datetime.fromtimestamp(self.unix, tz=timezone.utc)


class BungieXAccount(Enum):
    BungieHelp = "BungieHelp"
    DestinyTheGame = "DestinyTheGame"
    Destiny2Team = "Destiny2Team"

    @property
    def path(self):
        return f"{self.value}.json"


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
    ResultCountThisPage: int
    NewsArticles: List[NewsArticle]
    PagerAction: str
    NextPaginationToken: Optional[int] = None
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
    Unknown = 0
    Story = 2
    Strike = 3
    Raid = 4
    AllPvP = 5
    Patrol = 6
    AllPvE = 7
    Reserved9 = 9
    Control = 10
    Reserved11 = 11
    Clash = 12
    # Clash  -> Destiny's name for Team Deathmatch. 4v4 combat, the team with the highest kills at the end of time wins.
    Reserved13 = 13
    CrimsonDoubles = 15
    Nightfall = 16
    HeroicNightfall = 17
    AllStrikes = 18
    IronBanner = 19
    Reserved20 = 20
    Reserved21 = 21
    Reserved22 = 22
    Reserved24 = 24
    AllMayhem = 25
    Reserved26 = 26
    Reserved27 = 27
    Reserved28 = 28
    Reserved29 = 29
    Reserved30 = 30
    Supremacy = 31
    PrivateMatchesAll = 32
    Survival = 37
    Countdown = 38
    TrialsOfTheNine = 39
    Social = 40
    TrialsCountdown = 41
    TrialsSurvival = 42
    IronBannerControl = 43
    IronBannerClash = 44
    IronBannerSupremacy = 45
    ScoredNightfall = 46
    ScoredHeroicNightfall = 47
    Rumble = 48
    AllDoubles = 49
    Doubles = 50
    PrivateMatchesClash = 51
    PrivateMatchesControl = 52
    PrivateMatchesSupremacy = 53
    PrivateMatchesCountdown = 54
    PrivateMatchesSurvival = 55
    PrivateMatchesMayhem = 56
    PrivateMatchesRumble = 57
    HeroicAdventure = 58
    Showdown = 59
    Lockdown = 60
    Scorched = 61
    ScorchedTeam = 62
    Gambit = 63
    AllPvECompetitive = 64
    Breakthrough = 65
    BlackArmoryRun = 66
    Salvage = 67
    IronBannerSalvage = 68
    PvPCompetitive = 69
    PvPQuickplay = 70
    ClashQuickplay = 71
    ClashCompetitive = 72
    ControlQuickplay = 73
    ControlCompetitive = 74
    GambitPrime = 75
    Reckoning = 76
    Menagerie = 77
    VexOffensive = 78
    NightmareHunt = 79
    Elimination = 80
    Momentum = 81
    Dungeon = 82
    Sundial = 83
    TrialsOfOsiris = 84
    Dares = 85
    Offensive = 86
    LostSector = 87
    Rift = 88
    ZoneControl = 89
    IronBannerRift = 90
    IronBannerZoneControl = 91


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


class BungieMembershipType(Enum):
    All = -1
    Unknown = 0
    TigerXbox = 1
    TigerPsn = 2
    TigerSteam = 3
    TigerBlizzard = 4
    TigerStadia = 5
    TigerEgs = 6
    TigerDemon = 10
    BungieNext = 254

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return {
            BungieMembershipType.All: _("All"),
            BungieMembershipType.Unknown: _("Unknown"),
            BungieMembershipType.TigerXbox: _("Xbox"),
            BungieMembershipType.TigerPsn: _("Playstation"),
            BungieMembershipType.TigerSteam: _("Steam"),
            BungieMembershipType.TigerBlizzard: _("Blizzard"),
            BungieMembershipType.TigerStadia: _("Stadia"),
            BungieMembershipType.TigerEgs: _("Epic Games"),
            BungieMembershipType.TigerDemon: _("Demon"),
            BungieMembershipType.BungieNext: _("BungieNext"),
        }[self]


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


class DestinyActivity(discord.app_commands.Transformer):
    """Returns the correct history code if provided a named one"""

    async def convert(self, ctx: commands.Context, argument: str) -> DestinyActivityModeType:
        if argument.isdigit():
            try:
                return DestinyActivityModeType(int(argument))
            except ValueError:
                raise BadArgument(
                    _(
                        "That is not an available activity, pick from these: {activity_list}"
                    ).format(
                        activity_list=humanize_list(list(i.name for i in DestinyActivityModeType))
                    )
                )
        for activity in DestinyActivityModeType:
            if activity.name.lower() == argument.lower():
                return activity
        return DestinyActivityModeType.Unknown

    async def transform(
        self, interaction: discord.Interaction, argument: str
    ) -> DestinyActivityModeType:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(self, interaction: discord.Interaction, current: str):
        possible_options = [
            discord.app_commands.Choice(name=i.name, value=str(i.value))
            for i in DestinyActivityModeType
        ]
        choices = []
        for choice in possible_options:
            if current.lower() in choice.name.lower():
                choices.append(discord.app_commands.Choice(name=choice.name, value=choice.value))
        return choices[:25]


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
