from typing import List

from tabulate import tabulate


class Profile:
    def __init__(
        self,
        name: str,
        combatlevel: int,
        logged_in: bool,
        rank: int,
        melee_total: int,
        magic_total: int,
        ranged_total: int,
        totalskill: int,
        totalxp: int,
        questsstarted: int,
        questscomplete: int,
        questsnotstarted: int,
        activities: list,
        attack: dict,
        defence: dict,
        strength: dict,
        constitution: dict,
        ranged: dict,
        prayer: dict,
        magic: dict,
        cooking: dict,
        woodcutting: dict,
        fletching: dict,
        fishing: dict,
        firemaking: dict,
        crafting: dict,
        smithing: dict,
        mining: dict,
        herblore: dict,
        agility: dict,
        thieving: dict,
        slayer: dict,
        farming: dict,
        runecrafting: dict,
        hunter: dict,
        construction: dict,
        summoning: dict,
        dungeoneering: dict,
        divination: dict,
        invention: dict,
        archaeology: dict,
    ):
        super().__init__()
        self.name = name
        self.combatlevel = combatlevel
        self.logged_in = logged_in
        self.rank = rank
        self.melee_total = melee_total
        self.magic_total = magic_total
        self.ranged_total = ranged_total
        self.totalskill = totalskill
        self.totalxp = totalxp
        self.questsstarted = questsstarted
        self.questscomplete = questscomplete
        self.questsnotstarted = questsnotstarted
        self.activities = activities
        self.attack = attack
        self.defence = defence
        self.strength = strength
        self.constitution = constitution
        self.ranged = ranged
        self.prayer = prayer
        self.magic = magic
        self.cooking = cooking
        self.woodcutting = woodcutting
        self.fletching = fletching
        self.fishing = fishing
        self.firemaking = firemaking
        self.crafting = crafting
        self.smithing = smithing
        self.mining = mining
        self.herblore = herblore
        self.agility = agility
        self.thieving = thieving
        self.slayer = slayer
        self.farming = farming
        self.runecrafting = runecrafting
        self.hunter = hunter
        self.construction = construction
        self.summoning = summoning
        self.dungeoneering = dungeoneering
        self.divination = divination
        self.invention = invention
        self.archaeology = archaeology

    def __str__(self):
        skills_list = [["Overall", self.totalskill, "{:,}".format(self.totalxp), self.rank]]
        skills: List[str] = [
            "Attack",
            "Defence",
            "Strength",
            "Constitution",
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
            "Summoning",
            "Dungeoneering",
            "Divination",
            "Invention",
            "Archaeology",
        ]
        stats = self.to_json()
        for skill in skills:
            if skill.lower() not in stats:
                continue
            level = stats[skill.lower()]["level"]
            xp = stats[skill.lower()]["xp"]
            rank = stats[skill.lower()]["rank"] if "rank" in stats[skill.lower()] else "Unranked"
            skills_list.append([skill, level, xp, rank])
        return tabulate(
            skills_list, headers=["Skill", "Level", "Experience", "Rank"], tablefmt="orgtbl"
        )

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
        skill_id_conversion = {
            "0": "Attack",
            "1": "Defence",
            "2": "Strength",
            "3": "Constitution",
            "4": "Ranged",
            "5": "Prayer",
            "6": "Magic",
            "7": "Cooking",
            "8": "Woodcutting",
            "9": "Fletching",
            "10": "Fishing",
            "11": "Firemaking",
            "12": "Crafting",
            "13": "Smithing",
            "14": "Mining",
            "15": "Herblore",
            "16": "Agility",
            "17": "Thieving",
            "18": "Slayer",
            "19": "Farming",
            "20": "Runecrafting",
            "21": "Hunter",
            "22": "Construction",
            "23": "Summoning",
            "24": "Dungeoneering",
            "25": "Divination",
            "26": "Invention",
            "27": "Archaeology",
        }

        def get_skill(skill_id):
            for skill in data["skillvalues"]:
                if skill["id"] == skill_id:
                    skill["name"] = skill_id_conversion[str(skill_id)]
                    return skill

        logged_in = True if data["loggedIn"] == "true" else False

        return cls(
            data["name"],
            data["combatlevel"],
            logged_in,
            data["rank"],
            data["melee"],
            data["magic"],
            data["ranged"],
            data["totalskill"],
            data["totalxp"],
            data["questsstarted"],
            data["questscomplete"],
            data["questsnotstarted"],
            data["activities"],
            get_skill(0),
            get_skill(1),
            get_skill(2),
            get_skill(3),
            get_skill(4),
            get_skill(5),
            get_skill(6),
            get_skill(7),
            get_skill(8),
            get_skill(9),
            get_skill(10),
            get_skill(11),
            get_skill(12),
            get_skill(13),
            get_skill(14),
            get_skill(15),
            get_skill(16),
            get_skill(17),
            get_skill(18),
            get_skill(19),
            get_skill(20),
            get_skill(21),
            get_skill(22),
            get_skill(23),
            get_skill(24),
            get_skill(25),
            get_skill(26),
            get_skill(27),
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
