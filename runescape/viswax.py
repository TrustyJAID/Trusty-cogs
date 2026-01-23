from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

import discord
from redbot.core import commands

from .helpers import IMAGE_URL, get_runedate
from .rsrandom import JavaRandom


class RuneTransformer(discord.app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: str) -> Optional[Runes]:
        if argument.isdigit():
            try:
                return Runes(int(argument))
            except Exception:
                return None
        for rune in Runes:
            if argument.lower() == rune.name.lower():
                return rune
        return None

    async def transform(self, interaction: discord.Interaction, argument: str) -> Optional[Runes]:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        choices = [
            discord.app_commands.Choice(name=rune.name, value=str(rune.value))
            for rune in Runes
            if current.lower() in rune.name.lower()
        ]
        return choices[:25]


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
    def __init__(
        self,
        *,
        runedate: Optional[float] = None,
        date_time: Optional[datetime] = None,
        known_rune: Optional[Runes],
    ):
        if runedate is None:
            runedate = get_runedate(date_time)

        self.slot1: Runes = self.get_slot1(int(runedate))
        self.slot2: List[Runes] = self.get_slot2(int(runedate))
        self.runedate = runedate
        self.known_rune = known_rune

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
        if self.known_rune is not None:
            msg += f"- Slot 3:\n- {self.known_rune.name.title()} Rune ({self.known_rune.cost})\n"
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
        if self.known_rune is not None:
            em.add_field(
                name="Slot 3",
                value=f"- {self.known_rune.name.title()} Rune ({self.known_rune.cost})",
            )
        return em

    def layout(self) -> discord.ui.LayoutView:
        layout = discord.ui.LayoutView()
        container = discord.ui.Container()
        today = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        daily = today + timedelta(hours=((0 - today.hour) % 24))
        timestamp = discord.utils.format_dt(daily, "R")
        container.add_item(
            discord.ui.TextDisplay(
                f"# [Rune Goldberg Machine](https://runescape.wiki/w/Rune_Goldberg_Machine)\nResets {timestamp}"
            )
        )
        container.add_item(discord.ui.Separator())
        slot_1 = discord.ui.Section(
            discord.ui.TextDisplay(
                f"Slot 1\n- {self.slot1.name.title()} Rune ({self.slot1.cost})"
            ),
            accessory=discord.ui.Thumbnail(self.slot1.image),
        )
        container.add_item(slot_1)
        container.add_item(discord.ui.Separator())
        slot_2_text = "\n".join(f"- {i.name.title()} Rune ({i.cost})" for i in self.slot2)
        slot_2 = discord.ui.Section(
            discord.ui.TextDisplay(f"Slot 2\n{slot_2_text}"),
            accessory=discord.ui.Thumbnail(self.slot2[0].image),
        )
        container.add_item(slot_2)
        container.add_item(discord.ui.Separator())
        if self.known_rune is not None:
            slot_3 = discord.ui.Section(
                discord.ui.TextDisplay(
                    f"Slot 3\n- {self.known_rune.name.title()} Rune ({self.known_rune.cost})"
                ),
                accessory=discord.ui.Thumbnail(self.known_rune.image),
            )
            container.add_item(slot_3)
            container.add_item(discord.ui.Separator())
        layout.add_item(container)
        return layout
