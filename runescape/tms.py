from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Literal, Optional, Tuple

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number

from .helpers import get_runedate, name_to_image, runedate_to_datetime
from .rsrandom import JavaRandom


class TMSTransformer(discord.app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: str) -> TMSItems:
        if argument.isdigit() and -1 <= int(argument) <= 31:
            return TMSItems(int(argument))
        for e, name in TMSItems.names().items():
            if argument.lower() in name.lower():
                return e

        raise commands.BadArgument(
            f"`{argument}` doesn't look like a valid Travelling Merchant Item."
        )

    async def transform(self, interaction: discord.Interaction, argument: str) -> TMSItems:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        choices = [
            discord.app_commands.Choice(name=name, value=str(e.value))
            for e, name in TMSItems.names().items()
            if current.lower() in name.lower()
        ]
        return choices[:25]


class TMSItems(Enum):
    uncharted_island_map = -1
    gift_for_the_reaper = 0
    broken_fishing_rod = 1
    barrel_of_bait = 2
    anima_crystal = 3
    small_goebie_burial_charm = 4
    medium_goebie_burial_charm = 5
    menaphite_gift_offering_small = 6
    menaphite_gift_offering_medium = 7
    shattered_anima = 8
    dnd_token_daily = 9
    sacred_clay = 10
    livid_plant = 11
    slayer_vip_token = 12
    silverhawk_down = 13
    unstable_air_rune = 14
    advanced_pulse_core = 15
    tangled_fishbowl = 16
    unfocused_damage_enhancer = 17
    horn_of_honour = 18
    taijitu = 19
    large_goebie_burial_charm = 20
    menaphite_gift_offering_large = 21
    dnd_token_weekly = 22
    dnd_token_monthly = 23
    dungeoneering_wildcard = 24
    message_in_a_bottle = 25
    crystal_triskelion = 26
    starved_ancient_effigy = 27
    deathtouched_dart = 28
    dragonkin_lamp = 29
    harmonic_dust = 30
    unfocused_reward_enhancer = 31

    def __str__(self):
        return self.names()[self]

    @property
    def url(self):
        name = str(self).replace(" ", "_")
        return f"https://runescape.wiki/w/{name}"

    @property
    def image_url(self):
        name = {
            TMSItems.silverhawk_down: "Silverhawk feathers",
            TMSItems.starved_ancient_effigy: "Ancient effigy",
        }.get(self, str(self))
        return name_to_image(name)

    @property
    def image(self):
        name = {
            TMSItems.silverhawk_down: "Silverhawk feathers",
            TMSItems.starved_ancient_effigy: "Ancient effigy",
        }.get(self, str(self))
        return name.replace(" ", "_").replace("(", "").replace(")", "")

    @staticmethod
    def names() -> Dict[TMSItems, str]:
        return {
            TMSItems.uncharted_island_map: "uncharted island map",
            TMSItems.barrel_of_bait: "Barrel of bait",
            TMSItems.tangled_fishbowl: "Tangled fishbowl",
            TMSItems.broken_fishing_rod: "Broken fishing rod",
            TMSItems.small_goebie_burial_charm: "Small goebie burial charm",
            TMSItems.medium_goebie_burial_charm: "Goebie burial charm",
            TMSItems.menaphite_gift_offering_small: "Menaphite gift offering (small)",
            TMSItems.menaphite_gift_offering_medium: "Menaphite gift offering (medium)",
            TMSItems.unstable_air_rune: "Unstable air rune",
            TMSItems.anima_crystal: "Anima crystal",
            TMSItems.slayer_vip_token: "Slayer VIP Coupon",
            TMSItems.dnd_token_daily: "Distraction & Diversion reset token (daily)",
            TMSItems.unfocused_damage_enhancer: "Unfocused damage enhancer",
            TMSItems.sacred_clay: "Sacred clay (Deep Sea Fishing)",
            TMSItems.shattered_anima: "Shattered anima",
            TMSItems.advanced_pulse_core: "Advanced pulse core",
            TMSItems.livid_plant: "Livid plant (Deep Sea Fishing)",
            TMSItems.gift_for_the_reaper: "Gift for the Reaper",
            TMSItems.silverhawk_down: "Silverhawk down",
            TMSItems.large_goebie_burial_charm: "Large goebie burial charm",
            TMSItems.message_in_a_bottle: "Message in a bottle (Deep Sea Fishing)",
            TMSItems.dragonkin_lamp: "Dragonkin lamp",
            TMSItems.dungeoneering_wildcard: "Dungeoneering Wildcard",
            TMSItems.menaphite_gift_offering_large: "Menaphite gift offering (large)",
            TMSItems.taijitu: "Taijitu",
            TMSItems.dnd_token_weekly: "Distraction & Diversion reset token (weekly)",
            TMSItems.dnd_token_monthly: "Distraction & Diversion reset token (monthly)",
            TMSItems.starved_ancient_effigy: "Starved ancient effigy",
            TMSItems.harmonic_dust: "Harmonic dust",
            TMSItems.crystal_triskelion: "Crystal triskelion",
            TMSItems.deathtouched_dart: "Deathtouched dart",
            TMSItems.unfocused_reward_enhancer: "Unfocused reward enhancer",
            TMSItems.horn_of_honour: "Horn of honour",
        }

    @property
    def use(self) -> str:
        return {
            TMSItems.uncharted_island_map: "Allows travel to an [uncharted island](https://runescape.wiki/w/Uncharted_Isles) with the chance of 3–6 special resources at the cost of no supplies.\n    - In addition, players may also rarely receive a [red uncharted island map](https://runescape.wiki/w/Uncharted_island_map_(red)). The red map is received first if rolled successfully.",
            TMSItems.barrel_of_bait: "10% chance to gain an additional catch for 3 minutes.",
            TMSItems.tangled_fishbowl: "5% Fishing experience boost for 3 minutes.",
            TMSItems.broken_fishing_rod: "10% bonus catch rate for 3 minutes.",
            TMSItems.small_goebie_burial_charm: "50 [Goebie Reputation](https://runescape.wiki/w/Reputation_(Mazcab)) or 50 Teci.",
            TMSItems.medium_goebie_burial_charm: "100 [Goebie Reputation](https://runescape.wiki/w/Reputation_(Mazcab)) or 100 Teci.",
            TMSItems.menaphite_gift_offering_small: "Variety of rewards, see page.",
            TMSItems.menaphite_gift_offering_medium: "Variety of rewards, see page.",
            TMSItems.unstable_air_rune: "5,000 [Runespan points](https://runescape.wiki/w/Runespan#Rewards).",
            TMSItems.anima_crystal: "500 [faction reputation](https://runescape.wiki/w/Reputation_(Heart_of_Gielinor)).",
            TMSItems.slayer_vip_token: "Redeemed for 1–7 Slayer VIP tickets.",
            TMSItems.dnd_token_daily: "One-time use to reset a daily [Distractions and Diversions](https://runescape.wiki/w/Distractions_and_Diversions).",
            TMSItems.unfocused_damage_enhancer: "Allows choice of any damage enhancer at the cost of lower charges.",
            TMSItems.sacred_clay: "50–100 Stealing Creation points.",
            TMSItems.shattered_anima: "[Shattered Worlds Reward](https://runescape.wiki/w/Shattered_Worlds_Reward_Shop).",
            TMSItems.advanced_pulse_core: "50% extra experience that does not stack with other sources of bonus experience, up to the equivalent of a medium prismatic lamp.",
            TMSItems.livid_plant: "10,000 to 40,000 produce points.",
            TMSItems.gift_for_the_reaper: "20 Reaper points.",
            TMSItems.silverhawk_down: "An untradable version of silverhawk feathers. See silverhawk down for experience calculator.",
            TMSItems.large_goebie_burial_charm: "150 [Goebie Reputation](https://runescape.wiki/w/Reputation_(Mazcab)) or 150 Teci.",
            TMSItems.message_in_a_bottle: "One-time choice between three Deep Sea Fishing boosts.",
            TMSItems.dragonkin_lamp: "Rewards a set amount of experience.",
            TMSItems.dungeoneering_wildcard: "Consuming the card inside Daemonheim rewards 50% extra experience and [tokens](https://runescape.wiki/w/Dungeoneering_token).",
            TMSItems.menaphite_gift_offering_large: "Variety of rewards, see page.",
            TMSItems.taijitu: "Secondary currency used for the Waiko Reward Shop.",
            TMSItems.dnd_token_weekly: "One-time use to reset a weekly Distractions and [Distractions and Diversions](https://runescape.wiki/w/Distractions_and_Diversions).",
            TMSItems.dnd_token_monthly: "One-time use to reset a monthly Distractions and [Distractions and Diversions](https://runescape.wiki/w/Distractions_and_Diversions).",
            TMSItems.starved_ancient_effigy: "Rewards a set amount of experience in multiple skills.",
            TMSItems.harmonic_dust: "Used for creating crystal tools.",
            TMSItems.crystal_triskelion: "Deposited in a cliff face south of Rellekka to obtain a clue scroll (elite) and variety of other rewards.",
            TMSItems.deathtouched_dart: "Insta-kill majority of all monsters.",
            TMSItems.unfocused_reward_enhancer: "Allows choice of any reward enhancer at the cost of lower charges.",
            TMSItems.horn_of_honour: "Awards 200 [Barbarian Assault Honour Points](https://runescape.wiki/w/Honour_Points) in a role of the player's choice.",
        }[self]

    @property
    def cost(self) -> int:
        return {
            TMSItems.uncharted_island_map: 800000,
            TMSItems.medium_goebie_burial_charm: 100000,
            TMSItems.menaphite_gift_offering_small: 100000,
            TMSItems.menaphite_gift_offering_medium: 300000,
            TMSItems.unstable_air_rune: 250000,
            TMSItems.anima_crystal: 150000,
            TMSItems.slayer_vip_token: 200000,
            TMSItems.dnd_token_daily: 250000,
            TMSItems.unfocused_damage_enhancer: 500000,
            TMSItems.sacred_clay: 600000,
            TMSItems.shattered_anima: 750000,
            TMSItems.advanced_pulse_core: 800000,
            TMSItems.livid_plant: 1000000,
            TMSItems.gift_for_the_reaper: 1250000,
            TMSItems.silverhawk_down: 1500000,
            TMSItems.large_goebie_burial_charm: 150000,
            TMSItems.message_in_a_bottle: 200000,
            TMSItems.dragonkin_lamp: 250000,
            TMSItems.dungeoneering_wildcard: 400000,
            TMSItems.menaphite_gift_offering_large: 500000,
            TMSItems.taijitu: 800000,
            TMSItems.dnd_token_weekly: 400000,
            TMSItems.dnd_token_monthly: 1000000,
            TMSItems.starved_ancient_effigy: 1000000,
            TMSItems.harmonic_dust: 2000000,
            TMSItems.crystal_triskelion: 2000000,
            TMSItems.deathtouched_dart: 5000000,
            TMSItems.unfocused_reward_enhancer: 10000000,
            TMSItems.horn_of_honour: 1000000,
        }.get(self, 5000)

    @property
    def quantity(self) -> Tuple[int, int]:
        return {
            TMSItems.shattered_anima: (500000, 2000000),
            TMSItems.advanced_pulse_core: (1, 3),
            TMSItems.silverhawk_down: (50, 100),
            TMSItems.dungeoneering_wildcard: (1, 3),
            TMSItems.taijitu: (3, 5),
            TMSItems.harmonic_dust: (500, 1000),
        }.get(self, (1, 1))

    @property
    def quantity_str(self) -> str:
        if self.quantity == (1, 1):
            return "1"
        return f"{humanize_number(self.quantity[0])}-{humanize_number(self.quantity[1])}"


