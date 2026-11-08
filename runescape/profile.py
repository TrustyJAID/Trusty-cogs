from __future__ import annotations

import bisect
import json
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, NamedTuple, Optional

import aiohttp
import discord
from red_commons.logging import getLogger
from redbot.core.utils.chat_formatting import humanize_number, pagify
from tabulate import tabulate

from .helpers import HEADERS, IMAGE_URL
from .xp import ELITE_XP, XP_TABLE

log = getLogger("red.trusty-cogs.runescape")

LVL_RE = re.compile(r"Levelled Up (\w+)", flags=re.I)
XP_RE = re.compile(r"(?P<xp>\d+)XP IN (.+)", flags=re.I)
KILLED_RE = re.compile(r"(?:I )?(?:killed|defeated) (?:\d+ |the )?([a-z \-,]+)", flags=re.I)
FOUND_RE = re.compile(r"I found (?:a pair of|some|a|an) (.+)", flags=re.I)


class APIError(Exception):
    pass


class PrivateProfileError(APIError):
    pass


class PlayerID(NamedTuple):
    id: int
    name: str


@dataclass
class HiScorePlayer:
    id: int
    bossId: int
    size: int
    rank: int
    enrage: int
    killTimeSeconds: float
    timeOfKill: int
    members: List[PlayerID]

    @classmethod
    def from_json(cls, data: dict) -> HiScorePlayer:
        members = [PlayerID(**i) for i in data.pop("members", [])]
        return cls(members=members, **data)


