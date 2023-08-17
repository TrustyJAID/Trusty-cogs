from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

import discord

from .helpers import IMAGE_URL, get_runedate
from .rsrandom import JavaRandom


class Runes(Enum):
    air = 0
    water = 1
    earth = 2
    fire = 3
    dust = 4
    lava = 5
    mist = 6
    mud = 7
    smoke = 8
    steam = 9
    mind = 10
    body = 11
    cosmic = 12
    chaos = 13
    nature = 14
    law = 15
    death = 16
    astral = 17
    blood = 18
    soul = 19

    @property
    def image(self):
        return f"{IMAGE_URL}{self.name.title()}_rune.png"

    @property
    def cost(self) -> int:
        """
        Amount of runes for each selection on the machine

        Only really useful for calculating effective cost
        """
        return {
            Runes.air: 1000,
            Runes.water: 1000,
            Runes.earth: 1000,
            Runes.fire: 1000,
            Runes.dust: 500,
            Runes.lava: 500,
            Runes.mist: 500,
            Runes.mud: 300,
            Runes.smoke: 500,
            Runes.steam: 500,
            Runes.mind: 2000,
            Runes.body: 2000,
            Runes.cosmic: 400,
            Runes.chaos: 500,
            Runes.nature: 350,
            Runes.law: 300,
            Runes.death: 400,
            Runes.astral: 300,
            Runes.blood: 350,
            Runes.soul: 300,
        }[self]


class RuneGoldberg:
    def __init__(self, *, runedate: Optional[float] = None, date_time: Optional[datetime] = None):
        if runedate is None:
            runedate = get_runedate(date_time)

        self.slot1: Runes = self.get_slot1(int(runedate))
        self.slot2: List[Runes] = self.get_slot2(int(runedate))
        self.runedate = runedate

    def __str__(self):
        today = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        daily = today + timedelta(hours=((0 - today.hour) % 24))
        timestamp = discord.utils.format_dt(daily, "R")
        msg = "## [Rune Goldberg Machine](https://runescape.wiki/w/Rune_Goldberg_Machine)\n"
        msg += f"Refreshes {timestamp}\n"
        msg += f"- Slot 1:\n - {self.slot1.name.title()} Rune ({self.slot1.cost})\n"
        msg += "- Slot 2:\n"
        for r in self.slot2:
            msg += f" - {r.name.title()} Rune ({r.cost})\n"
        msg += "https://runescape.wiki/w/Rune_Goldberg_Machine"
        return msg

    def get_slot1(self, runedate: int) -> Runes:
        return Runes(JavaRandom(int(runedate) << 32).next_int(19) % 19)

    def get_slot2(self, runedate: int) -> List[Runes]:
        slot_2_params = [[2, -2], [3, -1], [4, 2]]
        slot_2_best = []
        for slot in slot_2_params:
            multiplier = slot[0]
            final_offset = slot[1]
            rng = JavaRandom(multiplier * (int(runedate) << 32)).next_int(19)
            rune_index = (rng + final_offset + 19) % 19
            if rune_index == self.slot1.value:
                rune_index += 1
            rune = Runes(rune_index)
            slot_2_best.append(rune)
        return slot_2_best

    def embed(self) -> discord.Embed:
        today = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        daily = today + timedelta(hours=((0 - today.hour) % 24))
        timestamp = discord.utils.format_dt(daily, "R")
        em = discord.Embed(
            title="Rune Goldberg Machine",
            description=f"Resets {timestamp}",
            url="https://runescape.wiki/w/Rune_Goldberg_Machine",
        )
        em.set_thumbnail(url=self.slot1.image)
        em.add_field(name="Slot 1", value=f"- {self.slot1.name.title()} Rune ({self.slot1.cost})")
        slot_2 = "\n".join(f"- {i.name.title()} Rune ({i.cost})" for i in self.slot2)
        em.add_field(name="Slot 2", value=slot_2)
        return em