class TravellingMerchant:
    slots_ab: List[TMSItems] = [TMSItems(i) for i in range(19)]
    slot_map: Dict[str, List[TMSItems]] = {
        "A": slots_ab,
        "B": slots_ab,
        "C": [TMSItems(i) for i in range(19, 32)],
    }
    slot_constants: Dict[str, List[int]] = {"A": [3, 19], "B": [8, 19], "C": [5, 13]}

    def __init__(self, *, runedate: Optional[float] = None, date_time: Optional[datetime] = None):
        if runedate is None:
            runedate = get_runedate(date_time)
        self.runedate = int(runedate)
        self.a = self.get("A", runedate=runedate)
        self.b = self.get("B", runedate=runedate)
        self.c = self.get("C", runedate=runedate)
        self.always = TMSItems(-1)

    def __str__(self):
        today = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        daily = today + timedelta(hours=((0 - today.hour) % 24))
        timestamp = discord.utils.format_dt(daily, "R")
        always = TMSItems.uncharted_island_map
        return (
            f"Resets {timestamp}\n"
            f"- [{always}]({always.url})\n - {always.use}\n - Cost: {humanize_number(always.cost)}"
            f"\n - Quantity: {always.quantity_str}\n"
            f"- [{self.a}]({self.a.url})\n - {self.a.use}\n - Cost: {humanize_number(self.a.cost)}"
            f"\n - Quantity: {self.a.quantity_str}\n"
            f"- [{self.b}]({self.b.url})\n - {self.b.use}\n - Cost: {humanize_number(self.b.cost)}"
            f"\n - Quantity: {self.b.quantity_str}\n"
            f"- [{self.c}]({self.c.url})\n - {self.c.use}\n - Cost: {humanize_number(self.c.cost)}"
            f"\n - Quantity: {self.c.quantity_str}\n"
        )

    def list_items(self) -> str:
        timestamp = discord.utils.format_dt(runedate_to_datetime(self.runedate), "D")
        # items = humanize_list([str(self.always), str(self.a), str(self.b), str(self.c)])
        _items = [self.always, self.a, self.b, self.c]
        items = "\n".join(f" - {i}" for i in _items)
        return f"- {timestamp}\n{items}"

    def get(self, slot: Literal["A", "B", "C"], *, runedate: Optional[float] = None) -> TMSItems:
        if runedate is not None:
            self.runedate = int(runedate)
        k, n = self.slot_constants[slot]
        seed = (self.runedate << 32) + (self.runedate % k)
        return self.slot_map[slot][JavaRandom(seed).next_int(n)]

    def embeds(self) -> List[discord.Embed]:
        ems = []
        em = discord.Embed(
            title="Travelling Merchant's Shop",
            description=str(self),
            url="https://runescape.wiki/w/Travelling_Merchant's_Shop",
        )
        for slot in ["always", "a", "b", "c"]:
            embed = em.copy()
            if slot == "always":
                embed.set_image(url=TMSItems.uncharted_island_map.image_url)
            else:
                embed.set_image(url=getattr(self, slot).image_url)
            ems.append(embed)
        return ems

    @classmethod
    async def find_next(cls, item: TMSItems, number: int) -> List[TravellingMerchant]:
        ret = []
        start_date = get_runedate()
        day = 0
        max_days = 1000
        while len(ret) < number:
            tms = TravellingMerchant(runedate=start_date + day)
            day += 1
            if item is tms.a or item is tms.b or item is tms.c or item is tms.always:
                ret.append(tms)
            # we shouldn't ever go this long but just in case
            # this is a good practice
            if max_days >= 1000:
                break
        return ret
