from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import pytz
from redbot.core.utils.chat_formatting import humanize_number
from tabulate import tabulate


class Skills(Enum):
    Attack = 0
    Defence = 1
    Strength = 2
    Constitution = 3
    Ranged = 4
    Prayer = 5
    Magic = 6
    Cooking = 7
    Woodcutting = 8
    Fletching = 9
    Fishing = 10
    Firemaking = 11
    Crafting = 12
    Smithing = 13
    Mining = 14
    Herblore = 15
    Agility = 16
    Thieving = 17
    Slayer = 18
    Farming = 19
    Runecrafting = 20
    Hunter = 21
    Construction = 22
    Summoning = 23
    Dungeoneering = 24
    Divination = 25
    Invention = 26
    Archaeology = 27


class Item:
    def __init__(self, *args, **kwargs):
        self.id = kwargs.get("id")
        self.icon = kwargs.get("icon")
        self.icon_large = kwargs.get("icon_large")
        self.type = kwargs.get("type")
        self.type_icon = kwargs.get("type_icon")
        self.name = kwargs.get("name")
        self.description = kwargs.get("description")
        self.members = kwargs.get("members")
        self.trend = kwargs.get("trend")
        self.price = kwargs.get("price")
        self.change = kwargs.get("change")
        self.current = kwargs.get("current")
        self.today = kwargs.get("today")
        self.day30 = kwargs.get("day30")
        self.day90 = kwargs.get("day90")
        self.day180 = kwargs.get("day180")


@dataclass
class Activity:
    date: datetime
    details: str
    text: str
    id: str

    @classmethod
    def from_json(cls, data: dict):
        tz = pytz.timezone("Europe/London")
        date = datetime.strptime(data.get("date"), "%d-%b-%Y %H:%M")
        date = tz.localize(date, is_dst=None).astimezone(timezone.utc)
        text = data.get("text")
        activity_id = f"{int(date.timestamp())}-{text}"
        return cls(
            date=date,
            details=data.get("details"),
            text=text,
            id=activity_id,
        )


class Activities:
    def __init__(self, *args, **kwargs):
        self.channels = kwargs.get("channels")
        self.last_id: str = kwargs.get("last_id")
        self.last_timestamp = kwargs.get("last_timestamp")
        self.username: str = kwargs.get("username")
        self.posted_activities: deque = deque(kwargs.get("posted_activities", []), 40)

    def to_json(self):
        return {
            "channels": self.channels,
            "last_id": self.last_id,
            "last_timestamp": self.last_timestamp,
            "username": self.username,
            "posted_activities": list(self.posted_activities),
        }


@dataclass
class Skill:
    level: int
    xp: int
    rank: int
    id: int
    name: str

    @classmethod
    def from_json(cls, data: dict):
        return cls(
            level=data.get("level", 1),
            xp=int(data.get("xp", 1) * 0.1),
            rank=data.get("rank", 0),
            id=data.get("id"),
            name=Skills(int(data.get("id"))).name,
        )