@dataclass
class ZamorakHiScores:
    content: List[HiScorePlayer]
    totalElements: int
    totalPages: int
    first: bool
    last: bool
    numberOfElements: int
    number: int
    size: int
    empty: bool
    url: str = "https://secure.runescape.com/m=group_hiscores/v1//groups?groupSize={groupSize}&size={size}&bossId=1&page={page}"

    @classmethod
    def from_json(cls, data: dict) -> ZamorakHiScores:
        content = [HiScorePlayer.from_json(i) for i in data.pop("content", [])]
        return cls(content=content, **data)

    @classmethod
    async def get(
        cls,
        groupSize: int,
        size: int,
        page: int,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> ZamorakHiScores:
        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(
                    cls.url.format(groupSize=groupSize, size=size, page=page)
                ) as resp:
                    if resp.status != 200:
                        raise APIError
                    data = await resp.json()
        else:
            async with session.get(
                cls.url.format(groupSize=groupSize, size=size, page=page)
            ) as resp:
                if resp.status != 200:
                    raise APIError
                data = await resp.json()
        return cls.from_json(data)


class Activities:
    def __init__(self, *args, **kwargs):
        self.channels: Dict[str, int] = kwargs.get("channels", {})
        self.last_id: str = kwargs.get("last_id", "")
        self.last_timestamp = kwargs.get("last_timestamp")
        self.username: str = kwargs.get("username", "")
        self.posted_activities: deque = deque(kwargs.get("posted_activities", []), 40)

    def to_json(self) -> dict:
        return {
            "channels": self.channels,
            "last_id": self.last_id,
            "last_timestamp": self.last_timestamp,
            "username": self.username,
            "posted_activities": list(self.posted_activities),
        }


@dataclass
class PlayerDetails:
    isSuffix: bool
    name: str
    title: str
    recruiting: Optional[bool] = None
    clan: Optional[str] = None
    online: Optional[bool] = False
    world: Optional[str] = None

    @classmethod
    def from_str(cls, data_str: str) -> PlayerDetails:
        try:
            data = json.loads(
                data_str.replace("jQuery000000000000000_0000000000([", "").replace("]);", "")
            )
        except Exception:
            log.exception("Error pulling player details")
            raise APIError
        return cls(**data)

    @classmethod
    async def get(
        cls, runescape_name: str, *, session: Optional[aiohttp.ClientSession] = None
    ) -> PlayerDetails:
        url = f"https://secure.runescape.com/m=website-data/playerDetails.ws?names=%5B%22{runescape_name}%22%5D&callback=jQuery000000000000000_0000000000&_=0.format"
        close_session = session is None
        if session is None:
            session = aiohttp.ClientSession(headers=HEADERS)
        async with session.get(url) as resp:
            if resp.status != 200:
                raise APIError
            data = await resp.text()
        if close_session:
            await session.close()
        return cls.from_str(data)


class PlogType(Enum):
    UNKNOWN = "unknown_plog_type"
    XP_MILESTONE = "rs_plog_xp_milestone"
    LEVELUP_COUNT = "rs_plog_levelup_count"
    LEVELUP_ALL_MILESTONE = "rs_plog_levelup_all_milestone"
    LEVELUP_TOTAL_MILESTONE = "rs_plog_levelup_total_milestone"
    ITEM_DROP = "rs_plog_item_drop"
    NPC_KILL_COUNT = "rs_plog_npc_kill_count"
    NPC_DEFEAT = "rs_plog_npc_defeat"
    ITEM_FOUND = "rs_plog_item_found"
    ITEM_FOUND_NOWHERE = "rs_plog_item_found_nowhere"
    QUEST = "rs_plog_quest"
    QP_MILESTONE = "rs_plog_qp_milestone"
    CHAMPIONS_CHALLENGE = "rs_plog_champions_challenge"
    COURTCASE = "rs_plog_courtcase"
    FINISHED_TRAIL = "rs_plog_finished_trail"
    DUNGEONS_DEEPEST_LEVEL = "rs_plog_dungeons_deepest_level"
    DUNGEONS_BOSS_KILLS = "rs_plog_dungeons_boss_kills"
    DUNGEONS_FOUND_BOOK = "rs_plog_dungeons_found_book"
    MUSIC_MILESTONE = "rs_plog_music_milestone"
    SPECIAL_EVENT = "rs_plog_special_event"
    # Depracated evnents that might still show up
    LEVEL_UPS = "rs_plog_levelup"
    NPC_KILLS = "rs_plog_npc_kill"
    PVP_KILL = "rs_plog_pvp_kill"
    HOLIDAY_EVENTS = "rs_plog_events"
    TREASURE_HUNTER_DROP = "rs_plog_wof_drop"
    DUNGEONEERING_TOKEN_SPENT = "rs_plog_dungeons_spend_token"

    @classmethod
    def from_str(cls, data: str):
        try:
            return PlogType(data)
        except ValueError:
            return PlogType.UNKNOWN


@dataclass
class PlayerEvent:
    date: datetime
    details: str
    text: str
    type: PlogType
    id: str

    @classmethod
    def from_json(cls, data: dict):
        plog_type = data.pop("type", "unknown_plog_type")
        try:
            date_str = data.pop("date").replace("Z", "+00:00")
            date = datetime.fromisoformat(date_str)
        except (ValueError, KeyError, TypeError):
            log.exception("Error getting date from data")
            date = datetime.now(tz=timezone.utc)
        event_text = data.get("text", "")
        event_id = f"{int(date.timestamp())}-{event_text}"

        return cls(**data, date=date, type=PlogType.from_str(plog_type), id=event_id)

    def _get_image_details_text(self):
        text = self.text
        details = self.details
        image_url = None
        page = None
        if match := KILLED_RE.search(self.text):
            page = match.group(1).strip()
            if page.endswith("s"):
                page = page[:-1]
            page = page.replace(" ", "_")
            if "-" in page:
                page = page.title()
            else:
                page = page.capitalize()
            image_url = IMAGE_URL + page + ".png"
        if match := XP_RE.search(self.text):
            page = match.group(2).strip()
            if xp := match.group("xp"):
                number = humanize_number(int(xp))
                text = self.text.replace(xp, number)
                details = self.details.replace(xp, number)
            image_url = IMAGE_URL + page.replace(" ", "_").capitalize() + ".png"
        if match := LVL_RE.search(self.text):
            page = match.group(1).strip()
            image_url = IMAGE_URL + page.replace(" ", "_").capitalize() + ".png"
        if match := FOUND_RE.search(self.text):
            page = match.group(1).strip() + " detail"
            image_url = IMAGE_URL + page.replace(" ", "_").capitalize() + ".png"
        return text, details, image_url

    def format_text(self) -> str:
        text, details, _image_url = self._get_image_details_text()
        ts = discord.utils.format_dt(self.date)
        return f"- {text}\n  - {details}\n  - -# {ts}\n"

    def embed(self, username: str) -> discord.Embed:
        # url = f"https://apps.runescape.com/runemetrics/app/overview/player/{profile.name}"
        # msg = f"{profile.name}: {activity.text}\n{activity.details}\n\n"
        ts = discord.utils.format_dt(self.date)
        text, details, image_url = self._get_image_details_text()
        embed = discord.Embed(title=text, description=f"{details}\n\n{ts}")
        name_url = username.replace(" ", "%20")
        avatar = f"http://secure.runescape.com/m=avatar-rs/{name_url}/chat.png"
        embed.set_author(name=username, icon_url=avatar)
        if image_url is not None:
            embed.set_thumbnail(url=image_url)
        return embed


@dataclass
class PlayerEvents:
    name: str
    events: List[PlayerEvent]

    @property
    def avatar(self) -> str:
        name_url = self.name.replace(" ", "%20")
        return f"http://secure.runescape.com/m=avatar-rs/{name_url}/chat.png"

    @classmethod
    def from_json(cls, data: dict):
        name = data.get("name", "")
        events = [PlayerEvent.from_json(e) for e in data.get("events", [])]
        return cls(name=name, events=events)

    @classmethod
    async def get(
        cls,
        runescape_name: str,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> PlayerEvents:
        url = (
            f"https://secure.runescape.com/m=adventurers-log/api/v1/playerEvents/{runescape_name}"
        )
        close_session = session is None
        if session is None:
            session = aiohttp.ClientSession(headers=HEADERS)
        async with session.get(url) as resp:
            if resp.status != 200:
                raise APIError
            data = await resp.json()
        if close_session:
            await session.close()
        if "error" in data:
            if data["error"] == "PROFILE_PRIVATE":
                raise PrivateProfileError(data["error"])
            else:
                raise APIError(data["error"])
        return cls.from_json(data)

    def embed(self) -> discord.Embed:
        em = discord.Embed(title="Adventure Log")
        em.set_author(name=self.name, icon_url=self.avatar)
        em.set_thumbnail(url=self.avatar)
        desc = ""
        for event in self.events:
            to_add = event.format_text()
            if len(desc) + len(to_add) < 1024:
                desc += to_add
            else:
                break
        em.description = desc
        return em


class HiscoreInstance(Enum):
    # RS3
    HISCORE = "hiscore"
    HISCORE_IRONMAN = "hiscore_ironman"
    HISCORE_HARDCORE_IRONMAN = "hiscore_hardcore_ironman"
    HISCORE_LEAGUE = "hiscore_leagues"
    # OSRS
    HISCORE_OLDSCHOOL = "hiscore_oldschool"
    HISCORE_OLDSCHOOL_SKILLER_DEFENCE = "hiscore_oldschool_skiller_defence"
    HISCORE_OLDSCHOOL_SKILLER = "hiscore_oldschool_skiller"
    HISCORE_OLDSCHOOL_IRONMAN = "hiscore_oldschool_ironman"
    HISCORE_OLDSCHOOL_HARDCORE_IRONMAN = "hiscore_oldschool_hardcore_ironman"
    HISCORE_OLDSCHOOL_UTMIATE = "hiscore_oldschool_ultimate"
    HISCORE_OLDSCHOOL_HARDCORE_MAINS = "hiscore_oldschool_hardcore_mains"
    HISCORE_OLDSCHOOL_DEADMAN = "hiscore_oldschool_deadman"
    HISCORE_OLDSCHOOL_SEASONAL = "hiscore_oldschool_seasonal"
    HISCORE_OLDSCHOOL_TOURNAMENT = "hiscore_oldschool_tournament"
    HISCORE_OLDSCHOOL_FRESH_START = "hiscore_oldschool_fresh_start"

    @property
    def is_rs3(self) -> bool:
        return "oldschool" not in self.value

    @property
    def to_str(self) -> str:
        game = "RS3" if self.is_rs3 else "OSRS"
        name_str = " ".join(self.value.replace("_", " ").replace("oldschool", "").title().split())
        return f"{game} {name_str}"


class HiscoreSkill(NamedTuple):
    id: int
    name: str
    rank: int
    level: int
    xp: int

    def __str__(self):
        return self.name

    @property
    def virtual_level(self) -> int:
        if self.level < 99:
            return self.level
        table = XP_TABLE
        max_level = 126
        if self.name == "Invention":
            table = ELITE_XP
            max_level = 150
        idx = bisect.bisect_right(table, self.xp, lo=98)
        # Since the xp list is already sorted we can bisect and
        # do a binary search for where our xp fits in the level brackets.
        # Since we only care about levels above 99
        # the lo sets the lowest index to start looking
        return min(idx, max_level)


class HiscoreActivity(NamedTuple):
    id: int
    name: str
    rank: int
    score: int

    def __str__(self):
        return self.name


@dataclass
class HiscoreProfile:
    def __init__(
        self,
        name: str,
        skills: Dict[int, HiscoreSkill],
        activities: Dict[int, HiscoreActivity],
        instance: HiscoreInstance,
    ):
        self.skills: Dict[int, HiscoreSkill] = skills
        self.activities: Dict[int, HiscoreActivity] = activities
        self.name: str = name
        self.instance = instance

    def get_skill(self, skill_name: str) -> Optional[HiscoreSkill]:
        for skill in self.skills.values():
            if skill.name == skill_name:
                return skill
        return None

    def get_activity(self, activity_name: str) -> Optional[HiscoreActivity]:
        for activity in self.activities.values():
            if activity.name == activity_name:
                return activity
        return None

    @classmethod
    async def get(
        cls,
        runescape_name: str,
        instance: HiscoreInstance,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> HiscoreProfile:
        url = f"https://secure.runescape.com/m={instance.value}/index_lite.json"
        close_session = session is None
        params = {"player": runescape_name}
        if session is None:
            session = aiohttp.ClientSession(headers=HEADERS)
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise APIError
            data = await resp.json()
        if close_session:
            await session.close()
        skills = {}
        activities = {}
        for skill in data.get("skills", []):
            skills[skill["id"]] = HiscoreSkill(**skill)
        for activity in data.get("activities", []):
            activities[activity["id"]] = HiscoreActivity(**activity)
        return cls(runescape_name, skills, activities, instance)

    async def get_stats_table(self) -> str:
        skills_list = []
        for skill in self.skills.values():
            skill_level = skill.level
            if skill.level != skill.virtual_level and skill.id != 0:
                skill_level = f"{skill.level} ({skill.virtual_level})"
            skills_list.append(
                [
                    skill.name,
                    skill_level,
                    humanize_number(skill.xp),
                    humanize_number(skill.rank),
                ]
            )
        table = tabulate(skills_list, headers=["Skill", "Level", "Experience", "Rank"])
        top_row_len = len(table.split("\n")[1])
        top_row = top_row_len * "-"
        title = f"{self.instance.to_str} For {self.name}"
        skills = f"{top_row}\n"
        for page in pagify(title, delims=[" "], page_length=top_row_len - 2):
            skills += f"|{page.center(top_row_len - 2)}|\n"
        skills += f"{top_row}\n{table}\n{top_row}"
        return skills

    async def get_profile_table(self) -> str:
        activities_list = []
        for activity in self.activities.values():
            activities_list.append([activity.name, humanize_number(activity.score)])
        table = tabulate(activities_list, headers=["Activity", "Completed"])
        top_row_len = len(table.split("\n")[1])
        top_row = top_row_len * "-"
        title = f"{self.instance.to_str} For {self.name}"
        skills = f"{top_row}\n"
        for page in pagify(title, delims=[" "], page_length=top_row_len - 2):
            skills += f"|{page.center(top_row_len - 2)}|\n"
        skills += f"{top_row}\n{table}\n{top_row}"
        return skills