class Profile:
    def __init__(self, **kwargs):
        self.name = kwargs.get("name")
        self.combatlevel = kwargs.get("combatlevel")
        self.logged_in = kwargs.get("logged_in")
        self.rank = kwargs.get("rank")
        self.melee_total = kwargs.get("melee_total")
        self.magic_total = kwargs.get("magic_total")
        self.ranged_total = kwargs.get("ranged_total")
        self.totalskill = kwargs.get("totalskill")
        self.totalxp = kwargs.get("totalxp")
        self.questsstarted = kwargs.get("questsstarted")
        self.questscomplete = kwargs.get("questscomplete")
        self.questsnotstarted = kwargs.get("questsnotstarted")
        self.activities = kwargs.get("activities")
        self.attack: Skill = kwargs.get("attack")
        self.defence: Skill = kwargs.get("defence")
        self.strength: Skill = kwargs.get("strength")
        self.constitution: Skill = kwargs.get("constitution")
        self.ranged: Skill = kwargs.get("ranged")
        self.prayer: Skill = kwargs.get("prayer")
        self.magic: Skill = kwargs.get("magic")
        self.cooking: Skill = kwargs.get("cooking")
        self.woodcutting: Skill = kwargs.get("woodcutting")
        self.fletching: Skill = kwargs.get("fletching")
        self.fishing: Skill = kwargs.get("fishing")
        self.firemaking: Skill = kwargs.get("firemaking")
        self.crafting: Skill = kwargs.get("crafting")
        self.smithing: Skill = kwargs.get("smithing")
        self.mining: Skill = kwargs.get("mining")
        self.herblore: Skill = kwargs.get("herblore")
        self.agility: Skill = kwargs.get("agility")
        self.thieving: Skill = kwargs.get("thieving")
        self.slayer: Skill = kwargs.get("slayer")
        self.farming: Skill = kwargs.get("farming")
        self.runecrafting: Skill = kwargs.get("runecrafting")
        self.hunter: Skill = kwargs.get("hunter")
        self.construction: Skill = kwargs.get("construction")
        self.summoning: Skill = kwargs.get("summoning")
        self.dungeoneering: Skill = kwargs.get("dungeoneering")
        self.divination: Skill = kwargs.get("divination")
        self.invention: Skill = kwargs.get("invention")
        self.archaeology: Skill = kwargs.get("archaeology")

    def __str__(self):
        skills_list = [["Overall", self.totalskill, "{:,}".format(self.totalxp), self.rank]]
        for skill_name in Skills:
            skill = getattr(self, skill_name.name.lower(), None)
            if not skill:
                level = 1
                xp = 0
                rank = "Unranked"
                skills_list.append([skill_name, level, xp, rank])
                continue
            level = skill.level
            xp = skill.xp
            rank = "Unranked"
            if skill.rank:
                rank = humanize_number(skill.rank)
            skills_list.append([skill.name, level, humanize_number(xp), rank])
        return tabulate(skills_list, headers=["Skill", "Level", "Experience", "Rank"])

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "combatlevel": self.combatlevel,
            "logged_in": self.logged_in,
            "rank": self.rank,
            "melee_total": self.melee_total,
            "magic_total": self.magic_total,
            "ranged_total": self.ranged_total,
            "totalskill": self.totalskill,
            "totalxp": self.totalxp,
            "questsstarted": self.questsstarted,
            "questscomplete": self.questscomplete,
            "questsnotstarted": self.questsnotstarted,
            "activities": self.activities,
            "attack": self.attack,
            "defence": self.defence,
            "strength": self.strength,
            "constitution": self.constitution,
            "ranged": self.ranged,
            "prayer": self.prayer,
            "magic": self.magic,
            "cooking": self.cooking,
            "woodcutting": self.woodcutting,
            "fletching": self.fletching,
            "fishing": self.fishing,
            "firemaking": self.firemaking,
            "crafting": self.crafting,
            "smithing": self.smithing,
            "mining": self.mining,
            "herblore": self.herblore,
            "agility": self.agility,
            "thieving": self.thieving,
            "slayer": self.slayer,
            "farming": self.farming,
            "runecrafting": self.runecrafting,
            "hunter": self.hunter,
            "construction": self.construction,
            "summoning": self.summoning,
            "dungeoneering": self.dungeoneering,
            "divination": self.divination,
            "invention": self.invention,
            "archaeology": self.archaeology,
        }

    @classmethod
    async def from_json(cls, data: dict):
        def get_skill(skill_id):
            for skill in data["skillvalues"]:
                if skill["id"] == skill_id:
                    return Skill.from_json(skill)

        logged_in = True if data["loggedIn"] == "true" else False

        return cls(
            name=data["name"],
            combatlevel=data["combatlevel"],
            logged_in=logged_in,
            rank=data["rank"],
            melee_total=data["melee"],
            magic_total=data["magic"],
            ranged_total=data["ranged"],
            totalskill=data["totalskill"],
            totalxp=data["totalxp"],
            questsstarted=data["questsstarted"],
            questscomplete=data["questscomplete"],
            questsnotstarted=data["questsnotstarted"],
            activities=[Activity.from_json(i) for i in data["activities"]],
            attack=get_skill(0),
            defence=get_skill(1),
            strength=get_skill(2),
            constitution=get_skill(3),
            ranged=get_skill(4),
            prayer=get_skill(5),
            magic=get_skill(6),
            cooking=get_skill(7),
            woodcutting=get_skill(8),
            fletching=get_skill(9),
            fishing=get_skill(10),
            firemaking=get_skill(11),
            crafting=get_skill(12),
            smithing=get_skill(13),
            mining=get_skill(14),
            herblore=get_skill(15),
            agility=get_skill(16),
            thieving=get_skill(17),
            slayer=get_skill(18),
            farming=get_skill(19),
            runecrafting=get_skill(20),
            hunter=get_skill(21),
            construction=get_skill(22),
            summoning=get_skill(23),
            dungeoneering=get_skill(24),
            divination=get_skill(25),
            invention=get_skill(26),
            archaeology=get_skill(27),
        )

    @classmethod
    async def from_text(cls, data: str):
        order = [
            "Overall",
            "Attack",
            "Defence",
            "Strength",
            "Hitpoints",
            "Ranged",
            "Prayer",
            "Magic",
            "Cooking",
            "Woodcutting",
            "Fletching",
            "Fishing",
            "Firemaking",
            "Crafting",
            "Smithing",
            "Mining",
            "Herblore",
            "Agility",
            "Thieving",
            "Slayer",
            "Farming",
            "Runecrafting",
            "Hunter",
            "Construction",
            "Bounty Hunter - Hunter",
            "Bounty Hunter - Rogues",
            "Clue Scrolls All",
            "Clue Scrolls Easy",
            "Clue Scrolls Medium",
            "Clue Scrolls Hard",
            "Clue Scrolls Elite",
            "Clue Scrolls Master",
            "LMS Rank",
        ]
        skills_list = []
        for line in enumerate(data.decode().split("\n")):
            try:
                xp = line[1].split(",")[2]
                rank = line[1].split(",")[0]
                level = line[1].split(",")[1]
                skills_list.append([order[line[0]], level, xp, rank])
            except Exception:
                pass
        return tabulate(
            skills_list, headers=["Skill", "Level", "Experience", "Rank"], tablefmt="orgtbl"
        )
